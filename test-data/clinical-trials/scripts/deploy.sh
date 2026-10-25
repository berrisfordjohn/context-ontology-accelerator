#!/usr/bin/env bash
# One-command deploy of COA (run inside WSL2/Linux; the repo is the checkout containing test-data/).
# Env: COA_ADMIN_EMAIL (required), SCL_PREFIX (default coa), COA_MODEL (default eu.anthropic.claude-sonnet-4-6)
set -eu
export AWS_PAGER= AWS_REGION="${AWS_REGION:-eu-north-1}"
export AWS_DEFAULT_REGION=$AWS_REGION CDK_DEFAULT_REGION=$AWS_REGION
export SCL_PREFIX="${SCL_PREFIX:-coa}"
: "${COA_ADMIN_EMAIL:?set COA_ADMIN_EMAIL}"
MODEL="${COA_MODEL:-eu.anthropic.claude-sonnet-4-6}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# COA_REPO: a Linux-native clone (a Windows checkout has CRLF scripts that fail under WSL)
REPO="${COA_REPO:-$(cd "$HERE/../../.." && pwd)}"

"$HERE/preflight.sh"

# assumed-role ARN -> IAM role ARN
ARN=$(aws sts get-caller-identity --query Arn --output text)
ROLE_NAME=$(echo "$ARN" | sed -E 's#.*:assumed-role/([^/]+)/[^/]+$#\1#')
export SCL_SMUS_ADMIN_ARNS=$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)
export SCL_LAMBDA_RESERVED_CONCURRENCY=0

# One model for LLM, induction and chat
cat > /tmp/coa-config.json <<EOF
{"initialAdminEmail":"$COA_ADMIN_EMAIL","bedrockLlmModelId":"$MODEL","bedrockEmbedModelId":"eu.cohere.embed-v4:0","bedrockEmbedDimensions":1024,"bedrockInductionLlmModelId":"$MODEL","bedrockChatModelId":"$MODEL"}
EOF
aws ssm put-parameter --name "/$SCL_PREFIX/config" --type String --overwrite --value file:///tmp/coa-config.json >/dev/null
rm -f /tmp/coa-config.json

# The SCP denies CloudFormation in us-east-1, so the CloudFront WAF ACL is created by hand and passed in
# (or skipped when WAF is denied). These patches go on the working copy only and are not committed.
cd "$REPO"
mkdir -p ~/.docker; echo '{}' > ~/.docker/config.json
grep -q cloudfront_web_acl_id scripts/deploy.sh || \
  sed -i '49a [ -n "${CF_ACL:-}" ] \&\& CONTEXT+=(--context "cloudfront_web_acl_id=$CF_ACL")' scripts/deploy.sh
grep -q COA_SKIP_EDGE_WAF infra/bin/app.ts || \
  sed -i 's|if (!cloudfrontWebAclId \&\& deployAccount) {|if (!cloudfrontWebAclId \&\& deployAccount \&\& !process.env.COA_SKIP_EDGE_WAF) {|' infra/bin/app.ts
sed -i 's|\[ "\$REGION" != "us-east-1" \] && _bootstrap_regions="\$REGION us-east-1"|:|' scripts/preflight-deploy.sh
CF_ACL=$(aws wafv2 list-web-acls --scope CLOUDFRONT --region us-east-1 --query "WebACLs[?Name=='$SCL_PREFIX-cf-acl'].ARN" --output text 2>/dev/null)
[ -n "$CF_ACL" ] || CF_ACL=$(aws wafv2 create-web-acl --name "$SCL_PREFIX-cf-acl" --scope CLOUDFRONT --region us-east-1 --default-action '{"Allow":{}}' \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=coaCf --query Summary.ARN --output text 2>/dev/null) || CF_ACL=""
if [ -n "$CF_ACL" ]; then export CF_ACL; else export COA_SKIP_EDGE_WAF=1; fi

echo "Deploying prefix=$SCL_PREFIX model=$MODEL waf=${CF_ACL:-none} (about 60 min; arm64 images build under emulation on x86)"
./scripts/deploy.sh dev
echo "DEPLOY COMPLETE"
aws cloudformation describe-stacks --stack-name "$SCL_PREFIX-dev-web" --query "Stacks[0].Outputs" --output table || true
