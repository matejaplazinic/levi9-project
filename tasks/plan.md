# Plan: DP-4 Bronze sloj (pollution + weather)

Spec: [DP-4.md](DP-4.md)

## Pregled
Lambda (`lambdas/bronze_copy/`) kopira fajlove stanice `35120` iz `levi9-praksa-2026-data/{pollution,weather}/`
u `bronze/` našeg bucketa, preskače postojeće i dobija svu konfiguraciju kroz env varijable. CDK je dodaje u
`DataLakeStack`, sa least-privilege dozvolama i bez okidača. Testovi: `moto` za handler, `Template` za CDK.

## Preduslov
Ispunjen: DP-3 (PR #2) je spojen u `develop`, a DP-4 grana je fast-forwardovana na `origin/develop` (`f6a7b39`).

## Zavisnosti
```
T1 spec/plan ─► [DP-3 merge] ─► T2 handler (jedan izvor, skip) ─► T3 env konfiguracija + više foldera
                                                                        │
                                                    T4 CDK Lambda + dozvole ◄┘
                                                        │
                                  T5 docs/infra.md ◄────┤
                                                        ▼
                                          T6 živi deploy + 2× invoke ─► T7 CLAUDE.md ─► T8 review + PR
```

## Arhitektonske odluke
- Lambda kod u zasebnom paketu `lambdas/bronze_copy/handler.py`, samo stdlib + `boto3` (već postoji u Lambda
  runtime-u) → nema bundlinga. Mala funkcija za pronalaženje foldera po ID-u je namerno kopirana iz
  `src/s3_source.py: find_city_prefix` (ista logika), jer `src/` vuče `requests` i nije deo Lambda paketa.
- Ključ u bronze = `bronze/` + izvorni ključ. Skup postojećih ključeva se pravi jednim paginiranim LIST-om.
- `copy_object` server-side; bez paralelizacije u V1 (~4100 fajlova staje u timeout od 5 min; meri se u T6).
- Runtime `PYTHON_3_13`, 256 MB, timeout 5 min, log grupa sa retencijom 1 nedelja + `DESTROY`.
- Konfiguracija (`STATION_ID`, `CITY_NAME`, `SOURCE_FOLDERS`, `SOURCE_BUCKET`) u `cdk.json` context-u;
  `TARGET_BUCKET` iz `bucket.bucket_name`.
- Dodavanje Lambde ne menja construct ID bucketa → `cdk diff` ne sme da pokaže replace bucketa.

## Taskovi (svaki = jedan commit `DP-4: ...`)
1. **T1** Spec, plan i lista taskova.
2. **T2** Handler: kopira jedan izvor, preskače postojeće (moto testovi).
3. **T3** Konfiguracija iz env varijabli, svi folderi iz `SOURCE_FOLDERS`, jasne greške.
4. **T4** CDK: Lambda u `DataLakeStack` sa env varijablama i dozvolama (Template testovi).
5. **T5** `docs/infra.md`: nova Lambda, rola, svaka dozvola, kontrolno pitanje.
6. **T6** Živi deploy, 2× invoke, provera (pitam pre deploy-a i pre eventualnog destroy-a).
7. **T7** `CLAUDE.md` ažuriranje (uvek poslednji korak pre review-a).
8. **T8** `/agent-skills:review` i PR ka `develop` (pitam pre pusha).

Detalji, acceptance i verify po tasku: [todo.md](todo.md).

## Rizici
| Rizik | Uticaj | Mitigacija |
|---|---|---|
| DP-3 nije spojen u `develop` | Visok (blokira T2+) | Čekamo merge, pa `git merge origin/develop` |
| Izvorni bucket je u drugom nalogu / bucket policy ne dozvoljava našu rolu | Visok | T6 prvo proba jedan invoke; ako `AccessDenied`, stajemo i pitamo mentora |
| Timeout kod ~4100 kopija | Srednji | Idempotentno: novo pokretanje nastavlja; po potrebi thread pool u zasebnom tasku |
| Filter stanice ne radi → kopira sve stanice | Srednji (trošak) | Test sa drugom stanicom (`1297`) koja ne sme da se kopira |
| `cdk diff` pokaže replace bucketa | Visok (brisanje podataka) | Stop i pitam |
| moto i jsii na Pythonu 3.14 | Nizak | Proveriti u T2 instalacijom; ako ne radi, pitam |

## Otvorena pitanja
- Posle T6: da li stack ostaje deployovan za DP-5 ili radimo `cdk destroy`? (Pitam u T6.)
