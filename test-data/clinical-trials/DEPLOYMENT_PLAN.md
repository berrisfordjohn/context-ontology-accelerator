# Deployment and Test Plan — Context Ontology Accelerator (COA) with Clinical-Trial Test Data

Status: **PLAN — not yet executed.** Step 2 of the task is to execute it.
Target: AWS account `<account-id>`, region `eu-north-1`, resource prefix `coa`, environment `dev`.

---

## 1. What gets deployed

`make deploy-dev` provisions the whole platform from CDK (17 stacks + a Databricks connector stack). You do not provision Neptune/EC2 by hand; CDK does. Services involved:

| Layer | AWS services | Notes |
|---|---|---|
| Network | VPC, subnets, NAT gateway, VPC endpoints, Cloud Map | One new VPC (account has 1 of 5 used) |
| Graph + vector | **Amazon Neptune** (`db.r8g.large`), **OpenSearch Serverless** | Neptune is only available on the *Paid* plan |
| Compute | Lambda, ECS on Fargate (enrichment, doc ingestion, per-namespace VKG/Ontop), **Bedrock AgentCore Runtime** (serve + MCP) | Fargate quota default is 6 vCPU, tight |
| AI | **Bedrock** (Claude Sonnet 5, Haiku 4.5, Cohere Embed v4) + Guardrails | Needs `eu.` inference profiles in this region |
| Catalog / data | **DataZone** (namespace = project), **Glue**, **Athena**, S3, DynamoDB | Our test data lives in S3 + Glue; Athena queries it |
| API / UI / auth | API Gateway, WAF, Cognito, CloudFront (+ WAF in us-east-1), Step Functions, SQS, EventBridge | |

EC2 is **not** needed by the application. (Optional fallback: a Graviton EC2 build host if the laptop cannot build the container images — see Risks.)

## 2. Findings from inspecting the current environment

| Item | Current state | Needed | Action |
|---|---|---|---|
| AWS plan | **Free**, $100 credit | Paid (Neptune is not in the Free plan) | **Upgrade in AWS Settings > Billing** (owner action) |
| Region | `eu-north-1` | Neptune, DataZone, OpenSearch Serverless, AgentCore Runtime, Bedrock all available | AgentCore Runtime listed for Stockholm; verify the rest in preflight |
| Bedrock profiles | `eu.anthropic.claude-sonnet-5`, `eu.anthropic.claude-haiku-4-5-...`, `eu.cohere.embed-v4:0` exist in eu-north-1 | Defaults are `us.` and are rejected outside the US | Write `/coa/config` in SSM with `eu.` IDs **before** deploying |
| Bedrock model access | not yet verified | Access to all 4 models | Verify with a test `converse` call |
| CDK bootstrap | **Not bootstrapped** (`CDKToolkit` missing) | eu-north-1 **and** us-east-1 | `cdk bootstrap` both |
| Docker | Installed, **daemon not running** | Running + arm64/amd64 emulation | Start Docker Desktop, run `docker buildx inspect --bootstrap` |
| Shell | PowerShell only; no `make` | `make`, bash scripts | Use **WSL2 Ubuntu** (bash installed) and run everything there |
| Python | 3.10 | 3.12 | `uv` (0.4.24, upgrade recommended) / `mise` |
| Node | v25.1 | 22.x | `mise install` pins Node 22 |
| pnpm, Java 17-24, Maven, Gradle | **missing** | pnpm 10.27, JDK 21, Maven | `mise install` inside WSL |
| VPC quota | 1 VPC used | < 5 | OK |
| Lambda concurrency | not yet checked | unreserved headroom | Check; else `SCL_LAMBDA_RESERVED_CONCURRENCY=0` |
| Fargate vCPU quota | not yet checked | default 6 | Check `L-3032A538`; request increase if < 12 |
| Service control policies | The project has managed SCPs | May block some services | Watch for AccessDenied during deploy; see AWS docs on project SCP/RCP |

### Cost warning
The platform runs always-on resources: Neptune instance, OpenSearch Serverless OCUs (standby replicas double consumption), a NAT gateway, Fargate services, VPC endpoints. Expect **tens of US dollars per day** (verify with the AWS Pricing Calculator). The $100 free credit would be consumed in days. Mitigations built into the plan: `aoss_min_ocu=2` (default), single Neptune instance, tear everything down with `make destroy-dev` as soon as testing finishes. Budget alert recommended.

