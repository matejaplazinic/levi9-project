# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Levi9 internship 2026 data project. The project combines air pollution and weather sensor data with
daily tourist estimates for **Novi Sad** (sensor station `35120`). It is built ticket by ticket (`DP-<n>`).
Specs: `SPEC.md` (DP-2), `tasks/DP-<n>.md` (from DP-3 on). `tasks/plan.md` and `tasks/todo.md` hold only the
current ticket's plan and task list; older versions live in git history.

- AWS account access goes through the SSO profile **`mateja`**. The working region is **`eu-north-1`**. SSO itself lives in `eu-west-1`, which is already set in `~/.aws/config`.
- **Source data** is in bucket `levi9-praksa-2026-data` (eu-north-1, **read-only for us**). The folders are `pollution/`, `weather/`, `sensor/` and `pollution-reduced/`.
- **Our data** goes into the bucket created by `DataLakeStack`, under the prefixes `bronze/` (raw copies), `silver/` (cleaned) and `gold/` (aggregated, joined). The prefixes are a convention (`infra/data_lake_stack.py: DATA_PREFIXES`), not folders. CloudFormation generates the bucket name; read it from the stack output `DataBucketName`.
- The tourist API token is in Secrets Manager as `tourist_estimate_token` (eu-north-1). Only the secret's *name* appears in code.

## Commands

This is Windows. Use `py` or `.venv\Scripts\python`, because `python` is not on PATH.

```bash
aws sso login --profile mateja                       # session expires after a few hours
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/ruff check .                           # lint (add --fix for safe fixes)
.venv/Scripts/ruff format --check .                  # formatting (drop --check to apply)
.venv/Scripts/python -m pytest -q                    # all tests, no AWS or network needed
.venv/Scripts/python -m pytest tests/infra -q        # only the CDK stack tests
.venv/Scripts/python -m pytest "tests/test_tourist_api.py::test_name" -q   # single test
cdk synth --profile mateja                           # template -> cdk.out/
cdk diff --profile mateja
cdk deploy --profile mateja                          # ask the user first
cdk destroy --profile mateja --force                 # ask the user first
.venv/Scripts/python -m src.fetch_sources --profile mateja --station 35120 --files 5 --skip-tourist   # DP-2 sample download
aws lambda invoke --profile mateja --region eu-north-1 --function-name <BronzeCopyFunctionName> --cli-read-timeout 400 out.json   # DP-4 bronze copy
```

Read `<BronzeCopyFunctionName>` and `DataBucketName` from the `cdk deploy` outputs (or `aws cloudformation describe-stacks --stack-name DataLakeStack`).
The AWS CLI's `--output text` on Windows ends lines with `\r`; strip it before comparing listings.

`cdk.json` runs the app with `.venv\Scripts\python.exe app.py`. That path is Windows-only on purpose, because the CDK CLI runs the app through `cmd`.

You may see `Error: ENOTEMPTY ... jsii-kernel-*` at the end of a pytest or cdk run. It is jsii failing to clean up its temp folder on Windows, and it can be ignored when the tests or synth themselves succeeded.

## Architecture

- `src/` is the DP-2 sample fetcher.
  - `s3_source.py` lists and downloads source files.
  - `tourist_api.py` reads the token from Secrets Manager and makes one validated GET call.
  - `fetch_sources.py` is the CLI that ties them together.
  - Downloads go to `data/raw/` (gitignored).
- `infra/` and `app.py` hold the CDK v2 Python app.
  - There is currently one stack, `DataLakeStack`. It has the bucket with SSE-S3 encryption, BLOCK_ALL public access, ACLs disabled and a TLS-only policy.
  - It also uses `RemovalPolicy.DESTROY` with `auto_delete_objects`, which adds a Lambda, an IAM role and a custom resource so that `cdk destroy` can empty the bucket.
  - It also holds the DP-4 bronze copy Lambda (below). Its settings come from the `bronze_copy` context in `cdk.json` (source bucket, station ID, city name, source folders); city and station never appear in `infra/` or `lambdas/` code, and tests check that.
  - `docs/infra.md` explains every permission.
