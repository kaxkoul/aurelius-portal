#!/usr/bin/env bash
#
# Deploy the vuln-demo CDK stack.
#
# Prerequisites:
#   - AWS credentials in environment / default profile
#   - Python 3.11+
#   - cdk CLI (npm install -g aws-cdk)
#   - Target region CDK-bootstrapped (cdk bootstrap aws://ACCT/REGION)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDK_DIR="$ROOT/infrastructure/cdk"
LAMBDA_DIR="$ROOT/lambda"
SHARED_DIR="$LAMBDA_DIR/shared"
FRONTEND_DIR="$ROOT/frontend"
BUILD_DIR="$ROOT/.build"
STACK="vuln-demo"

# Account comes straight from STS. Region is resolved from the same
# precedence the AWS CLI/CDK actually use, so bootstrap + deploy always
# target where the credentials point (avoids silently deploying to a
# hardcoded default region). Falls back to IMDS on EC2/CloudShell.
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

resolve_region() {
  # 1) AWS_REGION  2) AWS_DEFAULT_REGION  3) active profile config
  local r="${AWS_REGION:-${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || true)}}"
  # 4) instance/container metadata (EC2, CloudShell) via IMDSv2
  if [ -z "$r" ]; then
    local token
    token=$(curl -sS -m 2 -X PUT "http://169.254.169.254/latest/api/token" \
      -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || true)
    if [ -n "$token" ]; then
      r=$(curl -sS -m 2 -H "X-aws-ec2-metadata-token: $token" \
        "http://169.254.169.254/latest/meta-data/placement/region" 2>/dev/null || true)
    fi
  fi
  printf '%s' "$r"
}

REGION="$(resolve_region)"
if [ -z "$REGION" ]; then
  echo "ERROR: could not determine AWS region." >&2
  echo "  Set AWS_REGION, run 'aws configure set region <region>', or run from EC2/CloudShell." >&2
  exit 1
fi

echo "==> Account: $ACCOUNT"
echo "==> Region:  $REGION"

# 1. Pre-bundle Lambda assets ----------------------------------------
echo ""
echo "==> Pre-bundling Lambda assets at $BUILD_DIR"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
for fn in login orders comment config report; do
  out="$BUILD_DIR/$fn"
  mkdir -p "$out/shared"
  cp "$LAMBDA_DIR/$fn/"*.py "$out/"
  cp "$SHARED_DIR/"*.py "$out/shared/"
  echo "    built $out"
done

# 2. Python venv + CDK deps ------------------------------------------
echo ""
echo "==> Python venv + CDK deps"
if [ ! -d "$CDK_DIR/.venv" ]; then
  python3 -m venv "$CDK_DIR/.venv"
fi
# shellcheck disable=SC1091
source "$CDK_DIR/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$CDK_DIR/requirements.txt"

# 3. cdk bootstrap (scoped execution policy) --------------------------
# Bootstrap with the vuln-demo-cfn-exec managed policy instead of the
# default AdministratorAccess, so the CDKToolkit execution role is scoped
# to only the services this stack needs. Override the ARN via
# CDK_EXEC_POLICY_ARN if you named the policy differently.
echo ""
echo "==> cdk bootstrap $REGION (scoped execution policy)"
cd "$CDK_DIR"
export CDK_DEFAULT_ACCOUNT="$ACCOUNT"
export CDK_DEFAULT_REGION="$REGION"
EXEC_POLICY_ARN="${CDK_EXEC_POLICY_ARN:-arn:aws:iam::$ACCOUNT:policy/vuln-demo-cfn-exec}"
echo "    execution policy: $EXEC_POLICY_ARN"
cdk bootstrap "aws://$ACCOUNT/$REGION" \
  --cloudformation-execution-policies "$EXEC_POLICY_ARN"

# 4. cdk deploy -------------------------------------------------------
echo ""
echo "==> cdk deploy $STACK to $REGION"
cdk deploy "$STACK" \
  --require-approval never \
  --outputs-file ./outputs.json

# 5. Patch frontend with API URL --------------------------------------
echo ""
echo "==> Injecting API URL into frontend"
API_URL=$(python3 -c "import json; d=json.load(open('outputs.json')); print(d['$STACK']['ApiUrl'].rstrip('/'))")
FRONTEND_BUCKET=$(python3 -c "import json; d=json.load(open('outputs.json')); print(d['$STACK']['FrontendBucketName'])")
DIST_ID=$(python3 -c "import json; d=json.load(open('outputs.json')); print(d['$STACK']['DistributionId'])")
FRONTEND_URL=$(python3 -c "import json; d=json.load(open('outputs.json')); print(d['$STACK']['FrontendUrl'])")

# Replace `window.__API_BASE__ ||` line with a real assignment.
PATCHED="$BUILD_DIR/index.html"
python3 - "$FRONTEND_DIR/index.html" "$API_URL" "$PATCHED" <<'PY'
import sys
src, api, dst = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src) as f: html = f.read()
inject = f"<script>window.__API_BASE__ = {api!r};</script>"
patched = html.replace("</head>", inject + "\n</head>", 1)
with open(dst, "w") as f: f.write(patched)
PY

aws s3 cp "$PATCHED" "s3://$FRONTEND_BUCKET/index.html" \
  --region "$REGION" \
  --content-type 'text/html; charset=utf-8' \
  --cache-control 'no-cache' \
  --quiet

aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/*" \
  --query 'Invalidation.Id' --output text \
  --region "$REGION" >/dev/null

# 6. Done -------------------------------------------------------------
cat <<EOF

============================================================
  Deploy complete
============================================================
  Frontend URL:  $FRONTEND_URL
  API base URL:  $API_URL
  Test users:    alice / alice-pass-123
                 bob   / bob-pass-456

  CloudFront cache invalidation: in progress (~1-3 min)
  Tear down when done:           ./scripts/teardown.sh
============================================================
EOF
