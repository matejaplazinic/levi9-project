# Spec: DP-2 Data profile izvora — V1

Status: proposed (rev. 2)

## Objective

Upoznati tri izvora podataka za projekat (pollution, weather, tourist API) pre nego što se gradi
pipeline (bronze → silver → gold). Konkretno:

1. Python skripta preuzima **nekoliko fajlova** iz foldera `pollution/` i `weather/` u S3 bucketu
   `levi9-praksa-2026-data`, **samo za Novi Sad**.
2. Ista skripta **jednom** poziva Tourist estimation API za **jedan datum** i ispisuje odgovor.
3. Na osnovu preuzetih podataka i odgovora API-ja piše se `docs/data-profile.md` po checklisti
   (vidi [Data profile — sadržaj](#data-profile--sadržaj)).

Korisnik: Mateja (praksa, Data Engineer track) i mentor koji pregleda PR.

### Šta je već utvrđeno (istraženo 2026-11-18, profil `mateja`)

| Izvor | Lokacija | Format | Za Novi Sad |
|---|---|---|---|
| pollution | `s3://levi9-praksa-2026-data/pollution/35120 - Ćirila i Metodija, Novi Sad, Serbia/<DD-MM-YYYY>/<fajl>` | CSV sa headerom, bez ekstenzije | 2051 fajl, 631 KB, 2022-03-30 … 2022-05-16 (48 dana) |
| weather | `s3://levi9-praksa-2026-data/weather/35120 - Ćirila i Metodija, Novi Sad, Serbia/<DD-MM-YYYY>/<fajl>` | CSV sa headerom, bez ekstenzije | 2052 fajla, 870 KB, isti period |
| tourist API | `GET https://c4frojrhvq24ycydp5s2xxiytq0qjzop.lambda-url.eu-north-1.on.aws/?date=YYYY-MM-DD`, `Authorization: Bearer <token>` | JSON: `for_date`, `info[]` sa `name`, `estimated_no_people` | — |

- Kolone pollution: `name, time_nano, time_date, location_latitude, location_longitude, location_name, measurement_pm10Atmo, measurement_pm25Atmo, measurement_pm100Atmo` (vrednost može biti string `None`).
- Kolone weather: `name, time_nano, time_date, location_latitude, location_longitude, location_name, weather_temperature, weather_feelsLike, weather_pressure, weather_humidity, weather_dewPoint, weather_clouds, weather_windSpeed, weather_windDeg`.
- Imena gradskih foldera su u Unicode **NFD** obliku (`C` + kombinovani akcenat umesto `Ć`). Zato se grad bira po **ID-u stanice** (`35120`), ne po tekstu imena.
- Bucket, Lambda URL i secret `tourist_estimate_token` su svi u **`eu-north-1`** (secret potvrđen preko `describe-secret`; vrednost nije čitana).

## Assumptions (ispravi ako nešto ne važi)

1. „Nekoliko fajlova" = podrazumevano **5 po izvoru**, iz jednog dana (prvi dostupni dan), sa opcijom da se promeni.
2. Folderi `sensor/` i `pollution-reduced/` nisu deo ovog zadatka.
3. Podrazumevani datum za tourist API je **2022-04-15** (unutar perioda S3 podataka), menja se argumentom.
4. AWS pristup ide preko SSO profila `mateja`; skripta ga čita iz argumenta / `AWS_PROFILE`, ne iz koda.
5. URL API-ja je podrazumevana vrednost u kodu (nije tajna), sa mogućnošću da se pregazi env varijablom `TOURIST_API_URL`.
6. Secret je ili čist string tokena ili JSON sa jednim ključem; skripta podržava oba (proverava se pri prvom pokretanju, bez ispisa vrednosti).
7. „Koliko često stižu podaci" se meri na preuzetim fajlovima **i** na listingu svih ključeva za Novi Sad (vremena iz imena fajlova), bez preuzimanja svega.

## Tech Stack

- Python 3.14 (pokreće se kroz `py` launcher; `python` nije u PATH-u)
- `boto3` — S3 i Secrets Manager
- `requests` — HTTP poziv tourist API-ja
- `pytest` — testovi (S3/Secrets mockovani preko `botocore.stub.Stubber`, HTTP preko `monkeypatch`)

## Commands

```bash
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

aws sso login --profile mateja

# preuzimanje + tourist poziv
py -m src.fetch_sources --profile mateja --station 35120 --files 5 --tourist-date 2022-04-15

# samo S3 deo / samo API deo
py -m src.fetch_sources --profile mateja --station 35120 --skip-tourist
py -m src.fetch_sources --profile mateja --only-tourist --tourist-date 2022-04-15

# testovi
py -m pytest -q
```

## Project Structure

```
levi9-project/
├── SPEC.md
├── README.md
├── requirements.txt
├── .gitignore            → .venv/, data/, .env, __pycache__/
├── src/
│   ├── __init__.py
│   ├── fetch_sources.py  → CLI: argumenti, poziva s3_source i tourist_api
│   ├── s3_source.py      → nalaženje gradskog prefiksa po ID-u, listanje, preuzimanje
│   └── tourist_api.py    → čitanje tokena iz Secrets Managera, GET poziv
├── tests/
│   ├── test_s3_source.py
│   └── test_tourist_api.py
├── data/raw/             → preuzeti fajlovi i odgovor API-ja (NE commituje se)
│   ├── pollution/35120/<DD-MM-YYYY>/<fajl>.csv
│   ├── weather/35120/<DD-MM-YYYY>/<fajl>.csv
│   └── tourist/<YYYY-MM-DD>.json
└── docs/
    └── data-profile.md
```

Lokalne putanje koriste samo ID stanice (`35120`), bez akcenata i razmaka, i dodaju `.csv` ekstenziju.

## Data profile — sadržaj

`docs/data-profile.md` ima po jednu sekciju za **pollution**, **weather** i **tourist API**, i u svakoj:

1. **Format fajla** — tip (CSV/JSON), encoding, header, delimiter, ekstenzija, struktura putanje.
2. **Kolone i tipovi** — tabela: kolona, tip (string/int/float/timestamp), jedinica, primer vrednosti.
3. **Vremenska kolona** — koja kolona je vreme (`time_nano` vs `time_date` / `for_date`), format, timezone, da li se slažu.
4. **Koliko često stižu podaci** — razmak između zapisa, broj fajlova/zapisa po danu, period pokrivenosti, rupe.
5. **Uočeni problemi**
   - prazne vrednosti (npr. string `None`, prazna polja),
   - čudne vrednosti (negativne, nemoguće, outlieri),
   - duplikati (isti `time_nano` u više fajlova, isti fajl dvaput).

Plus zajednička sekcija:

6. **Predlog kako se izvori spajaju** — ključevi (stanica/lokacija + vreme zaokruženo na zajedničku granularnost; tourist po datumu i `name` lokacije), tip join-a, i šta se radi sa razlikom u granularnosti (npr. pollution/weather agregirani na dan pre spajanja sa tourist podacima).

Tvrdnje u profilu se zasnivaju na preuzetim fajlovima/odgovoru; gde je zaključak iz uzorka, to se naglasi.

## Code Style

PEP 8, type hints, male funkcije bez skrivenog globalnog stanja, `logging` za status
(odgovor API-ja se ispisuje na stdout kao formatirani JSON).

```python
def find_city_prefix(s3, bucket: str, source: str, station_id: str) -> str:
    """Vrati pun S3 prefiks grada (npr. 'pollution/35120 - Ćirila i Metodija, .../') po ID-u stanice."""
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=f"{source}/", Delimiter="/")
    for p in resp.get("CommonPrefixes", []):
        if p["Prefix"].split("/")[1].split(" - ")[0] == station_id:
            return p["Prefix"]
    raise ValueError(f"Stanica {station_id} ne postoji u {bucket}/{source}/")
```

## Testing Strategy

- `pytest`, testovi u `tests/`, bez pristupa pravom AWS-u ili internetu.
- `s3_source`: nalaženje prefiksa po ID-u (uključujući NFD ime), greška za nepostojeći ID, ograničenje broja fajlova, formiranje lokalne putanje.
- `tourist_api`: header `Authorization: Bearer …` i parametar `date` se šalju; neispravan format datuma se odbija pre poziva; HTTP greška (401/5xx) daje jasnu poruku; token se **nikad** ne pojavljuje u logu/izlazu; secret kao string i kao JSON.
- Ručna provera: jedno pravo pokretanje skripte protiv AWS-a i API-ja; rezultat se opisuje u PR-u.

## Boundaries

- **Always:** čitaj token samo iz Secrets Managera u memoriju; koristi profil `mateja` samo za čitanje (S3 `List/Get`, `secretsmanager:GetSecretValue`); radi na grani `feature/DP-2-data-profile`; pokreni testove pre commita; **commit poruke (i naslovi PR-ova) obavezno na engleskom**, npr. `DP-2: Add S3 source downloader`.
- **Ask first:** dodavanje zavisnosti van gornje liste; preuzimanje više od ~50 fajlova; više od jednog poziva tourist API-ja; push i otvaranje PR-a.
- **Never:** commit tokena, `.env` ili `data/`; ispis tokena u terminal/log; bilo kakvo pisanje/brisanje u S3 bucketu ili Secrets Manageru (profil ima admin prava — ne koristiti ih).

## Success Criteria

1. `py -m src.fetch_sources --profile mateja --station 35120 --files 5` preuzme tačno 5 pollution i 5 weather fajlova za Novi Sad u `data/raw/...` i ispiše njihove putanje.
2. Isti poziv sa `--tourist-date 2022-04-15` napravi **tačno jedan** GET ka tourist API-ju, ispiše JSON sa `for_date` i listom `info` (`name`, `estimated_no_people`) i sačuva ga u `data/raw/tourist/2022-04-15.json`.
3. `py -m pytest -q` prolazi bez mreže i bez AWS kredencijala.
4. `docs/data-profile.md` pokriva svih 5 stavki za svaki od 3 izvora i ima sekciju o spajanju.
5. `git status` posle pokretanja ne prikazuje `data/`, `.env` ni token.

## Out of Scope (Deferred)

- Preuzimanje svih fajlova / svih gradova — dolazi sa bronze ingestion zadatkom.
- `sensor/` i `pollution-reduced/` — nisu traženi u DP-2.
- Implementacija spajanja, čišćenje (`None` → null), Parquet, Glue/Athena — silver/gold faze (u DP-2 samo **predlog** spajanja).
- Retry/backoff i paginacija API-ja — jedan poziv je dovoljan za profil.

## Open Questions

Nema blokirajućih. Ako se pri prvom pokretanju pokaže da se `info[].name` iz tourist API-ja ne može povezati sa lokacijom stanice u Novom Sadu, to se upisuje u data profile kao problem i pitanje za mentora.
