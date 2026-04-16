from aws_cdk import CfnOutput, Fn, RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


class FrontendStack(Stack):
    """Public S3 static website for the frontend; injects config.json with API base URL."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket = s3.Bucket(
            self,
            "WebsiteBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False,
            ),
            website_index_document="index.html",
        )

        config_body = Fn.sub('{"apiBaseUrl":"${ApiUrl}"}', {"ApiUrl": api_url})

        s3deploy.BucketDeployment(
            self,
            "DeployFrontend",
            sources=[
                s3deploy.Source.asset(
                    "frontend",
                    exclude=["config.json", "config.example.json"],
                ),
                s3deploy.Source.data("config.json", config_body),
            ],
            destination_bucket=bucket,
            prune=True,
        )

        website_url = Fn.join("", ["http://", bucket.bucket_website_domain_name])

        CfnOutput(
            self,
            "WebsiteUrl",
            value=website_url,
            description="Open in browser (HTTP API URL is baked into config.json)",
        )
