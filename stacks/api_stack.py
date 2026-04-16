from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_lambda as lambda_,
)
from constructs import Construct


class ApiStack(Stack):
    """HTTP API Gateway routes wired to Lambda integrations."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        upload_function: lambda_.IFunction,
        query_function: lambda_.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name="document-intelligence-api",
            description="Upload, query, and health routes",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.DELETE,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["content-type", "authorization"],
                max_age=Duration.days(1),
            ),
        )

        upload_integration = apigwv2_integrations.HttpLambdaIntegration(
            "UploadIntegration",
            upload_function,
        )
        query_integration = apigwv2_integrations.HttpLambdaIntegration(
            "QueryIntegration",
            query_function,
        )

        http_api.add_routes(
            path="/upload",
            methods=[apigwv2.HttpMethod.POST],
            integration=upload_integration,
        )
        http_api.add_routes(
            path="/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=upload_integration,
        )
        http_api.add_routes(
            path="/results/{document_id}",
            methods=[apigwv2.HttpMethod.GET, apigwv2.HttpMethod.DELETE],
            integration=query_integration,
        )
        http_api.add_routes(
            path="/results",
            methods=[apigwv2.HttpMethod.GET],
            integration=query_integration,
        )

        self.http_api = http_api

        CfnOutput(
            self,
            "ApiUrl",
            value=http_api.api_endpoint,
            description="POST /upload, GET /health, GET /results, GET /results/{id}",
        )
