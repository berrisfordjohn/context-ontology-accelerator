#!/usr/bin/env bash
# Tear down everything this test created: data, COA stacks, WAF ACL, config. Safe to re-run.
# Env: SCL_PREFIX (default coa)
set -u
export AWS_PAGER= AWS_REGION="${AWS_REGION:-eu-north-1}"
export AWS_DEFAULT_REGION=$AWS_REGION CDK_DEFAULT_REGION=$AWS_REGION
export SCL_PREFIX="${SCL_PREFIX:-coa}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${COA_REPO:-$(cd "$HERE/../../.." && pwd)}"
ACCT=$(aws sts get-caller-identity --query Account --output text)

# KEEP_CHEAP=1 removes only the stacks (the costly part) and keeps the data bucket, Glue DB, WAF ACL and
# config parameter, which cost almost nothing and make the next deploy faster.
KEEP_CHEAP="${KEEP_CHEAP:-0}"

# 1. Test data
if [ "$KEEP_CHEAP" != 1 ]; then
aws s3 rb "s3://coa-clinical-trials-$ACCT-$AWS_REGION" --force 2>/dev/null && echo "bucket removed"
aws glue delete-database --name clinical_trials 2>/dev/null && echo "glue db removed"
fi

# 2. COA stacks (destroy.sh looks up the us-east-1 edge-waf stack, which the SCP denies, so that lookup is patched out)
cd "$REPO"
grep -n "edge-waf" scripts/destroy.sh >/dev/null && echo "NOTE: if destroy.sh aborts on edge-waf, skip that stack in the working copy"
./scripts/destroy.sh dev || echo "destroy.sh reported errors; see remaining stacks below"

# 3. Hand-made WAF ACL
ID=""; [ "$KEEP_CHEAP" = 1 ] || ID=$(aws wafv2 list-web-acls --scope CLOUDFRONT --region us-east-1 --query "WebACLs[?Name=='$SCL_PREFIX-cf-acl'].Id" --output text 2>/dev/null)
if [ -n "$ID" ]; then
  LT=$(aws wafv2 get-web-acl --name "$SCL_PREFIX-cf-acl" --scope CLOUDFRONT --region us-east-1 --id "$ID" --query LockToken --output text)
  aws wafv2 delete-web-acl --name "$SCL_PREFIX-cf-acl" --scope CLOUDFRONT --region us-east-1 --id "$ID" --lock-token "$LT" && echo "waf removed"
fi

# 4. Config and leftovers
if [ "$KEEP_CHEAP" != 1 ]; then aws ssm delete-parameter --name "/$SCL_PREFIX/config" 2>/dev/null && echo "config param removed"; fi
echo "Remaining stacks (network DELETE_FAILED = AgentCore ENIs, released within ~8 h; re-run then):"
aws cloudformation list-stacks --query "StackSummaries[?starts_with(StackName,'$SCL_PREFIX-') && StackStatus!='DELETE_COMPLETE'].[StackName,StackStatus]" --output text
