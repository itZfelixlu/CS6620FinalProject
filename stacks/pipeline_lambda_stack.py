from aws_cdk import BundlingOptions, DockerImage, Duration, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_sources
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct

class PipelineLambdaStack(Stack):
    """Extract → process → analysis → storage Lambdas, each triggered by its SQS queue.

    Keyword list: edit ``config/keyword_tags.json`` (``app.py`` copies it into ``lambda/analysis/`` at synth).

    Extract Lambda: ``pypdf`` is installed via CDK **Docker bundling** (SAM build image). Start Docker
    Desktop, then ``cdk synth`` / ``cdk deploy``.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        documents_bucket: s3.IBucket,
        extract_queue: sqs.IQueue,
        process_queue: sqs.IQueue,
        analysis_queue: sqs.IQueue,
        storage_queue: sqs.IQueue,
        results_table: dynamodb.ITable,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        extract_code = lambda_.Code.from_asset(
            "lambda/extract",
            bundling=BundlingOptions(
                image=DockerImage.from_registry("public.ecr.aws/sam/build-python3.12"),
                command=[
                    "bash",
                    "-c",
                    "pip install --no-cache-dir -r /asset-input/requirements.txt -t /asset-output && "
                    "cp /asset-input/extract_lambda.py /asset-output/",
                ],
            ),
        )

        extract_fn = lambda_.Function(
            self,
            "ExtractFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="extract_lambda.lambda_handler",
            code=extract_code,
            timeout=Duration.seconds(120),
            memory_size=512,
            environment={
                "PROCESS_QUEUE_URL": process_queue.queue_url,
                "MAX_EXTRACTED_CHARS": "80000",
            },
        )
        extract_queue.grant_consume_messages(extract_fn)
        process_queue.grant_send_messages(extract_fn)
        documents_bucket.grant_read(extract_fn)
        extract_fn.add_event_source(lambda_sources.SqsEventSource(extract_queue, batch_size=5))

        process_fn = lambda_.Function(
            self,
            "ProcessFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="process_lambda.lambda_handler",
            code=lambda_.Code.from_asset("lambda/process"),
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={"ANALYSIS_QUEUE_URL": analysis_queue.queue_url},
        )
        process_queue.grant_consume_messages(process_fn)
        analysis_queue.grant_send_messages(process_fn)
        process_fn.add_event_source(lambda_sources.SqsEventSource(process_queue, batch_size=5))

        analysis_fn = lambda_.Function(
            self,
            "AnalysisFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="analysis_lambda.lambda_handler",
            code=lambda_.Code.from_asset("lambda/analysis"),
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "STORAGE_QUEUE_URL": storage_queue.queue_url,
            },
        )
        analysis_queue.grant_consume_messages(analysis_fn)
        storage_queue.grant_send_messages(analysis_fn)
        analysis_fn.add_event_source(lambda_sources.SqsEventSource(analysis_queue, batch_size=5))

        storage_fn = lambda_.Function(
            self,
            "StorageFn",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="storage_lambda.lambda_handler",
            code=lambda_.Code.from_asset("lambda/storage"),
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                "PIPELINE_STAGE": "storage",
                "RESULTS_TABLE_NAME": results_table.table_name,
                "TENANT_ID": "default",
            },
        )
        storage_queue.grant_consume_messages(storage_fn)
        results_table.grant_write_data(storage_fn)
        storage_fn.add_event_source(lambda_sources.SqsEventSource(storage_queue, batch_size=5))
