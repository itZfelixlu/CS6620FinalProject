import aws_cdk as core
import aws_cdk.assertions as assertions

from stacks import ApiStack, DataStack, FrontendStack, LambdaStack, MessagingStack, PipelineLambdaStack, StorageStack


def test_storage_stack_has_bucket():
    app = core.App()
    stack = StorageStack(app, "DocumentsStorage")
    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::S3::Bucket", 1)


def test_messaging_stack_has_queues_and_notifications():
    app = core.App()
    storage = StorageStack(app, "DocumentsStorage")
    stack = MessagingStack(
        app,
        "Messaging",
        documents_bucket_name=storage.bucket.bucket_name,
    )
    template = assertions.Template.from_stack(stack)
    # Four main queues + four DLQs
    template.resource_count_is("AWS::SQS::Queue", 8)


def test_data_stack_has_results_table_and_gsi():
    app = core.App()
    stack = DataStack(app, "Data")
    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "GlobalSecondaryIndexes": assertions.Match.array_with(
                [
                    assertions.Match.object_like({"IndexName": "GSI1"}),
                    assertions.Match.object_like({"IndexName": "GSI2"}),
                ]
            )
        },
    )


def test_pipeline_lambda_stack_has_four_functions():
    app = core.App()
    storage = StorageStack(app, "DocumentsStorage")
    data = DataStack(app, "Data")
    messaging = MessagingStack(
        app,
        "Messaging",
        documents_bucket_name=storage.bucket.bucket_name,
    )
    stack = PipelineLambdaStack(
        app,
        "Pipeline",
        documents_bucket=storage.bucket,
        extract_queue=messaging.extract_queue,
        process_queue=messaging.process_queue,
        analysis_queue=messaging.analysis_queue,
        storage_queue=messaging.storage_queue,
        results_table=data.results_table,
    )
    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::Lambda::Function", 4)


def test_lambda_stack_has_upload_and_query_functions():
    app = core.App()
    storage = StorageStack(app, "DocumentsStorage")
    data = DataStack(app, "Data")
    stack = LambdaStack(
        app,
        "Lambda",
        documents_bucket=storage.bucket,
        results_table=data.results_table,
    )
    template = assertions.Template.from_stack(stack)
    template.resource_count_is("AWS::Lambda::Function", 2)


def test_frontend_stack_has_static_website_bucket():
    app = core.App()
    stack = FrontendStack(
        app,
        "Frontend",
        api_url="https://example.execute-api.us-east-1.amazonaws.com",
    )
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "WebsiteConfiguration": assertions.Match.object_like(
                {"IndexDocument": "index.html"}
            ),
        },
    )


def test_api_stack_has_http_api():
    app = core.App()
    storage = StorageStack(app, "DocumentsStorage")
    data = DataStack(app, "Data")
    lambdas = LambdaStack(
        app,
        "Lambda",
        documents_bucket=storage.bucket,
        results_table=data.results_table,
    )
    api = ApiStack(
        app,
        "Api",
        upload_function=lambdas.upload_function,
        query_function=lambdas.query_function,
    )
    template = assertions.Template.from_stack(api)
    template.resource_count_is("AWS::ApiGatewayV2::Api", 1)
