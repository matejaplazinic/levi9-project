# Plan: DP-2 Data profile izvora — V1

Spec: [SPEC.md](../SPEC.md) (odobren 2026-11-18)

## Komponente i zavisnosti

```
setup (venv, requirements, .gitignore)
   │
   ├──> s3_source.py ──┐
   │                   ├──> fetch_sources.py (CLI) ──> pravo pokretanje ──> docs/data-profile.md
   └──> tourist_api.py ┘
```

- `s3_source` i `tourist_api` ne zavise jedan od drugog — rade se kao dve odvojene vertikalne celine (modul + testovi), pa se tek onda spajaju u CLI.
- Data profile zavisi od stvarnih podataka, pa ide poslednji.

## Redosled

1. **Setup** — `.venv`, `requirements.txt`, `.gitignore`, `src/__init__.py`, prazan `tests/`. Provera: `pip install` prolazi, `pytest` se pokreće (0 testova).
2. **S3 izvor (TDD)** — testovi sa `Stubber` prvo, pa `find_city_prefix`, `list_day_keys`, `download_files`, `local_path`.
3. **Tourist API (TDD)** — testovi prvo, pa `get_token` (string/JSON secret), `validate_date`, `fetch_estimate`.
4. **CLI** — `fetch_sources.py` sa argumentima iz speca; poziva 2 i 3; čuva tourist JSON u `data/raw/tourist/`.
5. **Pravo pokretanje** — jedan run protiv AWS-a i API-ja (5+5 fajlova, 1 API poziv). Provera Success Criteria 1, 2, 5.
6. **Analiza i data profile** — pomoćna analiza preuzetih fajlova + listinga ključeva za Novi Sad (učestalost, rupe, duplikati, `None`), pa pisanje `docs/data-profile.md`.

## Rizici

| Rizik | Uticaj | Mitigacija |
|---|---|---|
| NFD imena foldera | Pogrešan/nijedan prefiks | Biranje po ID-u stanice; test sa NFD imenom |
| Windows `charmap` greške pri ispisu | Pad pri logovanju imena | UTF-8 za stdout (`sys.stdout.reconfigure`) i fajlove |
| SSO token istekne | `ExpiredToken` greška | Jasna poruka: pokreni `aws sso login --profile mateja` |
| Format secreta nepoznat | Pogrešan header | Podrška za string i JSON; vrednost se nikad ne ispisuje |
| Token u logu/izlazu | Curenje tajne | Test koji proverava da token nije u izlazu; `requests` se ne loguje na DEBUG |
| `info[].name` se ne vezuje za stanicu | Slab predlog spajanja | Zapisati kao problem/pitanje u profilu |

## Checkpointi

- Posle 1: okruženje radi.
- Posle 2 i 3: `py -m pytest -q` zeleno.
- Posle 5: stvarni podaci u `data/raw/`, `git status` čist od `data/` i tajni.
- Posle 6: profil pokriva 5 stavki × 3 izvora + spajanje → spremno za commit/PR (uz pitanje pre push-a).

Koraci 2 i 3 su nezavisni i mogli bi paralelno, ali su mali — rade se redom.
