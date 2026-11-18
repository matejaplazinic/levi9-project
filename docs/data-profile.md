# Data profile — izvori za Novi Sad

Ticket: DP-2 · Datum analize: 2026-11-18 · Spec: [SPEC.md](../SPEC.md)

Stanica: **`35120 - Ćirila i Metodija, Novi Sad, Serbia`** (lat 45.25, lon 19.84).

**Osnova za zaključke**

- **Listing svih ključeva** za Novi Sad u oba S3 izvora (2051 + 2052 fajla). Odatle su učestalost, rupe i broj fajlova.
- **Preuzeti uzorak**: 5 + 5 fajlova od 30.3.2022, uz 16 fajlova pročitanih iz različitih dana. Odatle su šema, tipovi i vrednosti.
- **Jedan uspešan odgovor** tourist API-ja za `2022-04-15`.

Gde je zaključak izveden iz uzorka, to je naznačeno sa *(uzorak)*.

---

## 1. Pollution

S3: `s3://levi9-praksa-2026-data/pollution/35120 - Ćirila i Metodija, Novi Sad, Serbia/<DD-MM-YYYY>/<fajl>`

### Format fajla

| Osobina | Vrednost |
|---|---|
| Tip | CSV, delimiter `,`, polja sa zarezom su u `"..."` |
| Encoding | UTF-8, bez BOM-a, kraj reda `\n` |
| Header | Da, u svakom fajlu |
| Redova po fajlu | 1 |
| Ekstenzija | Nema (Firehose ime: `levi9-hack9-pollution-firehose-2-<YYYY-MM-DD-HH-MM-SS>-<uuid>`) |
| Veličina | 311–319 B po fajlu; ukupno 2051 fajl ≈ 631 KB |
| Particionisanje | Po gradu (folder `<id> - <ime>`), pa po danu (`DD-MM-YYYY`) |

### Kolone i tipovi

| Kolona | Tip | Jedinica / značenje | Primer |
|---|---|---|---|
| `name` | string | ID + ime stanice | `35120 - Ćirila i Metodija, Novi Sad, Serbia` |
| `time_nano` | int64 | Unix epoch u **nanosekundama, UTC** | `1648639800000000000` |
| `time_date` | string → timestamp | Lokalno vreme (CEST, UTC+2), bez oznake zone | `2022-03-30 13:30:00` |
| `location_latitude` | float | stepeni | `45.25…` |
| `location_longitude` | float | stepeni | `19.84…` |
| `location_name` | string | adresa, grad, država | `Ćirila i Metodija, Novi Sad, Serbia` |
| `measurement_pm10Atmo` | float, nullable | **PM1.0** µg/m³ (ime vara: `pm10` znači 1.0) | `None` |
| `measurement_pm25Atmo` | float | **PM2.5** µg/m³ | `14.5` |
| `measurement_pm100Atmo` | float | **PM10** µg/m³ | `16.67` |

### Vremenska kolona

- Za glavnu vremensku kolonu treba uzeti **`time_nano`** (UTC). `time_date` je ista vrednost, ali u lokalnom vremenu **UTC+2**, i string ne kaže koja je zona. U svih 21 pregledanih zapisa razlika je tačno 2 h.
- Merenje je **satno**, oko `:30` po lokalnom vremenu. Ponekad je `:31` (npr. `18:31:00`), pa vreme nije savršeno poravnato.
- Vreme u imenu fajla je vreme kada je Firehose upisao fajl (UTC). To vreme **nije** vreme merenja: fajl se pojavi oko 20 minuta posle merenja.

### Koliko često stižu podaci

- **Fajl na svakih 30 minuta** (oko `:20:43` i `:50:43` UTC), dakle **2 fajla po satnom merenju**. Medijana razmaka je 30 min, a 1995 od 2050 razmaka je tačno 30 min.
- **44 fajla po danu** za pun dan. 30.3. ima 23 (prvi dan, krenulo u 11:45 UTC), 16.5. ima 20 (poslednji dan), a 20.4. i 25.4. imaju po 36.
- Period je **30.3.2022 – 16.5.2022**, 48 dana, i nijedan dan ne fali.
- **Noćna rupa:** svake noći nema fajlova od ~21:50 do ~00:20 UTC (150 min, 47 puta). Merenje za 00:30 po lokalnom vremenu verovatno nedostaje svaki dan *(uzorak: 23:30 → 01:30 za 10./11.4)*.

