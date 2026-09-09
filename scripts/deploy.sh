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
REGION="${AWS_REGION:-us-west-2}"
STACK="vuln-demo"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
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

# 3. cdk deploy -------------------------------------------------------
echo ""
echo "==> cdk deploy $STACK to $REGION"
cd "$CDK_DIR"
export CDK_DEFAULT_ACCOUNT="$ACCOUNT"
export CDK_DEFAULT_REGION="$REGION"
cdk deploy "$STACK" \
  --require-approval never \
  --outputs-file ./outputs.json

# 4. Patch frontend with API URL --------------------------------------
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

# 5. Done -------------------------------------------------------------
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
