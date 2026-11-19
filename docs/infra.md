# Infrastruktura: DataLakeStack

Stack je opisan u [`infra/data_lake_stack.py`](../infra/data_lake_stack.py). Ulazna tačka je [`app.py`](../app.py).
Region je `eu-north-1`, a nalog se uzima iz AWS profila (`CDK_DEFAULT_ACCOUNT`).
Kad hoćeš da vidiš tačan šablon, pokreni `cdk synth --profile mateja` i otvori `cdk.out/DataLakeStack.template.json`.

## Šta stack pravi

| Resurs (construct; u šablonu logički ID ima hash sufiks, npr. `DataBucketE3889A50`) | Tip | Zašto postoji |
|---|---|---|
| `DataBucket` | `AWS::S3::Bucket` | Bucket sa našim podacima pod `bronze/`, `silver/` i `gold/`. |
| `DataBucketPolicy` | `AWS::S3::BucketPolicy` | Pravila pristupa za bucket (vidi dole). |
| `CustomS3AutoDeleteObjectsCustomResourceProviderRole` | `AWS::IAM::Role` | Rola koju koristi Lambda za pražnjenje bucketa. |
| `CustomS3AutoDeleteObjectsCustomResourceProviderHandler` | `AWS::Lambda::Function` | Lambda koja pri `cdk destroy` obriše sve objekte, da bi CloudFormation mogao da obriše bucket. |
| `DataBucketAutoDeleteObjectsCustomResource` | `Custom::S3AutoDeleteObjects` | „Okidač“ koji poziva tu Lambdu kad se bucket briše. |
| `CDKMetadata` | `AWS::CDK::Metadata` | Anonimni podaci o verziji CDK-a. Nema uticaja na pristup. |

Izlaz `DataBucketName` daje generisano ime bucketa.

## Podešavanja bucketa

| Podešavanje | Vrednost | Šta radi |
|---|---|---|
| Enkripcija | SSE-S3 (`AES256`) | S3 svaki objekat šifruje pri upisu i dešifruje pri čitanju. Ključevima upravlja S3, ne plaćaju se i nema ključa o kom moramo da brinemo. |
| Block Public Access | sva 4 uključena | `BlockPublicAcls` i `IgnorePublicAcls`: javni ACL ne može da se postavi, a postojeći se ignoriše. `BlockPublicPolicy` i `RestrictPublicBuckets`: bucket policy ne može da da javni pristup. |
| Object Ownership | `BucketOwnerEnforced` | ACL-ovi su potpuno isključeni. Pristup se određuje samo kroz IAM i bucket policy. |
| `enforce_ssl` | da | Dodaje Deny izjavu u bucket policy (vidi dole). |
| Removal policy | `DESTROY` + `auto_delete_objects` | `cdk destroy` briše bucket čak i kad ima podataka. Bez ovoga bi bucket ostao u nalogu kao „siroče“. **Rizik:** isto važi i kad CloudFormation *zameni* bucket (npr. promenjen construct ID), pa svi podaci nestaju. Pre deploya proveri `cdk diff`. Kad u bucketu budu pravi podaci, razmotriti `RETAIN` ili versioning. |

## Svaka dozvola u stacku (kontrolno pitanje)

### 1. Bucket policy, izjava „Deny bez TLS-a“
- **Effect** `Deny`, **Principal** `*`, **Action** `s3:*`, **Resource**: bucket i `bucket/*`.
- **Condition** `aws:SecureTransport = false`.
- **Šta radi:** odbija *svaki* zahtev ka bucketu koji ne ide preko HTTPS-a, bez obzira ko ga šalje, čak i administrator. Eksplicitni Deny je jači od bilo kog Allow-a. Ova izjava ništa ne dozvoljava, samo zabranjuje nešifrovan saobraćaj.

### 2. Bucket policy, izjava „Allow za auto-delete rolu“
- **Effect** `Allow`. **Principal** je samo rola auto-delete Lambde. **Resource**: bucket i `bucket/*`.

| Akcija | Zašto treba Lambdi |
|---|---|
| `s3:GetBucket*` | Čita tagove i postojeći policy bucketa (`GetBucketTagging`, `GetBucketPolicy`). Lambda briše samo bucket koji ima tag `aws-cdk:auto-delete-objects=true`, koji je CDK postavio. To je zaštita od brisanja pogrešnog bucketa. |
| `s3:List*` | Lista objekte (i verzije objekata) koje treba obrisati. |
| `s3:DeleteObject*` | Briše objekte i njihove verzije. |
| `s3:PutBucketPolicy` | Pre pražnjenja u policy dodaje Deny za `s3:PutObject` za sve, pa novi upisi nisu mogući. Tako niko ne može da doda fajl dok se bucket prazni i da time obori `destroy`. |

Dozvole važe **samo za ovaj bucket**, ne za druge buckete u nalogu (npr. `levi9-praksa-2026-data`).

### 3. IAM rola auto-delete Lambde
- **Trust policy** (`AssumeRolePolicyDocument`): `sts:AssumeRole` je dozvoljen samo servisu `lambda.amazonaws.com`. Rolu može da „obuče“ samo Lambda, a ne korisnik ili neki drugi servis.
- **Managed policy** `AWSLambdaBasicExecutionRole` daje samo `logs:CreateLogGroup`, `logs:CreateLogStream` i `logs:PutLogEvents`, da bi Lambda mogla da piše svoje logove u CloudWatch.
- Sama rola nema nikakve S3 dozvole. Pristup bucketu dobija isključivo kroz izjavu 2 u bucket policy-ju.

### 4. Custom resource i Lambda
- `Custom::S3AutoDeleteObjects` ima samo `ServiceToken` (ARN Lambde) i `BucketName`. Kad CloudFormation briše resurs, poziva Lambdu sa tim imenom bucketa.
- Lambda je tipa `nodejs24.x`, ima 128 MB i timeout od 15 min. Kod je deo CDK-a, ne pišemo ga mi.

### 5. Dozvole koje koristi sam deploy (nisu u našem šablonu)
`cdk bootstrap` (uradio ga je mentor) napravio je stack `CDKToolkit` sa rolama koje CDK CLI koristi:
- **deploy role** (`cdk-hnb659fds-deploy-role-...`): CLI je preuzima da pokrene CloudFormation deploy ili destroy;
- **file-publishing role**: šalje zip sa kodom Lambde u bootstrap bucket sa asetima (`cdk-hnb659fds-assets-...`);
- **CloudFormation execution role**: sa njom CloudFormation zapravo pravi i briše resurse iz šablona;
- **lookup role**: za čitanje informacija o nalogu (ovaj stack je ne koristi).

Mi ove role ne menjamo i ne pokrećemo `cdk bootstrap`.
