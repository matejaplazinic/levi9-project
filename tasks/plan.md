# Plan: DP-3 Data lake bucket (CDK)

Spec: [DP-3.md](DP-3.md)

## Kontekst
Tiket DP-3 traži prvi deo infrastrukture kao kod: CDK (Python) stack sa jednim S3 bucketom
(SSE-S3, blokiran javni pristup, samo HTTPS) za podatke pod `bronze/`, `silver/`, `gold/`.
Uz to: pytest + ruff, CLAUDE.md (/init + context-engineering) i živi `cdk deploy` → provera → `cdk destroy`.
Spec je odobren: `tasks/DP-3.md`. Grana `feature/DP-3-infra` je već napravljena iz `origin/develop`
(upstream uklonjen), PR #1 (DP-2) je već u `develop`.

Prvi korak posle odobrenja: plan i taskove upisati u `tasks/plan.md` i `tasks/todo.md` (zamenjuju DP-2
verzije; DP-2 verzije ostaju u git istoriji), pa raditi `/build` task po task, jedan commit po tasku.

## Taskovi (redom, svaki = jedan commit `DP-3: ...`)

**T1: Alati i konfiguracija**
- `npm install -g aws-cdk` (odobreno u specu); u `.venv`: `aws-cdk-lib`, `constructs`, `ruff`.
- `requirements.txt` += `aws-cdk-lib>=2.170,<3`, `constructs>=10,<11`; novi `requirements-dev.txt`
  (`-r requirements.txt`, `pytest`, `ruff`) — pytest se seli iz requirements.txt u dev.
- `pyproject.toml`: `[tool.ruff]` line-length 120, target py312, lint `E,F,I,B,UP`;
  `[tool.pytest.ini_options]` testpaths `tests`.
- `.gitignore` += `cdk.out/`, `.ruff_cache/`, `node_modules/`.
- Verify: `cdk --version`, `ruff --version`, `py -m pytest -q` (63 zeleno).
- Rizik: Python 3.14 + jsii. Ako `import aws_cdk` ne radi na 3.14, stajem i pitam (opcija: venv na 3.12/3.13).

**T2: Ruff čist na postojećem kodu**
- `ruff check . --fix` + `ruff format .` na `src/`, `tests/`; ručno rešiti ostatak bez promene ponašanja.
- Verify: `ruff check .`, `ruff format --check .`, `pytest` (63 zeleno).

**T3: DataLakeStack (TDD)**
- Prvo test `tests/infra/__init__.py` + `tests/infra/test_data_lake_stack.py` (`aws_cdk.assertions.Template`):
  AES256 enkripcija, 4× public access block `true`, `OwnershipControls BucketOwnerEnforced`, Deny za
  `aws:SecureTransport=false`, `DeletionPolicy: Delete`, `Custom::S3AutoDeleteObjects`, output
  `DataBucketName`, `DATA_PREFIXES == ("bronze/","silver/","gold/")`, nema hardkodovanog account ID-a. → crveno.
- Zatim `infra/__init__.py`, `infra/data_lake_stack.py` (kod iz speca + `CfnOutput`), `app.py`
  (`env=Environment(account=os.environ["CDK_DEFAULT_ACCOUNT"], region="eu-north-1")`), `cdk.json`
  (`"app": ".venv/Scripts/python app.py"`). → zeleno.
- Verify: `pytest`, `ruff`, `cdk synth --profile mateja` (samo bucket, policy, auto-delete Lambda + rola, custom resource, metadata).

**T4: CLAUDE.md**
- Pokrenuti `/init` skill, pa doraditi uz `context-engineering` skill: projekat, Novi Sad (35120), `eu-north-1`,
  izvorni bucket `levi9-praksa-2026-data` (read-only), AWS profil `mateja` + `aws sso login`, komande
  (pip/ruff/pytest/cdk), struktura (`src/`, `infra/`, `tests/`), bronze/silver/gold konvencija,
  pravila: commit `DP-<n>:` na engleskom, grane `feature/DP-<n>-...` → PR u `develop`, tajne nikad u kod/log.
- Verify: pročitati i proveriti prema kriterijumima iz speca.

**T5: docs/infra.md — kontrolno pitanje**
- Iz `cdk.out/DataLakeStack.template.json`: šta pravi stack i šta radi svaka dozvola
  (bucket policy: SSL deny + dozvole auto-delete roli; Lambda rola `AWSLambdaBasicExecutionRole`;
  CDK bootstrap role koje koristi deploy). Bez account ID-a.

**T6: Živi deploy/destroy** (pitam pre deploy i pre destroy)
- `aws sso login` po potrebi → `cdk diff` → **pitam** → `cdk deploy` → provera CLI-jem
  (`get-bucket-encryption`, `get-public-access-block`, `get-bucket-policy`) + korisnik gleda konzolu →
  **pitam** → `cdk destroy --force` → provera da stack i bucket ne postoje.

**T7: Review i PR**
- `/agent-skills:review` na diff `origin/develop...HEAD`, popraviti nalaze.
- **Pitam** → push `-u origin feature/DP-3-infra`, PR ka `develop`, naslov `DP-3: ...`.

## Ključni fajlovi
`app.py`, `cdk.json`, `infra/data_lake_stack.py`, `tests/infra/test_data_lake_stack.py`, `pyproject.toml`,
`requirements*.txt`, `.gitignore`, `CLAUDE.md`, `docs/infra.md`, `tasks/plan.md`, `tasks/todo.md`.

## Verifikacija (end-to-end)
`ruff check .` · `ruff format --check .` · `pytest` (63 + novi) · `cdk synth` · `cdk deploy` + provera
bucketa · `cdk destroy` bez ručnih koraka · CLAUDE.md pokriva sve iz speca.
