#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.keyword_tags_sync import sync_keyword_tags

sync_keyword_tags()

from stacks import ApiStack, DataStack, FrontendStack, LambdaStack, MessagingStack, PipelineLambdaStack, StorageStack


app = cdk.App()

# Optional: pin account/region for lookups and consistent deploy targets.
# env = cdk.Environment(
#     account=os.getenv("CDK_DEFAULT_ACCOUNT"),
#     region=os.getenv("CDK_DEFAULT_REGION"),
# )

storage = StorageStack(app, "DocumentsStorage")
data = DataStack(app, "DataStack")
messaging = MessagingStack(app, "MessagingStack", documents_bucket_name=storage.bucket.bucket_name)

PipelineLambdaStack(
    app,
    "PipelineLambdaStack",
    documents_bucket=storage.bucket,
    extract_queue=messaging.extract_queue,
    process_queue=messaging.process_queue,
    analysis_queue=messaging.analysis_queue,
    storage_queue=messaging.storage_queue,
    results_table=data.results_table,
)
lambdas = LambdaStack(
    app,
    "LambdaStack",
    documents_bucket=storage.bucket,
    results_table=data.results_table,
)
api_stack = ApiStack(
    app,
    "Api",
    upload_function=lambdas.upload_function,
    query_function=lambdas.query_function,
)
FrontendStack(
    app,
    "Frontend",
    api_url=api_stack.http_api.api_endpoint,
)

app.synth()
