"""CDK stack with the project's data lake bucket and the Lambda that fills its bronze/ layer.

Data is stored under the bronze/, silver/ and gold/ prefixes of a single bucket. S3 has no real
folders, so the prefixes are a naming convention and appear once the first object is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

DATA_PREFIXES = ("bronze/", "silver/", "gold/")
BRONZE_PREFIX = DATA_PREFIXES[0]
LAMBDA_ROOT = Path(__file__).resolve().parents[1] / "lambdas"


@dataclass(frozen=True)
class BronzeCopyConfig:
    """What the bronze copy Lambda copies. Values come from the `bronze_copy` context in cdk.json."""

    source_bucket: str
    station_id: str
    city_name: str
    source_folders: tuple[str, ...]

    @classmethod
    def from_context(cls, ctx: dict) -> BronzeCopyConfig:
        return cls(
            source_bucket=ctx["source_bucket"],
            station_id=str(ctx["station_id"]),
            city_name=ctx["city_name"],
            source_folders=tuple(ctx["source_folders"]),
        )


class DataLakeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, bronze_copy: BronzeCopyConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Construct ID "DataBucket" must never change: a new ID replaces the bucket and deletes its data.
        self.bucket = s3.Bucket(
            self,
            "DataBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        self.bronze_copy = self._bronze_copy_function(bronze_copy)

        CfnOutput(self, "DataBucketName", value=self.bucket.bucket_name, description="Data lake bucket name")
        CfnOutput(
            self,
            "BronzeCopyFunctionName",
            value=self.bronze_copy.function_name,
            description="Run manually with `aws lambda invoke` to copy source files into bronze/",
        )

    def _bronze_copy_function(self, config: BronzeCopyConfig) -> lambda_.Function:
        log_group = logs.LogGroup(
            self,
            "BronzeCopyLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        # No trigger on purpose: the function runs only when invoked by hand, so it can never loop on its own writes.
        fn = lambda_.Function(
            self,
            "BronzeCopyFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(LAMBDA_ROOT / "bronze_copy"), exclude=["__pycache__"]),
            memory_size=256,
            timeout=Duration.minutes(5),
            log_group=log_group,
            environment={
                "SOURCE_BUCKET": config.source_bucket,
                "TARGET_BUCKET": self.bucket.bucket_name,
                "STATION_ID": config.station_id,
                "CITY_NAME": config.city_name,
                "SOURCE_FOLDERS": ",".join(config.source_folders),
            },
        )

        source_arn = f"arn:{self.partition}:s3:::{config.source_bucket}"
        source_prefixes = [f"{folder}/*" for folder in config.source_folders]
        # Source bucket: read-only, and only the configured folders.
        fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="ListSourceFolders",
                actions=["s3:ListBucket"],
                resources=[source_arn],
                conditions={"StringLike": {"s3:prefix": source_prefixes}},
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="ReadSourceFiles",
                actions=["s3:GetObject"],
                resources=[f"{source_arn}/{prefix}" for prefix in source_prefixes],
            )
        )
        # Our bucket: list and write only under bronze/. No delete, no read of other layers.
        fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="ListBronze",
                actions=["s3:ListBucket"],
                resources=[self.bucket.bucket_arn],
                conditions={"StringLike": {"s3:prefix": [f"{BRONZE_PREFIX}*"]}},
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="WriteBronze",
                actions=["s3:PutObject"],
                resources=[self.bucket.arn_for_objects(f"{BRONZE_PREFIX}*")],
            )
        )
        return fn
