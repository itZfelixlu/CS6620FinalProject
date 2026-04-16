from aws_cdk import Duration, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class LambdaStack(Stack):
    """API-facing Lambdas: upload presign + query reads."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        documents_bucket: s3.IBucket,
        results_table: dynamodb.ITable,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.upload_function = lambda_.Function(
            self,
            "UploadFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="upload_lambda.lambda_handler",
            code=lambda_.Code.from_asset("lambda/upload"),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "DOCUMENTS_BUCKET_NAME": documents_bucket.bucket_name,
                "PRESIGN_EXPIRES_SECONDS": "900",
                "MAX_UPLOAD_BYTES": str(50 * 1024 * 1024),
            },
        )
        documents_bucket.grant_put(self.upload_function)

        self.query_function = lambda_.Function(
            self,
            "QueryFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="query_lambda.lambda_handler",
            code=lambda_.Code.from_asset("lambda/query"),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "RESULTS_TABLE_NAME": results_table.table_name,
                "DOCUMENTS_BUCKET_NAME": documents_bucket.bucket_name,
                "TENANT_ID": "default",
                "DEFAULT_PAGE_LIMIT": "25",
                "CACHE_TTL_SECONDS": "120",
                "CACHE_ENABLED": "1",
            },
        )
        results_table.grant_read_write_data(self.query_function)
        documents_bucket.grant_delete(self.query_function)