### Uočeni problemi

- **Prazne vrednosti:** `measurement_pm10Atmo` (PM1.0) je u **svim** pregledanim zapisima string `"None"`, a ne prazno polje *(uzorak, 13/13)*. To treba pretvoriti u `NULL`, a kolona je praktično neupotrebljiva za Novi Sad.
- **Duplikati:** isto merenje stiže u **2–3 fajla**, sa istim `time_nano` i istim vrednostima (npr. 13:30 u tri fajla). U silver sloju treba deduplicirati po `(station_id, time_nano)`. Isti ključ fajla se nigde ne ponavlja.
- **Čudne vrednosti:** u uzorku nema negativnih ni nemogućih vrednosti. PM2.5 je između 3.7 i 32.5 µg/m³, što je realno. **Ime kolone navodi na pogrešan zaključak:** `pm10Atmo` je PM1.0, a `pm100Atmo` je PM10.
- **Imena foldera su u NFD obliku** (`C` + kombinovani akcenat), dok je sadržaj CSV-a u NFC obliku. Upoređivanje po imenu grada zato ne radi, pa grad treba birati po ID-u (`35120`).
- **Vremenska zona nije zapisana** u `time_date`.

---

## 2. Weather

S3: `s3://levi9-praksa-2026-data/weather/35120 - Ćirila i Metodija, Novi Sad, Serbia/<DD-MM-YYYY>/<fajl>`

### Format fajla

Isti kao kod pollution: CSV, UTF-8 bez BOM-a, header, 1 red po fajlu, bez ekstenzije. Veličina je 428–438 B po fajlu, a ukupno 2052 fajla ≈ 870 KB. Isto je i particionisanje.

### Kolone i tipovi

| Kolona | Tip | Jedinica / značenje | Primer |
|---|---|---|---|
| `name`, `location_*` | kao kod pollution | | |
| `time_nano` | int64 | Unix epoch ns, UTC | `1648639800000000000` |
| `time_date` | string → timestamp | lokalno vreme, UTC+2 | `2022-03-30 13:30:00` |
| `weather_temperature` | float | °C | `18.9` |
| `weather_feelsLike` | float | °C | `17.76` |
| `weather_pressure` | int | hPa | `1006` |
| `weather_humidity` | int | % | `35` |
| `weather_dewPoint` | float | °C | `3.12` |
| `weather_clouds` | int | % pokrivenosti | `100` |
| `weather_windSpeed` | float | m/s *(pretpostavka)* | `3.65` |
| `weather_windDeg` | int | stepeni (0–360) | `212` |
| `weather_windGust` | float | m/s *(pretpostavka)* | `4.85` |

### Vremenska kolona

Isto kao kod pollution: **`time_nano`** je u UTC, a `time_date` je lokalno vreme (UTC+2). Merenje je satno, oko `:30`/`:31`. Vremena se poklapaju sa pollution zapisima, pa se ta dva izvora prirodno spajaju po vremenu.

### Koliko često stižu podaci

Isto kao kod pollution: fajl na svakih 30 min, 44 fajla po danu, 30.3.–16.5.2022 (48 dana) i ista noćna rupa od 150 min. Oba izvora očigledno dolaze iz istog Firehose toka.

### Uočeni problemi

- **Prazne vrednosti:** u uzorku nema praznih ni `None` vrednosti.
- **Duplikati sa različitim vrednostima:** 2–3 fajla imaju **isti `time_nano`, ali različite vrednosti** (13:30 → temperatura 18.90 / 19.04 / 19.38). To nisu čisti duplikati: izvor osvežava vrednost, a vremensku oznaku ne menja. Pri deduplikaciji treba izabrati pravilo, npr. **poslednji upisani fajl** (po vremenu iz imena fajla).
- **Šema se razlikuje po stanicama:** Novi Sad ima kolonu **`weather_windGust`** (15 kolona), a uzorak iz Beograda (1297) je nema (14 kolona). Silver sloj mora da podnese kolonu koja negde nedostaje.
- **Čudne vrednosti:** u uzorku nema nemogućih. Negativna tačka rose (`-1.51`) je realna za hladnu noć.
- NFD imena foldera i vremenska zona koja nije zapisana su isti problemi kao kod pollution.

---

## 3. Tourist estimation API

