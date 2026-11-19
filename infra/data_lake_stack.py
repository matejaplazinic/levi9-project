"""CDK stack with the project's data lake bucket.

Data is stored under the bronze/, silver/ and gold/ prefixes of a single bucket. S3 has no real
folders, so the prefixes are a naming convention and appear once the first object is written.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from constructs import Construct

DATA_PREFIXES = ("bronze/", "silver/", "gold/")


class DataLakeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

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

        CfnOutput(self, "DataBucketName", value=self.bucket.bucket_name, description="Data lake bucket name")
