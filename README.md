Fiskabilar

Automatiserat fyndfilter för begagnade laddhybrider.

Projektet bevakar utvalda bilmodeller på flera annonssajter, identifierar samma fysiska bil mellan källorna, bygger upp historik över marknaden och beräknar ett uppskattat marknadsvärde. Bilar som ser ut att vara tydligt billigare än marknadsvärdet kan notifieras via e-post.

Projektet har utvecklats från ett enkelt regelbaserat fyndfilter till en pipeline med identitet, historik, livscykelanalys, marknadstrender, ML-baserad värdering, fyndutfall och en statisk webbvy.

Vad bevakas?

Aktuella konfigurationer finns i config.py.

Modell	Årsmodell	Varianter
Volvo V60	2023–2026	T6 AWD, T8 AWD
Volvo V90	2023–2026	T6 AWD, T8 AWD
BMW 530e xDrive Touring	2024	530e xDrive Touring
BMW 330e xDrive Touring	2024–2026	330e xDrive Touring

Gemensamma grundkrav:

* Automatisk växellåda
* 1 000–12 000 mil
* Skadade bilar kan filtreras bort
* Årsmodell och varianter styrs per bilmodell i config.py

Att lägga till eller ta bort en bilmodell görs genom att ändra BILAR i config.py. Scraperlogiken behöver normalt inte ändras för varje ny modell.

Datakällor

Följande källor är för närvarande konfigurerade som aktiva:

* Wayke
* Bilweb
* Bytbil

Blocket har scraperkod i projektet men är inte en aktiv källa i nuvarande konfiguration.

Källspecifik logik ligger i sources/. Källorna ansvarar för att hämta och normalisera annonser; de ska inte känna till scoring, valuation eller notifiering.

Huvudflödet

Varje körning följer i princip denna kedja:

Annonssajter
    │
    ▼
sources/
    │
    ▼
Normaliserade annonser
    │
    ▼
matching/
    │
    ▼
Samma fysiska bil identifieras
    │
    ▼
history/
    │
    ├── state
    ├── identity
    ├── historik
    ├── trend
    └── livscykel
    │
    ▼
valuation/
    │
    ▼
Marknadsvärde
    │
    ▼
scoring/
    │
    ▼
Fyndkandidater
    │
    ├── notifications/
    │
    └── reporting/

main.py orkestrerar flödet. Domänlogiken ligger i separata paket.

Mer detaljer finns i ARCHITECTURE.md⁠￼.

Identitet och deduplicering

Samma bil kan finnas på flera annonssajter och dessutom ändra pris eller annonsinformation över tid.

Projektet försöker därför skilja mellan:

* annons – en publicering på en viss sajt
* fordon – den fysiska bilen
* observation – hur bilen såg ut vid en viss körning

Det gör att historiken kan följa bilen även när samma fordon förekommer på flera källor.

Identity- och lifecycle-logiken ligger under history/.

Livscykeln kan bland annat beskriva om en annons är:

* NY
* AKTIV
* ÅTERKOMMEN
* FÖRSVUNNEN

Livscykeln används som analysinformation och är separerad från själva score- och valuationlogiken.

Marknadsvärdering

Projektet har två nivåer av värdering.

1. Marknadsunderlag

valuation/ bygger jämförelseunderlag från aktuella och historiska annonser.

2. ML-baserad värdering

ML-delen ligger i ml/ och använder den historik som byggts upp av projektet.

Den nuvarande ML-processen kan:

* profilera marknadsdatasetet
* träna en marknadsvärderingsmodell
* diagnostisera modellen
* generera ML-baserade marknadsvärden
* använda dessa värden i fyndfiltrets fortsatta bearbetning

ML-värderingen skrivs bland annat till:

data/ml_valuation.jsonl

Tränade modeller och metadata sparas under:

data/ml/

ML-värderingen är ett underlag, inte en garanti för vad en bil faktiskt är värd. Modellen blir bättre när projektet samlar mer verklig marknadsdata.

Vad räknas som ett fynd?

De centrala trösklarna finns i config.py:

* FYND_TROSKEL = 20 000
* EXTREMT_FYND_TROSKEL = 35 000

Det innebär att fyndlogiken utgår från hur mycket annonsens pris ligger under projektets uppskattade marknadsvärde.

Det finns även logik för bland annat:

