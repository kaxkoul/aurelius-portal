"""
vuln-demo CDK stack.

Resources:
  - 5 Lambda functions (login, orders, comment, config, report)
    each packaged with the shared/ helpers via a per-function asset.
  - REST API Gateway routing to those Lambdas.
  - S3 bucket holding the static frontend.
  - CloudFront distribution in front of S3.

Notes:
  - The Lambdas have minimal IAM (only basic execution).
  - The S3 bucket is private with OAC; CF reads it.
  - Stack outputs include the API base URL and the CloudFront domain.
"""
from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

# Path to the project root (where lambda/ and frontend/ live)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAMBDA_DIR = PROJECT_ROOT / "lambda"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
# scripts/deploy.sh pre-builds each function under .build/<fn>/ with
# the shared/ helpers copied alongside the function code, so CDK can
# package each one as a flat directory without needing Docker.
BUILD_DIR = PROJECT_ROOT / ".build"


class VulnDemoStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---------------- Frontend bucket + CloudFront ----------------
        # Private S3 bucket. Locked down with:
        #   - BLOCK_ALL public access (all four block flags)
        #   - public_read_access=False explicitly
        #   - BUCKET_OWNER_ENFORCED (disables ACLs entirely)
        #   - enforce_ssl=True (adds deny-non-TLS bucket policy)
        # CloudFront reads via OAC, which adds a tightly-scoped bucket
        # policy allowing only the specific distribution.
        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            public_read_access=False,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
        )

        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    frontend_bucket
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
            ),
            comment="vuln-demo frontend",
        )

        s3deploy.BucketDeployment(
            self,
            "FrontendDeployment",
            sources=[s3deploy.Source.asset(str(FRONTEND_DIR))],
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
            retain_on_delete=False,
        )

        # ---------------- Lambdas ----------------
        # Each Lambda is built from a per-function "build directory"
        # containing the function's lambda_function.py + the shared/
        # helpers copied alongside. We use cdk's bundling option.
        common_kwargs = dict(
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="lambda_function.lambda_handler",
            timeout=Duration.seconds(15),
            memory_size=256,
        )

        login_fn = self._make_lambda("LoginFn", "login", **common_kwargs)
        orders_fn = self._make_lambda("OrdersFn", "orders", **common_kwargs)
        comment_fn = self._make_lambda("CommentFn", "comment", **common_kwargs)
        config_fn = self._make_lambda("ConfigFn", "config", **common_kwargs)
        report_fn = self._make_lambda("ReportFn", "report", **common_kwargs)

        # ---------------- API Gateway ----------------
        api = apigw.RestApi(
            self,
            "VulnDemoApi",
            rest_api_name="vuln-demo-api",
            deploy_options=apigw.StageOptions(stage_name="prod"),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Authorization", "Content-Type"],
            ),
        )

        # POST /login
        api.root.add_resource("login").add_method(
            "POST", apigw.LambdaIntegration(login_fn, proxy=True)
        )

        # GET /orders/{id}
        orders_res = api.root.add_resource("orders").add_resource("{id}")
        orders_res.add_method("GET", apigw.LambdaIntegration(orders_fn, proxy=True))

        # GET, POST /comments
        comments_res = api.root.add_resource("comments")
        comments_res.add_method("GET", apigw.LambdaIntegration(comment_fn, proxy=True))
        comments_res.add_method("POST", apigw.LambdaIntegration(comment_fn, proxy=True))

        # GET /fetch
        api.root.add_resource("fetch").add_method(
            "GET", apigw.LambdaIntegration(config_fn, proxy=True)
        )

        # POST /report
        api.root.add_resource("report").add_method(
            "POST", apigw.LambdaIntegration(report_fn, proxy=True)
        )

        # ---------------- Outputs ----------------
        CfnOutput(self, "FrontendUrl", value=f"https://{distribution.distribution_domain_name}")
        CfnOutput(self, "FrontendBucketName", value=frontend_bucket.bucket_name)
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "DistributionId", value=distribution.distribution_id)

    # ------------------------------------------------------------------
    def _make_lambda(self, construct_id: str, fn_name: str, **kwargs) -> _lambda.Function:
        """Package a Lambda from the pre-built .build/<fn>/ directory.

        The deploy script (scripts/deploy.sh) pre-stages each function
        under .build/<fn>/ with the shared/ helpers copied alongside.
        """
        prebuilt = BUILD_DIR / fn_name
        if not prebuilt.is_dir():
            raise RuntimeError(
                f"Prebuilt Lambda dir missing: {prebuilt}. "
                f"Run scripts/deploy.sh which prebuilds Lambda assets."
            )
        return _lambda.Function(
            self,
            construct_id,
            code=_lambda.Code.from_asset(str(prebuilt)),
            **kwargs,
        )
