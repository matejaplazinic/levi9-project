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
| `BronzeCopyFunction` | `AWS::Lambda::Function` | DP-4: copies the station's raw files from the source bucket into `bronze/` (see [Bronze copy Lambda](#bronze-copy-lambda-dp-4)). |
| `BronzeCopyFunctionServiceRole` | `AWS::IAM::Role` | Execution role of the bronze copy Lambda. |
| `BronzeCopyFunctionServiceRoleDefaultPolicy` | `AWS::IAM::Policy` | The S3 permissions of that role (statement 6 below). |
| `BronzeCopyLogs` | `AWS::Logs::LogGroup` | The Lambda's CloudWatch logs, kept for 7 days and deleted with the stack. |
| `CDKMetadata` | `AWS::CDK::Metadata` | Anonymous CDK version data. Has no effect on access. |

The `DataBucketName` output gives the generated bucket name, and `BronzeCopyFunctionName` gives the Lambda's name.

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

### 6. IAM role of the bronze copy Lambda (DP-4)
- **Trust policy:** only `lambda.amazonaws.com` can assume it.
- **Managed policy** `AWSLambdaBasicExecutionRole`: CloudWatch logs only, as in statement 3.
- **Inline policy** (`BronzeCopyFunctionServiceRoleDefaultPolicy`), built from the `bronze_copy` context in `cdk.json`:

| Sid | Action | Resource | Condition | Why |
|---|---|---|---|---|
| `ListSourceFolders` | `s3:ListBucket` | `levi9-praksa-2026-data` | `s3:prefix` like `pollution/*`, `weather/*` | Find the station folder by ID and list its files. Other folders of the source bucket cannot be listed. |
| `ReadSourceFiles` | `s3:GetObject` | `levi9-praksa-2026-data/pollution/*`, `.../weather/*` | — | Read side of the server-side `CopyObject`. |
| `ListBronze` | `s3:ListBucket` | our bucket | `s3:prefix` like `bronze/*` | One listing of what is already in bronze, so existing files are skipped. |
| `WriteBronze` | `s3:PutObject` | our bucket `/bronze/*` | — | Write side of `CopyObject`. Nothing outside `bronze/`. |

There is no write, delete or tagging permission on the source bucket, and no delete permission on ours. The code also
refuses to start if `TARGET_BUCKET` equals `SOURCE_BUCKET`.

## Bronze copy Lambda (DP-4)

Code: [`lambdas/bronze_copy/handler.py`](../lambdas/bronze_copy/handler.py). Python 3.13, 256 MB, 5-minute timeout.

- **Configuration** is in environment variables, filled from the `bronze_copy` context in `cdk.json`:
  `SOURCE_BUCKET`, `TARGET_BUCKET` (our bucket), `STATION_ID`, `CITY_NAME` (logs only), `SOURCE_FOLDERS`
  (comma-separated). The station is selected by numeric ID because the source folder names are NFD-normalized.
- **Key layout:** `bronze/` + the full source key, e.g. `bronze/pollution/<id> - <name>/<DD-MM-YYYY>/<file>`.
  File contents are not changed (server-side `CopyObject`; the data never passes through the Lambda).
- **No trigger:** it runs only when invoked by hand
  (`aws lambda invoke --function-name <BronzeCopyFunctionName> --profile mateja out.json`). It has no S3 event
  or schedule, so it can never re-trigger itself on its own writes.
- **Result:** `{"pollution": {"copied": n, "skipped": m}, "weather": {...}}`.
- **Speed:** copies run on 16 threads (boto3 pool of 16 connections, standard retries with up to 10 attempts).
  The first full run for Novi Sad (~4,100 files) took ~100 s of the 5-minute timeout; a run with nothing to copy ~8 s.

**Known limitations**
- Files are skipped **by key only**. If the source ever rewrites a file under the same key, bronze keeps the old
  version. That matches the ticket ("if it exists, skip it").
- Two invocations at the same time would both copy the missing files (same bytes, double the requests). Run it once at
  a time; `reserved_concurrent_executions=1` was left out because reserving concurrency fails on accounts with a low
  concurrency limit.
- If two source folders share the station ID (e.g. after a rename), the run fails with an error instead of picking one.

**What happens if the Lambda runs twice? (control question)** Before copying, it lists the station's keys that
already exist in `bronze/` and skips them. The second run therefore copies nothing (`copied = 0`) and only picks up
files that appeared in the source since the first run. The result is the same as after one run (idempotent), and a run
that stopped halfway (e.g. a timeout) simply continues on the next invocation.

**Cost:** about 4,100 files (~1.5 MB) for Novi Sad. The first run is about 4,100 `CopyObject` requests (~$0.02); every
later run is a few `LIST` requests (practically $0). The idle Lambda costs nothing.