- `lambdas/bronze_copy/handler.py` (DP-4) copies the station's files from `pollution/` and `weather/` of the source bucket to `bronze/<full source key>` in our bucket.
  - Config only from env vars: `SOURCE_BUCKET`, `TARGET_BUCKET`, `STATION_ID`, `CITY_NAME` (logs only), `SOURCE_FOLDERS` (comma-separated).
  - Idempotent: lists bronze once and skips existing keys; a second run copies 0. Server-side `copy_object` on 16 threads (~100 s for ~4,100 files; 5-minute timeout).
  - Needs only `boto3` (in the Lambda runtime), so the asset is the folder itself with no bundling. `find_station_prefix` intentionally mirrors `src/s3_source.find_city_prefix`.
  - No trigger: manual invoke only. Its role can only list/read `pollution/*` and `weather/*` in the source bucket and list/put under `bronze/*` in ours.
- `tests/` uses botocore `Stubber` and fake HTTP sessions for `src/`, `moto` (`mock_aws`) for `lambdas/`, and `aws_cdk.assertions.Template` for `infra/`. No test touches AWS.
- `docs/data-profile.md` is the profile of the source data. Read it before writing any ingestion or transform code.

### Source data gotchas (details in `docs/data-profile.md`)
- S3 key layout: `<source>/<stationId> - <name>/<DD-MM-YYYY>/<file without extension>`, with CSV content.
- Station folder names are **NFD-normalized** (e.g. `C` + a combining accent). Match stations by numeric ID, never by name. AWS CLI output with these names can crash with a `charmap` error unless you set `PYTHONUTF8=1`.
- Each hourly reading appears in 2–3 files. Deduplicate on `(station_id, time_nano)` and keep the last-written file.
- `time_nano` is UTC in nanoseconds. `time_date` is local time (UTC+2) with no timezone.
- `measurement_pm10Atmo` is actually PM1.0 and is always `"None"`. PM10 is in `pm100Atmo`.
- The tourist API returns HTTP 503 on purpose some of the time (the Lambda's `ERROR_RATE`). It names the city "Beograd", while sensors say "Belgrade".

## Rules

- Talk to the user in Serbian. Code, comments, commit messages, PR titles and `CLAUDE.md` are in English.
- Ticket workflow: spec in `tasks/DP-<n>.md` (`/agent-skills:spec`) → `/plan` (`tasks/plan.md`, `tasks/todo.md`) → user
  reads the plan → `/build` one task at a time (TDD) → `/agent-skills:review` → PR. Wait for the user's approval
  between phases.
- **Commits and PR titles are in English and start with the ticket id**, e.g. `DP-3: Add S3 bucket to CDK stack`. Use one commit per task, made as soon as that task is done.
- **Every ticket's last task before review updates `CLAUDE.md`** with what the ticket added (architecture, commands, gotchas, rules).
- Branch `feature/DP-<n>-<slug>` from `develop`. PRs go into `develop`, never into `main`. Ask before pushing or opening a PR.
- **Never write secrets into code, config, logs or test fixtures.** That includes tokens, keys and `.env` contents. Read the token into memory only, from Secrets Manager, and never print it or put it in error messages. Do not hardcode the AWS account ID either: CDK takes it from the profile (`CDK_DEFAULT_ACCOUNT`); a test checks `app.py`, `cdk.json` and `infra/`.
- Run `ruff check .`, `ruff format --check .` and `pytest` before every commit.
- AWS changes happen only through CDK code. Run `cdk diff` before `cdk deploy`. Ask before any `cdk deploy` or `cdk destroy`.
  The data bucket is `DESTROY` + `auto_delete_objects`: if `cdk diff` shows the bucket being **replaced** (e.g. a renamed
  construct ID), all its data is deleted. Stop and ask.
- Never write to or delete from `levi9-praksa-2026-data`. Never modify the `TouristApiStack` or `CDKToolkit` stacks. Never run `cdk bootstrap` (the mentor already did). The `mateja` role is an admin role, but these limits still apply.
- Ask before adding dependencies. Runtime dependencies go in `requirements.txt`, dev tools in `requirements-dev.txt`.

## AWS cost

Always pick the cheapest option that does the job.

- **Cheap (cents):** Lambda, S3 with our data (~40 MB), Athena over small data, EventBridge rules, Secrets Manager.
  The base project should stay in this range.
- **Infinite loops:** a Lambda triggered by an S3 event must never write to the bucket + prefix that triggers it,
  or it re-triggers itself forever.
- **Glue / PySpark jobs** (advanced task) are billed per minute. Run them manually; never put them on a schedule
  without the user's agreement.
- **Athena** bills per data scanned. Even though our data is small, use partitions and `LIMIT` while exploring.
- **Always-on services** (EC2, RDS, NAT Gateway, OpenSearch, etc.) are not needed for this project. Do not create
  them without asking.
- **Forgotten resources** cost money even when idle. Remove anything that is no longer used.