* prisförändringar
* hur länge en bil legat ute
* marknadstrender
* stora prissänkningar
* tidigare notifieringar

Notifieringar

Notifiering sker via e-post.

En redan notifierad bil får inte automatiskt samma notis igen. En ny notis kan däremot skickas om priset därefter sänks tillräckligt mycket.

Nuvarande gräns är:

MIN_PRISSANKNING_FOR_NY_NOTIS = 10000

Notifieringshistoriken sparas i state så att samma bil kan följas över flera körningar.

E-postlösenord ska aldrig ligga i källkoden. GitHub Actions använder repository secret:

EPOST_LOSENORD

Övriga mottagar-/avsändarinställningar finns i config.py.

Historik och rapporter

Projektet sparar marknadsobservationer löpande.

Historik:

data/market_history/

Dagliga rapporter:

data/daily_reports/

Codex påminner kl. 19.00 svensk tid. Kvällskörningen startas manuellt. Rapportdatum låses
när körningen börjar. Rapporten sparas efter datainsamlingen och före ML-träningen.
Mejl är avstängt i lokala körningar. Om insamlingen passerar midnatt stoppas körningen innan
rapporten skapas, så att observationer från olika dagar inte blandas.
En viss dag kan sammanställas med
`python -m reporting.daily_market_report --date ÅÅÅÅ-MM-DD`.

Historiken används både för vanlig analys och som underlag för ML-modellen.

Projektet sparar dessutom information om faktiska fyndutfall. Det gör att det går att analysera om de bilar som systemet markerar faktiskt utvecklas till bra köp enligt de kriterier som används.

Daglig webb

Kvällskörningen bygger en statisk webbplats från projektets data.

Webbbygget innehåller bland annat:

* aktuella fynd
* prisförändringar
* fyndutfall
* score-analys
* marknadshistorik
* ML-information

Webbens källkod finns under:

web/

Webben visas tills vidare lokalt på http://127.0.0.1:8766.

Lokal kvällskörning med act

Hela flödet startas manuellt en gång per kväll på Macen genom `act`. Inga GitHub Actions-
minuter, Pages-artifacts eller Docker behövs. De gamla fynd- och rapportschemana
är avstängda i workflow-filerna; de går fortfarande att starta manuellt på GitHub.

1. Hämta annonser, deduplicera, uppdatera identitet, historik och state.
2. Beräkna fynd och följ upp tidigare fyndutfall.
3. Spara dagens sammanfattning. Alla mejlutskick är avstängda i kvällsflödet.
4. Träna ML-modellen, kör diagnostik och skapa ML-värderingar.
5. Bygg och validera den lokala webben.

Installera Python 3.11 eller senare och `act`. Skapa sedan projektets Pythonmiljö:

```sh
python3 scripts/setup_local.py
```

Kör allt manuellt:

```sh
bash scripts/run_evening.sh
```

Lokala körningar skickar inga mejl och behöver inga mejlhemligheter.
Rapporten sparas i `data/daily_reports/`. Secrets, loggar och genererad webb
ignoreras av Git.

Installera den lokala webbservern och ta bort det tidigare automatiska kvällsjobbet:

```sh
.venv/bin/python scripts/install_local_schedule.py --install
```

Kvällskörningen har inget automatiskt jobb i launchd. En påminnelse i Codex
kl. 19.00 svensk tid ersätter schemat; inga jobb startas av påminnelsen.
Webbservern startar direkt och vid inloggning. Den lyssnar på 127.0.0.1:8766.

Körstatus med steg, tider och mejlstatus finns i `.local/evening-status.json`.
Loggen finns i `.local/logs/evening.log`. Ett lås hindrar överlappande körningar.
Misslyckad insamling stoppar kedjan. Mejlstatus är `disabled` för lokala
körningar. Data sparas i arbetskopian; kvällsflödet
gör inga automatiska Git-pushar.

HTTP-fel från en aktiv datakälla, inklusive 403, 404, 429 och 5xx, samt timeout
eller anslutningsfel stoppar hela kedjan med felstatus. Detsamma gäller fel i
Bilwebs parallella detaljsidor. Inga annonsobservationer eller state-ändringar
sparas från en ofullständig insamling. Spärrsidor som returnerar HTTP 200
avvisas också när de känns igen. Tomma resultat ska inte maskera nätverksfel.

