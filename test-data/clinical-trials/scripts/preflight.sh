#!/usr/bin/env bash
# Cheap, fail-fast checks for everything that stopped earlier deployments.
# Probes create and immediately delete tiny free resources. Bedrock probes use ~10 tokens per model.
# Usage: scripts/preflight.sh            (exit 0 = safe to deploy, 1 = blocked)
set -u
export AWS_PAGER=
R="${AWS_REGION:-eu-north-1}"
PREFIX="${SCL_PREFIX:-coa}"
MODEL="${COA_MODEL:-eu.anthropic.claude-sonnet-4-6}"
EMBED="${COA_EMBED:-eu.cohere.embed-v4:0}"
fail=0
ok()  { echo "  OK:   $*"; }
bad() { echo "  FAIL: $*"; fail=1; }

echo "== Preflight ($R, prefix $PREFIX) =="

# 1. Credentials
ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
  && ok "credentials, account $ACCT" || { bad "no AWS credentials (run 'aws login')"; exit 1; }

# 2. Account plan and credit (a spend limit or exhausted credit pauses the account)
PLAN=$(aws freetier get-account-plan-state --region us-east-1 --query '[accountPlanType,accountPlanStatus,accountPlanRemainingCredits.amount]' --output text 2>/dev/null)
echo "  INFO: plan/status/credit = $PLAN"
case "$PLAN" in PAID*ACTIVE*) ok "paid plan active";; *) bad "plan is not PAID/ACTIVE: $PLAN";; esac

# 3. Local tools
for t in docker node pnpm java; do command -v $t >/dev/null && ok "$t present" || bad "$t missing"; done
docker info >/dev/null 2>&1 && ok "docker daemon running" || bad "docker daemon not running (start Docker Desktop)"

# 4. SCP probes: actions the stacks need. A denial means the org policy blocks the deploy.
UP=$(aws cognito-idp create-user-pool --pool-name coa-preflight --region "$R" --query UserPool.Id --output text 2>&1)
if [[ "$UP" == ${R}_* ]]; then aws cognito-idp delete-user-pool --user-pool-id "$UP" --region "$R"; ok "cognito-idp:CreateUserPool"; else bad "Cognito CreateUserPool: ${UP:0:160}"; fi
EIP=$(aws ec2 allocate-address --region "$R" --query AllocationId --output text 2>&1)
if [[ "$EIP" == eipalloc-* ]]; then aws ec2 release-address --region "$R" --allocation-id "$EIP"; ok "ec2:AllocateAddress"; else bad "EIP allocate: ${EIP:0:160}"; fi
# ec2:CreateNatGateway is denied by a resource-level SCP that only a real call reveals; the network stack is deployed first so it fails fast.
WAF=$(aws wafv2 create-web-acl --name coa-preflight --scope CLOUDFRONT --region us-east-1 --default-action '{"Allow":{}}' \
  --visibility-config SampledRequestsEnabled=false,CloudWatchMetricsEnabled=false,MetricName=coaPre --query 'Summary.[Id,LockToken]' --output text 2>&1)
if [[ "$WAF" =~ ^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}[[:space:]]+[0-9a-f]{8}- ]]; then
  set -- $WAF; aws wafv2 delete-web-acl --name coa-preflight --scope CLOUDFRONT --region us-east-1 --id "$1" --lock-token "$2"
  ok "wafv2 CloudFront ACL (deploy.sh creates the real one)"
else echo "  WARN: WAF denied in us-east-1, CloudFront will have no WAF: ${WAF:0:120}"; fi

# 5. Bedrock: real invocations, since a model being listed does not mean it is usable
OUT=$(aws bedrock-runtime converse --region "$R" --model-id "$MODEL" --messages '[{"role":"user","content":[{"text":"hi"}]}]' \
  --inference-config maxTokens=5 --query 'usage.totalTokens' --output text 2>&1)
[[ "$OUT" =~ ^[0-9]+$ ]] && ok "bedrock $MODEL" || bad "bedrock $MODEL: ${OUT:0:160}"
echo '{"texts":["hi"],"input_type":"search_document","embedding_types":["float"]}' > /tmp/emb.json
aws bedrock-runtime invoke-model --region "$R" --model-id "$EMBED" --body fileb:///tmp/emb.json --content-type application/json /tmp/emb.out >/dev/null 2>/tmp/emb.err \
  && ok "bedrock $EMBED" || bad "bedrock $EMBED: $(head -c 160 /tmp/emb.err)"
rm -f /tmp/emb.*

# 6. Stale stacks that block a fresh deploy
for s in $(aws cloudformation list-stacks --region "$R" --query "StackSummaries[?starts_with(StackName,'${PREFIX}-') && (StackStatus=='DELETE_FAILED'||StackStatus=='ROLLBACK_COMPLETE'||StackStatus=='ROLLBACK_FAILED')].StackName" --output text); do
  bad "stale stack $s (delete it, or use another SCL_PREFIX)"
done

# 7. VPC headroom and CDK bootstrap
V=$(aws ec2 describe-vpcs --region "$R" --query 'length(Vpcs)' --output text); [ "$V" -lt 5 ] && ok "VPCs $V/5" || bad "VPC limit reached ($V/5)"
aws cloudformation describe-stacks --region "$R" --stack-name CDKToolkit >/dev/null 2>&1 && ok "CDK bootstrapped" || bad "run 'cdk bootstrap aws://$ACCT/$R'"

[ $fail -eq 0 ] && echo "PREFLIGHT PASSED" || echo "PREFLIGHT FAILED - not deploying"
exit $fail
