# Tasks: DP-3 Data lake bucket (CDK)

Plan: [plan.md](plan.md) · Spec: [DP-3.md](DP-3.md)

- [x] **T1: Alati i konfiguracija**
  - Acceptance: CDK CLI globalno; `aws-cdk-lib`, `constructs` u `requirements.txt`; `requirements-dev.txt` sa pytest i ruff; `pyproject.toml` sa ruff/pytest konfiguracijom; `.gitignore` ignoriše `cdk.out/`, `.ruff_cache/`, `node_modules/`.
  - Verify: `cdk --version`, `ruff --version`, `pytest` (63 zeleno).
  - Files: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.gitignore`

- [x] **T2: Ruff čist na postojećem kodu**
  - Acceptance: `ruff check .` i `ruff format --check .` bez nalaza; ponašanje nepromenjeno.
  - Verify: ruff + `pytest` (63 zeleno).
  - Files: `src/*.py`, `tests/*.py`

- [x] **T3: DataLakeStack (TDD)**
  - Acceptance: bucket sa SSE-S3, BLOCK_ALL, BucketOwnerEnforced, SSL-only policy, DESTROY + auto-delete, output `DataBucketName`; `DATA_PREFIXES` = bronze/silver/gold; nema hardkodovanog account ID-a.
  - Verify: `pytest`, `ruff`, `cdk synth --profile mateja`.
  - Files: `infra/__init__.py`, `infra/data_lake_stack.py`, `app.py`, `cdk.json`, `tests/infra/test_data_lake_stack.py`

- [x] **T4: CLAUDE.md**
  - Acceptance: projekat, grad, region, izvorni bucket, komande, bronze/silver/gold, pravilo `DP-<n>:`, bez tajni u kodu.
  - Verify: pregled prema specu.
  - Files: `CLAUDE.md`

- [x] **T5: docs/infra.md**
  - Acceptance: šta stack pravi i šta radi svaka dozvola (kontrolno pitanje).
  - Verify: uporediti sa `cdk.out/DataLakeStack.template.json`.
  - Files: `docs/infra.md`

- [x] **T6: Živi deploy/destroy** (pitati pre deploy i destroy)
  - Acceptance: `cdk deploy` i `cdk destroy --force` prolaze bez ručnih koraka; bucket proveren pa obrisan.
  - Verify: AWS CLI provere + konzola; posle destroy stack i bucket ne postoje.

- [ ] **T7: Review i PR**
  - Acceptance: review nalazi rešeni; PR ka `develop` sa naslovom `DP-3: ...` (pitati pre pusha).