Webben byggs i en separat katalog och ersätter den tidigare fungerande webben
först efter lyckad validering. Ett rent webbbygge skriver sin egen status i
`.local/web-build-status.json` och skriver inte över kvällskörningens status.
State och rapportloggar skrivs atomärt. En omkörning samma dag räknas inte som
en andra missad dag i annonsens livscykel. Trasiga identitets- och rapportfiler
stoppar körningen i stället för att skrivas över med tomma uppgifter.

ML-träningen använder både `pris` från annonsobservationer och `annonspris`
från värdeobservationer. Träning och test separeras vid en faktisk tidpunkt,
så att samma observationstid inte finns i båda delarna. Träningen kräver
minst 30 giltiga observationer och två olika tidpunkter. Kommandot
`python -m ml.train_market_model` tränar och diagnostiserar modellen; det
lokala kvällsflödet kör detta steg en gång. En ofullständig ML-värderingsfil
får inte ersätta den tidigare filen.

För att bara bygga om webben från sparad data:

```sh
.venv/bin/python -m scripts.evening --build-only
```

Workflowen är `.github/workflows/evening-local.yml`, som använder en lokal
host runner via `.actrc`. Övriga workflow-filer finns kvar för manuell felsökning.

Lokal körning

Installera beroenden:

pip install -r requirements.txt

Kör huvudflödet:

python -u main.py

Debug kan aktiveras med miljövariabeln:

DEBUG=true python -u main.py

I debugläge körs pipeline-logiken men notifieringar skickas inte och notifieringsstate markeras inte.

Loggning

Central loggning finns i:

app_logging/logger.py

Nivåerna är:

QUIET < INFO < DEBUG < TRACE

Standardnivån är QUIET.

* QUIET – endast viktiga fel/varningar och avsedda slutresultat
* INFO – normal körningsinformation
* DEBUG – detaljerad diagnostik
* TRACE – maximal diagnostik

Loggnivå kan styras med --log-level.

Projektstruktur

Fiskabilar/
│
├── main.py
├── config.py
├── requirements.txt
├── ARCHITECTURE.md
│
├── sources/          # hämtning och normalisering från annonssajter
├── matching/         # identifiering och deduplicering av fordon
├── history/          # state, identity, historik, trend och lifecycle
├── valuation/        # marknadsunderlag och marknadsvärde
├── scoring/          # fyndscore och kandidatlogik
├── notifications/    # notifieringar
├── reporting/        # dagliga marknadsrapporter
├── ml/               # dataset, träning, diagnostik och ML-värdering
├── pipeline/         # orkestrering av delar av körningen
├── web/              # analys och statisk webb
├── app_logging/      # central loggning
├── scripts/          # analys- och underhållsskript
│
├── data/
│   ├── market_history/
│   ├── daily_reports/
│   ├── ml/
│   └── ml_valuation.jsonl
│
└── .github/workflows/  # automatiserade körningar

Konfigurationspunkter

De viktigaste inställningarna finns i config.py.

Där kan du bland annat ändra:

* vilka bilmodeller som bevakas
* årsmodellintervall
* miltal
* aktiva källor
* fyndtrösklar
* krav på prisnedsättning för ny notifiering
* historik- och rapportkataloger
* e-postinställningar

Kodens struktur är medvetet byggd så att konfiguration och domänlogik hålls isär.

Utvecklingsprincip

Projektet utvecklas stegvis.

Målet är inte att göra en stor omskrivning varje gång en ny funktion behövs, utan att flytta ansvar till rätt del av systemet och behålla fungerande datakontrakt.

Grundprinciperna är:

* sources/ hämtar och normaliserar data
* matching/ identifierar fordon
* history/ äger persistence och historisk analys
* valuation/ beräknar marknadsunderlag och värde
* scoring/ beräknar fyndscore
* notifications/ skickar notifieringar
* reporting/ producerar rapporter
* web/ presenterar analyser
* main.py orkestrerar flödet

Det gör det möjligt att utveckla exempelvis ML-värderingen utan att behöva blanda in scraper- eller notifieringslogik.

Status

Projektet är aktivt under utveckling.

Fokus ligger just nu på att bygga upp tillräckligt bra historik och ML-underlag för att gradvis kunna ersätta manuella/reglerade antaganden med modeller som lär sig av den faktiska marknaden.

Det viktiga är därför inte bara att hitta billiga annonser, utan att samla data över tid och kunna mäta vilka signaler som faktiskt leder till intressanta bilfynd.
