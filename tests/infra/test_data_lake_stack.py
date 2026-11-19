import json
import re
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from infra.data_lake_stack import DATA_PREFIXES, BronzeCopyConfig, DataLakeStack

FAKE_ACCOUNT = "111111111111"
ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_ID_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
CONTEXT = json.loads((ROOT / "cdk.json").read_text(encoding="utf-8"))["context"]["bronze_copy"]


@pytest.fixture(scope="module")
def template() -> Template:
    app = cdk.App()
    stack = DataLakeStack(
        app,
        "TestDataLake",
        bronze_copy=BronzeCopyConfig.from_context(CONTEXT),
        env=cdk.Environment(account=FAKE_ACCOUNT, region="eu-north-1"),
    )
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


def test_stack_grants_no_extra_roles_or_functions(template):
    # Auto-delete provider + bronze copy Lambda; anything more is a new permission to review.
    template.resource_count_is("AWS::IAM::Role", 2)
    template.resource_count_is("AWS::Lambda::Function", 2)
    template.resource_count_is("AWS::S3::BucketPolicy", 1)
    template.resource_count_is("AWS::IAM::Policy", 1)


def test_bucket_name_is_exported_as_output(template):
    template.has_output("DataBucketName", {"Value": {"Ref": Match.any_value()}})


def test_infra_source_has_no_hardcoded_account_id():
    # The account must come from the AWS profile (CDK_DEFAULT_ACCOUNT), never from the code.
    files = [ROOT / "app.py", ROOT / "cdk.json", *sorted((ROOT / "infra").glob("*.py"))]
    offenders = [f.name for f in files if ACCOUNT_ID_RE.search(f.read_text(encoding="utf-8"))]
    assert offenders == []


SOURCE_ARN = "arn:${AWS::Partition}:s3:::levi9-praksa-2026-data"


def _bronze_copy_function(template):
    functions = template.find_resources("AWS::Lambda::Function", {"Properties": {"Handler": "handler.handler"}})
    assert len(functions) == 1
    return next(iter(functions.values()))["Properties"]


def _bronze_copy_statements(template):
    policies = template.find_resources("AWS::IAM::Policy")
    assert len(policies) == 1
    return next(iter(policies.values()))["Properties"]["PolicyDocument"]["Statement"]


def _resolve(value):
    # Fn::Join of the partition and a bucket ARN, rendered as text for easy assertions.
    if isinstance(value, dict) and "Fn::Join" in value:
        return "".join(_resolve(v) for v in value["Fn::Join"][1])
    if isinstance(value, dict) and "Ref" in value:
        return "${" + value["Ref"] + "}"
    if isinstance(value, dict) and "Fn::GetAtt" in value:
        return "${" + ".".join(value["Fn::GetAtt"]) + "}"
    return value


def test_bronze_copy_function_settings(template):
    props = _bronze_copy_function(template)
    assert props["Runtime"] == "python3.13"
    assert props["MemorySize"] == 256
    assert props["Timeout"] == 300


def test_bronze_copy_config_comes_from_cdk_json_context(template):
    env = _bronze_copy_function(template)["Environment"]["Variables"]
    assert env["SOURCE_BUCKET"] == CONTEXT["source_bucket"]
    assert env["STATION_ID"] == CONTEXT["station_id"]
    assert env["CITY_NAME"] == CONTEXT["city_name"]
    assert env["SOURCE_FOLDERS"] == ",".join(CONTEXT["source_folders"])
    # Same logical ID as before DP-4, so the bucket is not replaced.
    assert env["TARGET_BUCKET"] == {"Ref": "DataBucketE3889A50"}


def test_infra_source_has_no_hardcoded_city_or_station():
    files = [ROOT / "app.py", *sorted((ROOT / "infra").glob("*.py"))]
    offenders = [f.name for f in files if re.search(r"35120|Novi Sad|levi9-praksa", f.read_text(encoding="utf-8"))]
    assert offenders == []


def test_bronze_copy_permissions_are_least_privilege(template):
    statements = {s["Sid"]: s for s in _bronze_copy_statements(template)}
    assert set(statements) == {"ListSourceFolders", "ReadSourceFiles", "ListBronze", "WriteBronze"}
    assert all(s["Effect"] == "Allow" for s in statements.values())

    list_source = statements["ListSourceFolders"]
    assert list_source["Action"] == "s3:ListBucket"
    assert _resolve(list_source["Resource"]) == SOURCE_ARN
    assert list_source["Condition"] == {"StringLike": {"s3:prefix": ["pollution/*", "weather/*"]}}

    read_source = statements["ReadSourceFiles"]
    assert read_source["Action"] == "s3:GetObject"
    assert [_resolve(r) for r in read_source["Resource"]] == [f"{SOURCE_ARN}/pollution/*", f"{SOURCE_ARN}/weather/*"]

    list_bronze = statements["ListBronze"]
    assert list_bronze["Action"] == "s3:ListBucket"
    assert list_bronze["Condition"] == {"StringLike": {"s3:prefix": ["bronze/*"]}}

    write_bronze = statements["WriteBronze"]
    assert write_bronze["Action"] == "s3:PutObject"
    assert _resolve(write_bronze["Resource"]).endswith("/bronze/*")
    assert "levi9-praksa" not in _resolve(write_bronze["Resource"])


def test_bronze_copy_has_no_trigger(template):
    # Manual runs only: no S3 notification or schedule that could re-trigger it on its own writes.
    template.resource_count_is("Custom::S3BucketNotifications", 0)
    template.resource_count_is("AWS::Events::Rule", 0)
    template.resource_count_is("AWS::Lambda::EventSourceMapping", 0)
    template.resource_count_is("AWS::Lambda::Permission", 0)


def test_bronze_copy_logs_expire_and_are_removed(template):
    template.has_resource(
        "AWS::Logs::LogGroup",
        {"Properties": {"RetentionInDays": 7}, "DeletionPolicy": "Delete"},
    )


def test_bronze_copy_function_name_is_exported(template):
    template.has_output("BronzeCopyFunctionName", {"Value": {"Ref": Match.string_like_regexp("BronzeCopyFunction")}})