## 3. Execution plan

### Phase 0 — Decisions / prerequisites (needs you)
1. Upgrade the account to the Paid plan and set a budget alert.
2. Provide `initialAdminEmail` (a mailbox you control; Cognito sends the temporary password).
3. Choose help level for AWS guidance (low/medium/high).

### Phase 1 — Workstation (WSL2 Ubuntu)
```bash
sudo apt-get update && sudo apt-get install -y make git curl unzip build-essential
curl https://mise.run | sh   # then: mise install  (Python 3.12, Java 17/21, Node 22, pnpm 10.27, Maven)
# Docker Desktop: Settings > Resources > WSL integration > enable for the distro
docker buildx inspect --bootstrap
docker run --rm --platform linux/arm64 alpine uname -m   # must print aarch64 (x86_64 host)
aws sts get-caller-identity                              # credentials available inside WSL
```
Clone/open the repo inside WSL (`/mnt/c/...` works but is slow; copying to `~/` is faster), then `make setup`.

### Phase 2 — AWS account preparation
```bash
export AWS_DEFAULT_REGION=eu-north-1 CDK_DEFAULT_REGION=eu-north-1
npx cdk bootstrap aws://<account-id>/eu-north-1
npx cdk bootstrap aws://<account-id>/us-east-1        # required by the edge-waf stack
aws service-quotas get-service-quota --service-code fargate --quota-code L-3032A538
aws lambda get-account-settings --query 'AccountLimit.[ConcurrentExecutions,UnreservedConcurrentExecutions]'
```
Create the deploy config (model IDs for the EU):
```bash
aws ssm put-parameter --name /coa/config --type SecureString --overwrite --value '{
  "initialAdminEmail": "<your-email>",
  "bedrockLlmModelId": "eu.anthropic.claude-sonnet-5",
  "bedrockInductionLlmModelId": "eu.anthropic.claude-sonnet-5",
  "bedrockChatModelId": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
  "bedrockEmbedModelId": "eu.cohere.embed-v4:0",
  "bedrockEmbedDimensions": 1024
}'
```
(Exact key set is validated at `cdk synth`; adjust to the error text if needed.)

### Phase 3 — Deploy
```bash
SCL_SMUS_ADMIN_ARNS=<arn of the admin federated role> \
SCL_LAMBDA_RESERVED_CONCURRENCY=0   `# only if the Lambda quota check requires it` \
make preflight && make deploy-dev        # ~40 min
```
Notes: the account has no role named `Admin`, so `SCL_SMUS_ADMIN_ARNS` is **required**. Capture outputs: web URL (`coa-dev-web` → `WebAppUrl`), API URL (`scripts/fetch-runtime-config.sh`), Cognito pool ID (SSM `/coa/userpool-id`).

### Phase 4 — Users and access
```bash
aws cognito-idp admin-create-user --user-pool-id <POOL_ID> --username <email> \
  --user-attributes Name=email,Value=<email> Name=email_verified,Value=true
