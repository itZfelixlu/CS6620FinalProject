from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_sqs as sqs
from constructs import Construct


def _queue_pair(
    scope: Construct,
    *,
    base_id: str,
    visibility_timeout: Duration,
) -> tuple[sqs.Queue, sqs.Queue]:
    dlq = sqs.Queue(
        scope,
        f"{base_id}Dlq",
        retention_period=Duration.days(14),
        enforce_ssl=True,
    )
    q = sqs.Queue(
        scope,
        f"{base_id}Queue",
        visibility_timeout=visibility_timeout,
        retention_period=Duration.days(4),
        enforce_ssl=True,
        dead_letter_queue=sqs.DeadLetterQueue(queue=dlq, max_receive_count=5),
    )
    return dlq, q


class MessagingStack(Stack):
    """
    Pipeline queues: extract -> process -> analysis -> storage.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        documents_bucket_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vis = Duration.seconds(300)

        _, self.extract_queue = _queue_pair(self, base_id="Extract", visibility_timeout=vis)
        _, self.process_queue = _queue_pair(self, base_id="Process", visibility_timeout=vis)
        _, self.analysis_queue = _queue_pair(self, base_id="Analysis", visibility_timeout=vis)
        _, self.storage_queue = _queue_pair(self, base_id="Storage", visibility_timeout=vis)

        # S3 -> EventBridge -> ExtractQueue avoids cross-stack S3/SQS policy cycles.
        events.Rule(
            self,
            "UploadsObjectCreatedRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [documents_bucket_name]},
                    "object": {"key": [{"prefix": "uploads/"}]},
                },
            ),
            targets=[targets.SqsQueue(self.extract_queue)],
        )
