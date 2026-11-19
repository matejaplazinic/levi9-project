"""CDK app entry point: `cdk synth|deploy|destroy --profile mateja`."""

import os

import aws_cdk as cdk

from infra.data_lake_stack import DataLakeStack

REGION = "eu-north-1"

app = cdk.App()
DataLakeStack(
    app,
    "DataLakeStack",
    # The account comes from the AWS profile used by the CDK CLI; it is never written in code.
    env=cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region=REGION),
)
app.synth()
