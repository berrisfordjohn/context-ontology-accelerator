"""Load one scenario of the pharma SDTM/SEND/USDM/master dataset into AWS (S3 + Glue + Athena check).

  uv run --no-project --with boto3 --with "botocore[crt]" python load_pharma.py --scenario 1 --region eu-north-1 [--namespace-id <uuid> --prefix coa2]

Scenario 1 -> 15 Glue databases (one per study) ; scenario 2 -> 4 databases. One bucket per scenario.
Idempotent. With --namespace-id every database and the bucket get the <prefix>:namespace tag COA needs.
Prints each database name so you can register one COA Glue source per database.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

HERE = Path(__file__).parent
FOLDERS = {"1": "scenario1_separate", "2": "scenario2_combined"}
NUMERIC = {"AGE": "int", "EXDOSE": "double", "VSSTRESN": "double", "LBSTRESN": "double", "LBNRLO": "double", "LBNRHI": "double",
           "BWSTRESN": "double", "BWDY": "int", "PLANNED_ENROLLMENT": "int"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=["1", "2"], required=True)
    ap.add_argument("--region", default="eu-north-1")
    ap.add_argument("--prefix", default="coa")
    ap.add_argument("--namespace-id")
    ap.add_argument("--skip-verify", action="store_true")
    a = ap.parse_args()
    sess = boto3.Session(region_name=a.region)
    account = sess.client("sts").get_caller_identity()["Account"]
    bucket = f"coa-pharma-s{a.scenario}-{account}-{a.region}"
    s3, glue, athena = sess.client("s3"), sess.client("glue"), sess.client("athena")
    folder = FOLDERS[a.scenario]
    schema = json.loads((HERE / "schema.json").read_text())[folder]

    try:
        kw = {} if a.region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": a.region}}
        s3.create_bucket(Bucket=bucket, **kw)
    except ClientError as e:
        if e.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
            raise
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})

    for db, tables in schema.items():
        try:
            glue.create_database(DatabaseInput={"Name": db, "Description": f"Synthetic pharma data, scenario {a.scenario}"})
        except glue.exceptions.AlreadyExistsException:
            pass
        for t, cols in tables.items():
            s3.upload_file(str(HERE / "data" / folder / db / f"{t}.csv"), bucket, f"curated/{db}/{t}/data.csv")
            tin = {"Name": t, "TableType": "EXTERNAL_TABLE",
                   "Parameters": {"classification": "csv", "skip.header.line.count": "1", "EXTERNAL": "TRUE"},
                   "StorageDescriptor": {
                       "Columns": [{"Name": c.lower(), "Type": NUMERIC.get(c, "string")} for c in cols],
                       "Location": f"s3://{bucket}/curated/{db}/{t}/",
                       "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                       "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                       "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.serde2.OpenCSVSerde",
                                     "Parameters": {"separatorChar": ",", "quoteChar": "\"", "escapeChar": "\\"}}}}
            try:
                glue.create_table(DatabaseName=db, TableInput=tin)
            except glue.exceptions.AlreadyExistsException:
                glue.update_table(DatabaseName=db, TableInput=tin)
        print(f"database {db}: {len(tables)} tables")
        if a.namespace_id:
            glue.tag_resource(ResourceArn=f"arn:aws:glue:{a.region}:{account}:database/{db}", TagsToAdd={f"{a.prefix}:namespace": a.namespace_id})
    if a.namespace_id:
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": f"{a.prefix}:namespace", "Value": a.namespace_id}]})
        print("tagged databases and bucket")

    if not a.skip_verify:
        bad = False
        for db, tables in schema.items():
            for t in tables:
                qid = athena.start_query_execution(QueryString=f'SELECT COUNT(*) FROM "{db}"."{t}"',
                                                   ResultConfiguration={"OutputLocation": f"s3://{bucket}/athena-results/"},
                                                   WorkGroup="primary")["QueryExecutionId"]
                while True:
                    st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
                    if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                        break
                    time.sleep(1)
                if st["State"] != "SUCCEEDED":
                    print(f"  {db}.{t}: {st['State']} {st.get('StateChangeReason')}")
                    bad = True
                    continue
                n = int(athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"][1]["Data"][0]["VarCharValue"])
                csv_n = sum(1 for _ in open(HERE / "data" / folder / db / f"{t}.csv", encoding="utf-8")) - 1
                bad |= n != csv_n
                if n != csv_n:
                    print(f"  {db}.{t}: athena={n} csv={csv_n} MISMATCH")
        if bad:
            sys.exit("verification failed")
        print("all tables verified against CSV row counts")
    print(f"Bucket: {bucket}")


if __name__ == "__main__":
    main()
