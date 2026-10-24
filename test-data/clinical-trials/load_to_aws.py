"""Load the synthetic clinical-trial dataset into AWS so COA can scan it.

Steps: create S3 bucket -> upload CSVs (one folder per table) and documents -> create Glue database + tables
(OpenCSVSerde, header skipped) -> tag database/bucket with <prefix>:namespace -> verify row counts in Athena.

Usage (boto3 is fetched on the fly by uv):
  uv run --with boto3 python load_to_aws.py --region eu-north-1 [--namespace-id <uuid>] [--prefix coa]

Idempotent: safe to re-run. Use --namespace-id once the COA namespace exists (tags are required before
COA can register the sources); without it the tagging step is skipped.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

HERE = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default=boto3.session.Session().region_name or "eu-north-1")
    ap.add_argument("--database", default="clinical_trials")
    ap.add_argument("--bucket", help="default: coa-clinical-trials-<account>-<region>")
    ap.add_argument("--prefix", default="coa", help="COA resource prefix (tag key is <prefix>:namespace)")
    ap.add_argument("--namespace-id", help="COA namespace UUID; enables tagging of the database and bucket")
    ap.add_argument("--skip-verify", action="store_true")
    a = ap.parse_args()

    sess = boto3.Session(region_name=a.region)
    account = sess.client("sts").get_caller_identity()["Account"]
    bucket = a.bucket or f"coa-clinical-trials-{account}-{a.region}"
    s3, glue, athena = sess.client("s3"), sess.client("glue"), sess.client("athena")
    schema = json.loads((HERE / "schema.json").read_text())
    for t in schema:
        if not (HERE / "data" / f"{t}.csv").exists():
            sys.exit(f"missing data/{t}.csv - run generate_data.py first")

    # 1. bucket
    try:
        kwargs = {} if a.region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": a.region}}
        s3.create_bucket(Bucket=bucket, **kwargs)
        print(f"created bucket {bucket}")
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou",):
            raise
        print(f"bucket {bucket} already exists")
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})

    # 2. upload
    for t in schema:
        s3.upload_file(str(HERE / "data" / f"{t}.csv"), bucket, f"curated/{t}/data.csv")
    for f in (HERE / "documents").glob("*"):
        s3.upload_file(str(f), bucket, f"documents/{f.name}")
    print(f"uploaded {len(schema)} tables and documents to s3://{bucket}")

    # 3. glue database + tables
    try:
        glue.create_database(DatabaseInput={"Name": a.database, "Description": "Synthetic clinical trial data (test)"})
    except glue.exceptions.AlreadyExistsException:
        pass
    for t, cols in schema.items():
        tinput = {
            "Name": t,
            "TableType": "EXTERNAL_TABLE",
            "Parameters": {"classification": "csv", "skip.header.line.count": "1", "EXTERNAL": "TRUE"},
            "StorageDescriptor": {
                "Columns": [{"Name": c["name"], "Type": c["type"]} for c in cols],
                "Location": f"s3://{bucket}/curated/{t}/",
                "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.serde2.OpenCSVSerde",
                              "Parameters": {"separatorChar": ",", "quoteChar": "\"", "escapeChar": "\\"}},
            },
        }
        try:
            glue.create_table(DatabaseName=a.database, TableInput=tinput)
        except glue.exceptions.AlreadyExistsException:
            glue.update_table(DatabaseName=a.database, TableInput=tinput)
    print(f"glue database '{a.database}' with {len(schema)} tables ready")

    # 4. tags
    if a.namespace_id:
        key = f"{a.prefix}:namespace"
        db_arn = f"arn:aws:glue:{a.region}:{account}:database/{a.database}"
        glue.tag_resource(ResourceArn=db_arn, TagsToAdd={key: a.namespace_id})
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": key, "Value": a.namespace_id}]})
        print(f"tagged glue database and bucket with {key}={a.namespace_id}")
    else:
        print("no --namespace-id: skipped tagging (re-run with it once the namespace exists)")

    # 5. verify in athena
    if not a.skip_verify:
        out = f"s3://{bucket}/athena-results/"
        bad = False
        for t in schema:
            qid = athena.start_query_execution(
                QueryString=f'SELECT COUNT(*) FROM "{a.database}"."{t}"',
                ResultConfiguration={"OutputLocation": out}, WorkGroup="primary")["QueryExecutionId"]
            while True:
                st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
                if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                    break
                time.sleep(1)
            if st["State"] != "SUCCEEDED":
                print(f"  {t}: ATHENA {st['State']} - {st.get('StateChangeReason')}")
                bad = True
                continue
            n = int(athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"][1]["Data"][0]["VarCharValue"])
            csv_rows = sum(1 for _ in open(HERE / "data" / f"{t}.csv", encoding="utf-8")) - 1
            ok = n == csv_rows
            bad |= not ok
            print(f"  {t}: athena={n} csv={csv_rows} {'OK' if ok else 'MISMATCH'}")
        if bad:
            sys.exit("verification failed")
    print(f"\nDone. Glue database: {a.database}   Bucket: {bucket}   Account: {account}")


if __name__ == "__main__":
    main()
