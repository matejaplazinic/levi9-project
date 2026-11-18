# Tasks: DP-2 Data profile izvora

Plan: [plan.md](plan.md) · Spec: [SPEC.md](../SPEC.md)

- [x] **T1: Setup projekta**
  - Acceptance: `.venv` napravljen; `requirements.txt` sa `boto3`, `requests`, `pytest`; `.gitignore` sadrži `.venv/`, `data/`, `.env`, `__pycache__/`, `.pytest_cache/`; postoje `src/__init__.py` i `tests/`.
  - Verify: `pip install -r requirements.txt` prolazi; `py -m pytest -q` se pokreće.
  - Files: `requirements.txt`, `.gitignore`, `src/__init__.py`, `tests/__init__.py`

- [x] **T2: S3 izvor**
  - Acceptance: `find_city_prefix` nalazi prefiks po ID-u (i za NFD ime) i baca `ValueError` za nepostojeći; `list_day_keys` vraća ključeve prvog (ili zadatog) dana; `download_files` preuzima najviše N fajlova u `data/raw/<source>/<station>/<DD-MM-YYYY>/<fajl>.csv`.
  - Verify: `py -m pytest tests/test_s3_source.py -q` zeleno (bez mreže).
  - Files: `src/s3_source.py`, `tests/test_s3_source.py`

- [x] **T3: Tourist API**
  - Acceptance: `get_token` čita secret iz `eu-north-1` (string ili JSON); `validate_date` odbija sve osim `YYYY-MM-DD`; `fetch_estimate` šalje tačno jedan GET sa `date` i `Authorization: Bearer`; HTTP greška daje jasnu poruku; token se ne pojavljuje u izlazu.
  - Verify: `py -m pytest tests/test_tourist_api.py -q` zeleno (bez mreže).
  - Files: `src/tourist_api.py`, `tests/test_tourist_api.py`

- [x] **T4: CLI**
  - Acceptance: `py -m src.fetch_sources` podržava `--profile`, `--station`, `--files`, `--tourist-date`, `--skip-tourist`, `--only-tourist`; ispisuje putanje fajlova i formatiran JSON; čuva `data/raw/tourist/<datum>.json`; jasna poruka za istekli SSO.
  - Verify: `py -m src.fetch_sources --help`; ceo `py -m pytest -q` zeleno.
  - Files: `src/fetch_sources.py`

- [x] **T5: Pravo pokretanje**
  - Acceptance: 5 pollution + 5 weather fajlova za Novi Sad u `data/raw/`; tačno 1 API poziv, odgovor ima `for_date` i `info[]`.
  - Verify: `py -m src.fetch_sources --profile mateja --station 35120 --files 5 --tourist-date 2022-04-15`; `git status` ne prikazuje `data/`.
  - Files: — (samo `data/raw/`, ignorisano)

- [x] **T6: Data profile**
  - Acceptance: `docs/data-profile.md` — za pollution, weather i tourist: format, kolone i tipovi, vremenska kolona, učestalost, problemi (prazne/čudne/duplikati); plus predlog spajanja. Zaključci iz uzorka su naglašeni.
  - Verify: ručni pregled prema SPEC „Data profile — sadržaj“; brojke se slažu sa analizom.
  - Files: `docs/data-profile.md`