```
Sign in to the web app, then grant `platform-admin` to the user (Permissions page or API). For scripted API calls use `coa-skills/control-plane/scripts/coa_login.py login --client web`.

### Phase 5 — Create the namespace
Web app: **Administration > Namespaces > Create namespace** — name `clinical-trials`, language `en`, owner = your email. Or `POST /namespaces`. Record the returned `namespaceId` (UUID).

### Phase 6 — Load the test data (see `README.md` in this folder)
```bash
cd test-data/clinical-trials
python generate_data.py                       # only if you want to regenerate; CSVs are already committed
uv run --with boto3 python load_to_aws.py --region eu-north-1 --namespace-id <namespaceId>
```
This creates the S3 bucket, Glue database `clinical_trials` (10 tables), tags both with `coa:namespace`, and verifies row counts through Athena.

### Phase 7 — Scan, review, build the ontology
1. **Register source 1 (structured):** Sources > Connect Source > Glue Data Catalog; catalog id `<account-id>`, region `eu-north-1`, database `clinical_trials`. Wait for the scan + AI enrichment (status moves to review-ready).
2. **Review & approve:** check inferred primary/foreign keys (`study_id`, `subject_id`, `arm_id`, `site_id`, `drug_id`, `meddra_pt_code`); approve all tables (bulk approve).
3. **Register source 2 (documents):** S3 bucket source, `s3://<bucket>/documents/` (bucket tag already set), or upload the six `documents/*.md` files via the UI.
4. **Induce the ontology:** Ontology > Induction, strategy `table_to_ontology`, select the Glue source. Review the proposal, check mapped classes/R2RML, **accept**.
5. *(Optional comparison)* Upload `clinical_trials_ontology.ttl` as a manual ontology and compare it with the induced one.
6. **Metrics:** create the five metrics in `metrics.json` (replace `REPLACE_WITH_SOURCE_ID` with the source's `dataSourceId`).

### Phase 8 — Test the service
Run the questions in `TEST_QUESTIONS.md` in the Playground (SSE) and via REST `POST /namespaces/{id}/query`; compare numeric answers with `expected_answers.json`. Also exercise: graph view of ontology, MCP tools (`describe_schema`, `query`, `rag_retrieval`, `graph_traversal`) using the `mcp` client token, and a restricted-role user (data-analyst) to prove namespace RBAC.

### Phase 9 — Capture results and tear down
Record pass/fail per question and any defects. Then `SCL_DESTROY_YES=1 make destroy-dev` (also delete the test bucket and Glue database, `aws s3 rb s3://<bucket> --force`, `aws glue delete-database --name clinical_trials`). Ask before tearing down if the user wants to keep the environment.

## 3a. Build options: laptop, EC2 build host, or direct Docker

The deploy builds six container images, because `cdk deploy` builds each Docker asset itself:

| Image | Dockerfile | Context | Platform |
|---|---|---|---|
| Context Manager (serve and MCP stacks) | `packages/context-manager/Dockerfile` | repo root | linux/arm64 |
| VKG (Ontop) | `packages/vkg/Dockerfile` | `packages/vkg` | linux/arm64 |
| Ontology engine | `packages/ontology-engine/Dockerfile` | repo root | linux/amd64 |
| DB enrichment | `packages/sources/database/enrichment/Dockerfile` | repo root | linux/amd64 |
| Doc KG build | `packages/sources/documents/kg-build/Dockerfile` | repo root | linux/amd64 |

A host builds only one architecture natively and emulates the other with QEMU, which is slow. On an x86_64 laptop (the WSL2 run here) the arm64 images are emulated. The whole deploy took about 60 minutes.

### Option A: laptop or WSL2 (what was used)
Docker Desktop must be running before you start. It can take a few minutes after login, so check `docker version`. Register emulation once:
```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64,amd64
```
Use `~/.docker/config.json` with `{}` if the Windows credential helper (`"credsStore": "desktop.exe"`) breaks ECR Public pulls ("The stub received bad data").

### Option B: temporary EC2 build and deploy host (faster, portable)
Run the whole deploy from a Graviton instance in the same region, so arm64 images build natively, then terminate it afterwards. The EC2 build host needs no inbound access, so use SSM Session Manager instead of SSH.
```bash
# 1. Launch (eu-north-1): c7g.2xlarge (8 vCPU, arm64), Amazon Linux 2023 arm64 AMI, 100 GB gp3 root volume,
#    an instance profile with admin rights (or the same permissions as the deploy role), and outbound internet.
AMI=$(aws ssm get-parameter --region eu-north-1 \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 --query Parameter.Value --output text)
aws ec2 run-instances --region eu-north-1 --image-id "$AMI" --instance-type c7g.2xlarge \
  --iam-instance-profile Name=<profile-with-SSM-and-deploy-permissions> \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=100,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=coa-build}]'
aws ssm start-session --target <instance-id>

# 2. On the instance (once)
sudo dnf install -y git docker make gcc unzip
sudo systemctl enable --now docker && sudo usermod -aG docker $USER && newgrp docker
sudo docker run --privileged --rm tonistiigi/binfmt --install amd64      # arm64 is native; amd64 is emulated
curl https://mise.run | sh && ~/.local/bin/mise use -g node@22 java@temurin-21 maven pnpm@10.27.0 uv python@3.12
git clone <repo-url> coa && cd coa && ./scripts/smithy-generate.sh && ./scripts/setup-dev.sh

# 3. Same deploy steps as Phases 2-3 (SSM config, bootstrap, preflight, deploy) with the instance role's credentials
export AWS_DEFAULT_REGION=eu-north-1 CDK_DEFAULT_REGION=eu-north-1
SCL_SMUS_ADMIN_ARNS=<admin role arn> ./scripts/preflight-deploy.sh && ./scripts/deploy.sh dev
```
Notes:
- The instance role's ARN is not the federated admin role, so pass the human admin role in `SCL_SMUS_ADMIN_ARNS`.
- Take an AMI (`aws ec2 create-image`) after step 2 to reuse the toolchain on another machine, and stop the instance between deploys. Terminate it and delete the AMI and volume when finished.
- Fully-amd64 alternative: a `c7i.2xlarge` makes the three amd64 images native and emulates the three arm64 ones, so pick the Graviton host by default.

### Option C: build the images directly with Docker
Use this to check that an image builds, or to warm the local layer cache before `cdk deploy`. CDK deploy still builds and pushes its own hashed assets, so direct builds don't replace it, but on the same Docker host the cache makes the later CDK build much faster.
```bash
cd ~/coa    # repo root
docker buildx build --platform linux/arm64 -f packages/context-manager/Dockerfile -t coa/context-manager:local .
docker buildx build --platform linux/arm64 -t coa/vkg:local packages/vkg
docker buildx build --platform linux/amd64 -f packages/ontology-engine/Dockerfile -t coa/ontology-engine:local .
docker buildx build --platform linux/amd64 -f packages/sources/database/enrichment/Dockerfile -t coa/db-enrichment:local .
docker buildx build --platform linux/amd64 -f packages/sources/documents/kg-build/Dockerfile -t coa/doc-kg-build:local .
```
To run an image in a given ECR repo manually (for example to patch one service without a CDK deploy), log in, then tag and push:
```bash
aws ecr get-login-password --region eu-north-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.eu-north-1.amazonaws.com
docker tag coa/vkg:local <account-id>.dkr.ecr.eu-north-1.amazonaws.com/<repo>:<tag>
docker push <account-id>.dkr.ecr.eu-north-1.amazonaws.com/<repo>:<tag>
```
A manually pushed tag is not used by the stacks until you redeploy them with that asset hash, so `cdk deploy` is still the supported path.

### Lessons from the eu-north-1 run
- An SCP denied CloudFormation in us-east-1, so `*-edge-waf` couldn't deploy and the preflight's us-east-1 bootstrap check failed. Workaround: create the CloudFront WAF ACL by hand (`aws wafv2 create-web-acl --scope CLOUDFRONT --region us-east-1 ...`) and pass its ARN as the CDK context `cloudfront_web_acl_id`. `deploy.sh` has no `SCL_` variable for this, so a local one-line patch added the context key.
- No role named `Admin` existed, so `SCL_SMUS_ADMIN_ARNS` was required (`arn:aws:iam::<acct>:role/<admin-role-name>`).
- `SCL_LAMBDA_RESERVED_CONCURRENCY=0` skipped the Lambda headroom check.

## 3b. Scripted deploy and teardown (low-token path)

Scripts in [scripts/](scripts/), run from WSL2/Linux in a checkout of this repo:

```bash
export COA_ADMIN_EMAIL=<you@example.com>   # optional: SCL_PREFIX=coa2, COA_MODEL=<model id>
test-data/clinical-trials/scripts/preflight.sh    # checks only, ~30 s, near-zero cost
test-data/clinical-trials/scripts/deploy.sh       # runs preflight, writes config, deploys (~60 min)
test-data/clinical-trials/scripts/teardown.sh     # removes data, stacks, WAF ACL, config
```

Order of work: preflight, then deploy, then (Phases 4-8) sign in, create the namespace, run `load_to_aws.py`, register sources, ask the test questions, then `teardown.sh`. No Bedrock tokens are spent until Phase 7.

### Preflight checks that can stop a deployment (all run by `preflight.sh`, and it aborts before any cost is incurred)

| # | Check | Blocks when | Remedy |
|---|---|---|---|
| 1 | AWS credentials | Session expired | `aws login` |
| 2 | Account plan and credit | Not `PAID`/`ACTIVE`, or credit exhausted or a spend limit hit (the account is paused and calls return AccessDenied) | AWS Settings > Billing; ask a project owner to raise the limit |
| 3 | Tools: docker, node, pnpm, java; Docker daemon running | Missing or daemon stopped | Start Docker Desktop, or use the EC2 build host (3a) |
| 4 | SCP probe: `cognito-idp:CreateUserPool` (create, then delete) | Explicit SCP deny (seen on 2026-10-24, after it worked on the first deploy) | Needs the org policy changed or advanced features activated; no workaround, the auth stack needs Cognito |
| 5 | SCP probe: `ec2:AllocateAddress` (NAT needs it; `CreateNatGateway` is only proven by the deploy, so the network stack goes first and fails fast) | Explicit SCP deny | Same as above |
| 6 | SCP probe: WAF CloudFront ACL in us-east-1 | Denied | Warning only: CloudFront is deployed without a WAF |
| 7 | Bedrock model invoked for real (`converse`, 5 tokens) | `ThrottlingException` (quota 0), `AccessDenied` (model not enabled or not offered to the account), `ServiceUnavailable` | Support case for quota; choose a model that responds; the preflight in the repo only checks that a model is listed |
| 8 | Embedding model invoked for real | Same as above | Same as above |
| 9 | Stale stacks with the same prefix in `DELETE_FAILED`/`ROLLBACK_*` | CloudFormation cannot deploy over them | Delete them, or use another `SCL_PREFIX` (AgentCore ENIs can hold a network stack for ~8 h) |
| 10 | VPC headroom (limit 5) | 5 VPCs exist | Delete unused VPCs |
| 11 | CDK bootstrap in the region | Missing | `cdk bootstrap aws://<account>/<region>` (us-east-1 cannot be bootstrapped under this SCP, so that check is patched out) |

`deploy.sh` additionally: derives the admin role ARN for `SCL_SMUS_ADMIN_ARNS`, sets `SCL_LAMBDA_RESERVED_CONCURRENCY=0`, writes SSM `/<prefix>/config` with a single model for LLM, induction and chat (default Sonnet 4.6, the newest model this account can invoke) plus Cohere Embed v4, creates the CloudFront WAF ACL by hand (or skips the edge stack when WAF is denied), and applies the three local-only patches described above.

## 4. Risks and fallbacks

| Risk | Likelihood | Fallback |
|---|---|---|
| Free-plan/SCP blocks a required service | High until upgrade | Upgrade to Paid plan |
| A dependency (DataZone, Neptune r8g, AOSS NEXTGEN) not offered in eu-north-1 AZs | Medium | Preflight/synth will say; `SCL_NEPTUNE_INSTANCE_CLASS` for another class; otherwise use `eu-west-1`/`eu-central-1` (project region is fixed by the AWS account contact address, so confirm in AWS Settings first) |
| Laptop cannot build arm64 + amd64 images (emulation, memory) | Medium | Run the deploy from a Graviton EC2 instance (e.g. `c7g.2xlarge`, 100 GB disk, Docker + QEMU binfmt) in the same region, then terminate it |
| Fargate vCPU quota (6) exhausted by enrichment + VKG | Medium | Request quota increase before deploy |
| Bedrock model access/quota not enabled | Medium | Request access in console; reduce scan parallelism |
| Glue `date`/`double` columns not honoured by OpenCSVSerde | Low | Alter schema to `string` and CAST in metrics (documented fallback in README) |
| Deploy leaves orphaned resources | Medium | `make destroy-dev` + manual cleanup steps in `deploying.md` > Troubleshooting |

## 5. Definition of done
- All CloudFormation stacks `CREATE_COMPLETE`; web app reachable; user signed in with platform-admin.
- Glue source scanned, reviewed, approved; document source ingested; ontology accepted and visible in the graph.
- >= 90% of the questions in `TEST_QUESTIONS.md` answered correctly versus `expected_answers.json`, with Tier 1 (metrics), Tier 2 (structured) and Tier 3 (documents) each demonstrated.
- Environment torn down (or explicitly kept) and costs confirmed.
