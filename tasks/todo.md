# Tasks: DP-4 Bronze sloj (pollution + weather)

Plan: [plan.md](plan.md) · Spec: [DP-4.md](DP-4.md)

- [x] **T1: Spec, plan i lista taskova**
  - Acceptance: `tasks/DP-4.md`, `tasks/plan.md`, `tasks/todo.md` opisuju DP-4; korisnik je pročitao plan.
  - Verify: pregled sa korisnikom.
  - Files: `tasks/DP-4.md`, `tasks/plan.md`, `tasks/todo.md` · Scope: XS

> **Gate (ispunjen):** DP-3 spojen u `develop`, DP-4 grana fast-forwardovana na `origin/develop`.

- [x] **T2: Handler kopira jedan izvor i preskače postojeće**
  - Acceptance: `copy_source(s3, source_bucket, target_bucket, folder, station_id)` kopira sve ključeve stanice
    u `bronze/<ključ>` sa identičnim sadržajem; drugi poziv vraća `copied=0`; fajlovi stanice `1297` se ne kopiraju;
    nepostojeća stanica → `ValueError`.
  - Verify: `pytest tests/lambdas -q` (moto `mock_aws`, NFD imena foldera kao u `tests/test_s3_source.py`), ruff.
  - Files: `lambdas/__init__.py`, `lambdas/bronze_copy/__init__.py`, `lambdas/bronze_copy/handler.py`,
    `tests/lambdas/test_bronze_copy.py`, `requirements-dev.txt` (`moto[s3]`) · Scope: M
  - Deps: Gate

- [ ] **T3: Konfiguracija iz env varijabli i svi folderi**
  - Acceptance: `handler(event, context)` čita `SOURCE_BUCKET`, `TARGET_BUCKET`, `STATION_ID`, `CITY_NAME`,
    `SOURCE_FOLDERS`; prolazi kroz sve foldere i vraća `{folder: {copied, skipped}}`; nedostajuća varijabla →
    jasna greška sa imenom varijable; u kodu Lambde nema `35120` ni `Novi Sad` (test).
  - Verify: `pytest tests/lambdas -q` (`monkeypatch.setenv`), ruff.
  - Files: `lambdas/bronze_copy/handler.py`, `tests/lambdas/test_bronze_copy.py` · Scope: S
  - Deps: T2

### Checkpoint A (posle T3)
- [ ] `ruff check .`, `ruff format --check .`, `pytest` zeleno; handler pokriva kriterijume 1, 2 i 4 u moto testovima.

- [ ] **T4: CDK Lambda sa env varijablama i dozvolama**
  - Acceptance: jedna `AWS::Lambda::Function` (Python 3.13, 256 MB, 5 min) sa 5 env varijabli; vrednosti iz
    `cdk.json` context-a; IAM: izvor samo List + Get na `pollution/*`, `weather/*`, naš bucket List/Get/Put samo na
    `bronze/*`, bez `s3:Delete*` i bez pisanja u izvor; nema S3 notifikacija ni EventBridge pravila; log retencija 7 dana;
    bucket construct ID nepromenjen; output sa imenom funkcije.
  - Verify: `pytest tests/infra -q`, ruff, `cdk synth --profile mateja`, `cdk diff --profile mateja` (bez replace bucketa).
  - Files: `infra/data_lake_stack.py`, `cdk.json`, `app.py`, `tests/infra/test_data_lake_stack.py` · Scope: M
  - Deps: T3

- [ ] **T5: docs/infra.md**
  - Acceptance: opisani nova Lambda, njena rola, svaka dozvola i zašto; odgovor na kontrolno pitanje; trošak.
  - Verify: uporediti sa `cdk.out/DataLakeStack.template.json`.
  - Files: `docs/infra.md` · Scope: XS · Deps: T4

### Checkpoint B (posle T5)
- [ ] Sve zeleno, `cdk diff` pregledan sa korisnikom pre deploy-a.

- [ ] **T6: Živi deploy i dva pokretanja** (pitam pre `cdk deploy`)
  - Acceptance: 1. invoke kopira ~2051 + ~2052 fajla; broj objekata u `bronze/pollution/` i `bronze/weather/` =
    broj u izvoru za `35120`; 2. invoke vraća `copied=0`; trajanje i memorija u granicama.
  - Verify: `aws lambda invoke` ×2, `aws s3 ls --recursive ... | wc -l` za izvor i bronze, CloudWatch log.
  - Files: `tasks/todo.md` (rezultati) · Deps: Checkpoint B
  - Posle: pitam da li stack ostaje ili ide `cdk destroy`.

- [ ] **T7: CLAUDE.md ažuriranje** (uvek poslednji korak pre review-a)
  - Acceptance: arhitektura (`lambdas/bronze_copy`, env varijable, bronze raspored ključeva), komanda za invoke,
    odeljak **AWS cost** (iz `git stash` "AWS cost rules for CLAUDE.md"), pravilo da se `CLAUDE.md` ažurira na kraju
    svakog tiketa.
  - Verify: pregled; `pytest` (test za account ID i dalje zelen).
  - Files: `CLAUDE.md` · Scope: XS · Deps: T6

- [ ] **T8: Review i PR**
  - Acceptance: `/agent-skills:review` nalazi rešeni; pročitana tabela Common Rationalizations iz
    `incremental-implementation`; PR ka `develop`, naslov `DP-4: ...` (pitam pre pusha).
  - Verify: ruff, pytest, `cdk synth` zeleno na finalnom commitu.