`GET https://c4frojrhvq24ycydp5s2xxiytq0qjzop.lambda-url.eu-north-1.on.aws/?date=YYYY-MM-DD` uz header `Authorization: Bearer <token>`. Token je u Secrets Manageru (`tourist_estimate_token`, `eu-north-1`) i čuva se kao čist string ili kao JSON sa jednim ključem.

### Format

JSON objekat, UTF-8. Za jedan datum stiže jedan odgovor.

```json
{
  "for_date": "2022-04-15",
  "info": [
    {"name": "Beograd",  "estimated_no_people": 36928},
    {"name": "Novi Sad", "estimated_no_people": 19628},
    {"name": "Iași",     "estimated_no_people": 14392},
    {"name": "Kyiv",     "estimated_no_people": 36949},
    {"name": "Lviv",     "estimated_no_people": 22281}
  ]
}
```

### Kolone i tipovi

| Polje | Tip | Značenje |
|---|---|---|
| `for_date` | string → date | Datum procene (`YYYY-MM-DD`, bez vremena i zone) |
| `info[].name` | string | Ime **grada** (ne stanice) |
| `info[].estimated_no_people` | int | Procenjen broj turista u gradu tog dana |

Posle „razvijanja“ niza, jedan red je `(for_date, name, estimated_no_people)`.

### Vremenska kolona

`for_date`, granularnost je **dan**. Vremenska zona nije navedena; pretpostavka je lokalni datum.

### Koliko često stižu podaci

API ne šalje podatke sam (pull model): za svaki dan se pravi jedan poziv. Odgovor za Novi Sad je testiran samo za 15.4.2022. Za ostale datume u periodu S3 podataka nije provereno da li vraćaju odgovor.

### Uočeni problemi

- **Nestabilnost:** prvi poziv je vratio **HTTP 503** *"Service temporarily unavailable, try again"*, a drugi je uspeo. Ingestion mora da ima **retry sa backoff-om**.
- **Nedostaje Amsterdam,** iako u S3 postoje podaci za Amsterdam (stanica 38348).
- **Imena gradova nisu u istom obliku kao u drugim izvorima:** API koristi `Beograd`, a sensor folder `Belgrade`; API koristi `Iași` (NFC), a S3 folder isto ime u NFD obliku. Za spajanje je potrebna normalizacija ili tabela mapiranja.
- **Prazne, čudne i duplikat vrednosti:** u jednom odgovoru nema ničeg sumnjivog. To nije dovoljno za zaključak.

---

## 4. Predlog kako se izvori spajaju

```
pollution (sat) ─┐ join po (station_id, time_nano)  ─> stanica × sat
weather   (sat) ─┘          │
                            ▼  agregacija na dan (lokalni datum) + izvlačenje grada
                    stanica × dan ──join po (grad, datum)──> tourist (grad × dan)
```

1. **Silver, čišćenje:** `"None"` pretvoriti u `NULL`, kastovati tipove, `time_nano` pretvoriti u `timestamp UTC`, izvući `station_id` iz `name` (deo pre ` - `) i `city` iz `location_name` (pretposlednji deo: `Novi Sad`), uz NFC normalizaciju teksta.
2. **Silver, deduplikacija:** po `(station_id, time_nano)`, tako da ostane poslednji upisani fajl (vreme iz imena fajla). Po potrebi zaokružiti `time_nano` na pun sat zbog `:30`/`:31` odstupanja.
3. **Pollution + weather:** **inner join** po `(station_id, sat_utc)`. Isti Firehose tok i ista vremena daju skoro 1:1 poklapanje. Ako se želi zadržati merenje kome fali par, onda left join na pollution.
4. **Sa tourist podacima:** tourist je **grad × dan**, pa se pollution/weather prvo **agregira na dan**: prosek PM2.5/PM10/temperature, max udar vetra, broj sati sa merenjem. Dan se računa po **lokalnom** datumu (iz `time_date` ili UTC+2), jer je `for_date` verovatno lokalni dan. Zatim ide **left join** po `(city, date)` sa tourist podacima.
5. **Mapiranje gradova:** tabela `city_alias` (npr. `Belgrade` ↔ `Beograd`) za izvore koji koriste druga imena. Novi Sad se poklapa direktno.

**Otvorena pitanja za mentora:**
- Da li je `for_date` lokalni dan ili UTC dan?
- Zašto nema Amsterdama u tourist API-ju?
- Da li je noćna rupa (00:30 lokalno) poznato ograničenje izvora?
