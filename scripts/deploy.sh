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

# 3. Ensure scoped CFN execution policy exists -----------------------
# The CDKToolkit execution role is bootstrapped with the vuln-demo-cfn-exec
# managed policy instead of the default AdministratorAccess, so it is scoped
# to only the services this stack needs. That policy must exist BEFORE
# bootstrap references it, so create it here (idempotent) if missing.
# Override the ARN via CDK_EXEC_POLICY_ARN if you named it differently.
export CDK_DEFAULT_ACCOUNT="$ACCOUNT"
export CDK_DEFAULT_REGION="$REGION"
EXEC_POLICY_ARN="${CDK_EXEC_POLICY_ARN:-arn:aws:iam::$ACCOUNT:policy/vuln-demo-cfn-exec}"

echo ""
echo "==> Ensuring CFN execution policy exists: $EXEC_POLICY_ARN"
if aws iam get-policy --policy-arn "$EXEC_POLICY_ARN" >/dev/null 2>&1; then
  echo "    already exists"
else
  echo "    not found - creating vuln-demo-cfn-exec"
  POLICY_DOC="$(mktemp -t vuln-demo-cfn-exec.XXXXXX.json)"
  trap 'rm -f "$POLICY_DOC"' EXIT
  cat > "$POLICY_DOC" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFormation",
      "Effect": "Allow",
      "Action": [
        "cloudformation:CreateStack",
        "cloudformation:UpdateStack",
        "cloudformation:DeleteStack",
        "cloudformation:CreateChangeSet",
        "cloudformation:DeleteChangeSet",
        "cloudformation:ExecuteChangeSet",
        "cloudformation:DescribeChangeSet",
        "cloudformation:DescribeStacks",
        "cloudformation:DescribeStackEvents",
        "cloudformation:DescribeStackResources",
        "cloudformation:GetTemplate",
        "cloudformation:GetTemplateSummary",
        "cloudformation:ListStacks",
        "cloudformation:ListStackResources",
        "cloudformation:ValidateTemplate",
        "cloudformation:TagResource",
        "cloudformation:UntagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:DeleteBucket",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:GetBucketPolicy",
        "s3:PutBucketPolicy",
        "s3:DeleteBucketPolicy",
        "s3:PutBucketPublicAccessBlock",
        "s3:GetBucketPublicAccessBlock",
        "s3:PutEncryptionConfiguration",
        "s3:GetEncryptionConfiguration",
        "s3:PutBucketOwnershipControls",
        "s3:GetBucketOwnershipControls",
        "s3:PutBucketVersioning",
        "s3:GetBucketVersioning",
        "s3:PutBucketTagging",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucketVersions",
        "s3:DeleteObjectVersion"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Lambda",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:DeleteFunction",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration",
        "lambda:ListFunctions",
        "lambda:AddPermission",
        "lambda:RemovePermission",
        "lambda:InvokeFunction",
        "lambda:TagResource",
        "lambda:UntagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ApiGateway",
      "Effect": "Allow",
      "Action": [
        "apigateway:GET",
        "apigateway:POST",
        "apigateway:PUT",
        "apigateway:PATCH",
        "apigateway:DELETE"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudFront",
      "Effect": "Allow",
      "Action": [
        "cloudfront:CreateDistribution",
        "cloudfront:UpdateDistribution",
        "cloudfront:DeleteDistribution",
        "cloudfront:GetDistribution",
        "cloudfront:GetDistributionConfig",
        "cloudfront:ListDistributions",
        "cloudfront:TagResource",
        "cloudfront:UntagResource",
        "cloudfront:CreateInvalidation",
        "cloudfront:GetInvalidation",
        "cloudfront:CreateOriginAccessControl",
        "cloudfront:UpdateOriginAccessControl",
        "cloudfront:DeleteOriginAccessControl",
        "cloudfront:GetOriginAccessControl"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Logs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:DeleteLogGroup",
        "logs:DescribeLogGroups",
        "logs:PutRetentionPolicy",
        "logs:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ManageDemoRoles",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRolePolicy",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
        "iam:TagRole",
        "iam:UntagRole"
      ],
      "Resource": "arn:aws:iam::*:role/vuln-demo-*"
    },
    {
      "Sid": "PassDemoRoles",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/vuln-demo-*",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": [
            "lambda.amazonaws.com"
          ]
        }
      }
    }
  ]
}
JSON
  aws iam create-policy \
    --policy-name vuln-demo-cfn-exec \
    --policy-document "file://$POLICY_DOC" \
    --query 'Policy.Arn' --output text >/dev/null
  echo "    created"
fi

# 4. cdk bootstrap (scoped execution policy) --------------------------
echo ""
echo "==> cdk bootstrap $REGION (scoped execution policy)"
cd "$CDK_DIR"
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
