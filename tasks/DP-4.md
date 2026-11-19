# DP-4: Bronze sloj — kopiranje pollution i weather fajlova

Uloga: Data Engineer · Grana: `feature/DP-4-bronze-pollution-weather` (iz `develop`) · PR ka `develop`

## Cilj
Prvi deo pipeline-a. Lambda kopira sirove fajlove za Novi Sad (stanica `35120`) iz izvornog bucketa
`levi9-praksa-2026-data` u naš bucket, u `bronze/` sloj. Sadržaj fajlova se ne menja.

## Zahtevi (iz tiketa)
1. CDK: Lambda funkcija sa dozvolom da čita izvorni bucket i piše u naš.
2. Lambda prolazi kroz fajlove grada u `pollution/` i `weather/` i kopira ih u `bronze/pollution/` i `bronze/weather/`.
3. Pre kopiranja proverava da li fajl već postoji u bronze; ako postoji, preskače ga.
4. Grad i folderi se Lambdi prosleđuju kao environment varijable, ne upisuju se u kod.
5. Testovi sa `moto` (dozvoljeno pisati ih posle koda).

## Kriterijumi prihvatanja
1. Posle pokretanja svi fajlovi grada su u `bronze/<izvor>/`.
2. Drugo pokretanje ne kopira ništa ponovo.
3. Izvor i grad su konfiguracija, ne hardkodovane vrednosti.
4. Unit testovi sa moto prolaze.

## Odluke
- **Izbor grada po ID-u stanice.** Env: `STATION_ID=35120` (za biranje foldera, jer su imena NFD) i
  `CITY_NAME=Novi Sad` (samo za logove). Folderi: `SOURCE_FOLDERS=pollution,weather`. Bucketi:
  `SOURCE_BUCKET`, `TARGET_BUCKET`. Vrednosti žive u `cdk.json` context-u, ne u kodu.
- **Raspored ključeva:** `bronze/` + ceo izvorni ključ, npr.
  `bronze/pollution/35120 - <ime>/DD-MM-YYYY/<fajl>`. Bronze je tačna kopija izvora.
- **Kopiranje:** server-side `copy_object` (podaci ne prolaze kroz Lambdu). Postojanje se proverava jednim
  `LIST`-om bronze prefiksa (skup ključeva), ne `HEAD`-om po fajlu.
- **Okidač:** samo ručno pokretanje (`aws lambda invoke`). Bez S3 eventa i bez rasporeda → nema petlje.
- **Dozvole (least privilege):** izvor: `s3:ListBucket` + `s3:GetObject` samo na `pollution/*` i `weather/*`;
  naš bucket: list + read + put samo na `bronze/*`. Nikakvo pisanje u izvorni bucket.
- **Nova dev zavisnost:** `moto[s3]` u `requirements-dev.txt` (odobreno).
- **Trošak:** ~4100 fajlova (~1,5 MB) → prvo pokretanje ~$0,02–0,03, svako sledeće ≈ $0.

## Van opsega
Silver/gold transformacije, tourist API, raspored (EventBridge), S3 event okidači.

## Kontrolno pitanje
*Šta se desi ako Lambda radi dvaput?* Drugo pokretanje lista bronze, vidi da su svi fajlovi tu i ne kopira
ništa (`copied=0`); kopira samo fajlove koji su se u međuvremenu pojavili u izvoru. Rezultat je isti kao posle
jednog pokretanja (idempotentnost), a prekinuto pokretanje se nastavlja tamo gde je stalo.
