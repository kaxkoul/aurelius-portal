#!/usr/bin/env bash
#
# Tear down the vuln-demo CDK stack and clean up local build artifacts.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDK_DIR="$ROOT/infrastructure/cdk"
REGION="${AWS_REGION:-us-west-2}"
STACK="vuln-demo"

echo "==> cdk destroy $STACK in $REGION"
cd "$CDK_DIR"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION="$REGION"
cdk destroy "$STACK" --force

# Local cleanup
rm -rf "$ROOT/.build"
rm -f "$CDK_DIR/outputs.json"
rm -rf "$CDK_DIR/cdk.out"

echo ""
echo "==> Done."
