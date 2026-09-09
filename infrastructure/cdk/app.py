#!/usr/bin/env python3
"""CDK entry point for the vuln-demo stack."""
import os

import aws_cdk as cdk

from vuln_demo_stack import VulnDemoStack

app = cdk.App()

# Resolve account + region from the standard CDK env vars, with sensible
# defaults aligned to the demo's target region.
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-west-2"),
)

VulnDemoStack(
    app,
    "vuln-demo",
    env=env,
    description="AWS Security Agent demo target — DELIBERATELY VULNERABLE.",
)

app.synth()
