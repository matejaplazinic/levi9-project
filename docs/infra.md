# Infrastructure: DataLakeStack

The stack is defined in [`infra/data_lake_stack.py`](../infra/data_lake_stack.py). The entry point is [`app.py`](../app.py).
The region is `eu-north-1`, and the account comes from the AWS profile (`CDK_DEFAULT_ACCOUNT`).
To see the exact template, run `cdk synth --profile mateja` and open `cdk.out/DataLakeStack.template.json`.

## What the stack creates

| Resource (construct; in the template the logical ID has a hash suffix, e.g. `DataBucketE3889A50`) | Type | Why it exists |
|---|---|---|
| `DataBucket` | `AWS::S3::Bucket` | Bucket with our data under `bronze/`, `silver/` and `gold/`. |
| `DataBucketPolicy` | `AWS::S3::BucketPolicy` | Access rules for the bucket (see below). |
| `CustomS3AutoDeleteObjectsCustomResourceProviderRole` | `AWS::IAM::Role` | Role used by the Lambda that empties the bucket. |
| `CustomS3AutoDeleteObjectsCustomResourceProviderHandler` | `AWS::Lambda::Function` | Lambda that deletes all objects on `cdk destroy`, so CloudFormation can delete the bucket. |
| `DataBucketAutoDeleteObjectsCustomResource` | `Custom::S3AutoDeleteObjects` | The "trigger" that calls that Lambda when the bucket is deleted. |
| `CDKMetadata` | `AWS::CDK::Metadata` | Anonymous CDK version data. Has no effect on access. |

The `DataBucketName` output gives the generated bucket name.

## Bucket settings

| Setting | Value | What it does |
|---|---|---|
| Encryption | SSE-S3 (`AES256`) | S3 encrypts every object on write and decrypts it on read. S3 manages the keys, they cost nothing, and there is no key for us to look after. |
| Block Public Access | all 4 enabled | `BlockPublicAcls` and `IgnorePublicAcls`: a public ACL cannot be set, and any existing one is ignored. `BlockPublicPolicy` and `RestrictPublicBuckets`: the bucket policy cannot grant public access. |
| Object Ownership | `BucketOwnerEnforced` | ACLs are fully disabled. Access is controlled only through IAM and the bucket policy. |
| `enforce_ssl` | yes | Adds a Deny statement to the bucket policy (see below). |
| Removal policy | `DESTROY` + `auto_delete_objects` | `cdk destroy` deletes the bucket even when it holds data. Without this the bucket would stay in the account as an "orphan". **Risk:** the same applies when CloudFormation *replaces* the bucket (e.g. a changed construct ID), so all data is lost. Check `cdk diff` before deploying. Once the bucket holds real data, consider `RETAIN` or versioning. |

## Every permission in the stack (control question)

### 1. Bucket policy, "Deny without TLS" statement
- **Effect** `Deny`, **Principal** `*`, **Action** `s3:*`, **Resource**: the bucket and `bucket/*`.
- **Condition** `aws:SecureTransport = false`.
- **What it does:** rejects *every* request to the bucket that does not use HTTPS, no matter who sends it, even an administrator. An explicit Deny beats any Allow. This statement allows nothing; it only forbids unencrypted traffic.

### 2. Bucket policy, "Allow for the auto-delete role" statement
- **Effect** `Allow`. The **Principal** is only the auto-delete Lambda's role. **Resource**: the bucket and `bucket/*`.

| Action | Why the Lambda needs it |
|---|---|
| `s3:GetBucket*` | Reads the bucket's tags and existing policy (`GetBucketTagging`, `GetBucketPolicy`). The Lambda only empties a bucket that has the `aws-cdk:auto-delete-objects=true` tag set by CDK. This protects against deleting the wrong bucket. |
| `s3:List*` | Lists the objects (and object versions) to delete. |
| `s3:DeleteObject*` | Deletes objects and their versions. |
| `s3:PutBucketPolicy` | Before emptying, adds a Deny for `s3:PutObject` for everyone to the policy, so no new writes are possible. This way nobody can add a file while the bucket is being emptied and make `destroy` fail. |

These permissions apply **only to this bucket**, not to other buckets in the account (e.g. `levi9-praksa-2026-data`).

### 3. IAM role of the auto-delete Lambda
- **Trust policy** (`AssumeRolePolicyDocument`): `sts:AssumeRole` is allowed only for the `lambda.amazonaws.com` service. Only Lambda can assume the role, not a user or any other service.
- The **managed policy** `AWSLambdaBasicExecutionRole` grants only `logs:CreateLogGroup`, `logs:CreateLogStream` and `logs:PutLogEvents`, so the Lambda can write its logs to CloudWatch.
- The role itself has no S3 permissions. It gets bucket access only through statement 2 of the bucket policy.

### 4. Custom resource and Lambda
- `Custom::S3AutoDeleteObjects` has only a `ServiceToken` (the Lambda's ARN) and `BucketName`. When CloudFormation deletes the resource, it calls the Lambda with that bucket name.
- The Lambda runs on `nodejs24.x`, with 128 MB and a 15-minute timeout. Its code is part of CDK; we do not write it.

### 5. Permissions used by the deploy itself (not in our template)
`cdk bootstrap` (done by the mentor) created the `CDKToolkit` stack with the roles that the CDK CLI uses:
- **deploy role** (`cdk-hnb659fds-deploy-role-...`): the CLI assumes it to start a CloudFormation deploy or destroy;
- **file-publishing role**: uploads the Lambda code zip to the bootstrap assets bucket (`cdk-hnb659fds-assets-...`);
- **CloudFormation execution role**: CloudFormation uses it to actually create and delete the resources in the template;
- **lookup role**: reads account information (this stack does not use it).

We do not change these roles and we do not run `cdk bootstrap`.
