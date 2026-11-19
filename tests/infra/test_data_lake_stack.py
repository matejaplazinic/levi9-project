import re
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from infra.data_lake_stack import DATA_PREFIXES, DataLakeStack

FAKE_ACCOUNT = "111111111111"
ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_ID_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")


@pytest.fixture(scope="module")
def template() -> Template:
    app = cdk.App()
    stack = DataLakeStack(app, "TestDataLake", env=cdk.Environment(account=FAKE_ACCOUNT, region="eu-north-1"))
    return Template.from_stack(stack)


def test_data_prefixes():
    assert DATA_PREFIXES == ("bronze/", "silver/", "gold/")


def test_single_bucket_encrypted_with_s3_managed_keys(template):
    template.resource_count_is("AWS::S3::Bucket", 1)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [{"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            }
        },
    )


def test_public_access_fully_blocked_and_acls_disabled(template):
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
        },
    )


def test_bucket_policy_denies_non_tls_requests(template):
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Effect": "Deny",
                                "Action": "s3:*",
                                "Principal": {"AWS": "*"},
                                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                            }
                        )
                    ]
                )
            }
        },
    )


def test_bucket_is_deleted_with_its_objects_on_destroy(template):
    template.has_resource("AWS::S3::Bucket", {"DeletionPolicy": "Delete", "UpdateReplacePolicy": "Delete"})
    template.resource_count_is("Custom::S3AutoDeleteObjects", 1)


def test_bucket_name_is_exported_as_output(template):
    template.has_output("DataBucketName", {"Value": {"Ref": Match.any_value()}})


def test_infra_source_has_no_hardcoded_account_id():
    # The account must come from the AWS profile (CDK_DEFAULT_ACCOUNT), never from the code.
    files = [ROOT / "app.py", ROOT / "cdk.json", *sorted((ROOT / "infra").glob("*.py"))]
    offenders = [f.name for f in files if ACCOUNT_ID_RE.search(f.read_text(encoding="utf-8"))]
    assert offenders == []
