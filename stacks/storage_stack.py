from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_s3 as s3
from constructs import Construct


class StorageStack(Stack):
    """Data plane: raw document objects (S3)."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self,
            "DocumentsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=False,
            event_bridge_enabled=True,
        )
        self.bucket.add_cors_rule(
            allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.GET, s3.HttpMethods.HEAD],
            allowed_origins=["*"],
            allowed_headers=["*"],
            exposed_headers=["ETag"],
            max_age=3000,
        )

        CfnOutput(
            self,
            "DocumentsBucketName",
            value=self.bucket.bucket_name,
            description="Raw uploads land under uploads/",
        )
