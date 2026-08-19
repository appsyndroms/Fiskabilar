# V60/V90/BMW 530e/330e-fyndfilter

Automatiskt filter (kör var 15:e minut, mål ~30 min, 06-22 svensk tid)
som letar efter Volvo V60/V90 Recharge (T6/T8 AWD) och BMW 330e 530e xDrive
Touring, räknar fram ett marknadsvärde per bil och mejlar dig
**direkt** när en annons ligger tydligt under vad den borde kosta.

**Notisregel: varje bil mejlas max EN gång, någonsin.** Så fort ett
fynd upptäcks skickas ett eget mejl direkt för just den bilen (inte
en samlad sammanfattning i slutet). Nästa körning ser samma bil igen
men skickar inget nytt mejl om den - historiken i `data/state.json`
kommer ihåg vilka bilar som redan mejlats, permanent.

**Bilar styrs av `BILAR` i `config.py`** - en lista där varje post
beskriver märke, modell, sökvägar för Wayke/Bilweb och vilka varianter
som räknas som träff. Lägg till fler bilar genom att lägga till fler
poster i listan; ta bort genom att ta bort en post. Se kommentarerna
i `config.py` för hur varje fält används.

⚠️ **Migrationsnotis (2026-08-12):** historiknyckeln i `state.json`
ändrades för att skilja V60 från V90 (annars hade en V60 och en V90
med råkat lika variant/år/mil kunnat räknas som samma bil). Det gör
att de V60-bilar som redan notifierats med den GAMLA nyckeln ser ut
som nya igen och kan mejlas EN gång till efter den här uppdateringen.
Efter det första varvet fungerar "aldrig upprepning" som vanligt igen.

## Status per källa (uppdaterad 2026-08-12)

| Källa | Status | Kommentar |
|---|---|---|
| **Wayke** | ✅ Verifierad (V60+V90) | Server-renderad, fungerar med `requests`. Textmönster-baserad parser, samma mall för båda modellerna. |
| **Bilweb** | ✅ Verifierad (V60+V90) | Fungerar UTAN JavaScript. Modell/variant/år/ID läses direkt ur annons-URL:en. |
| **Bytbil** | ⚠️ Ej verifierad | Websökningen hittade inte Bytbils faktiska sökresultat. Koden är fortfarande en overifierad mall. Avaktiverad som standard. |
| **Blocket** | ⚠️ Ej verifierad, avaktiverad | Aktivt anti-bot-skydd (Datadome). Avaktiverad som standard. |

Om du vill lägga till Bytbil eller Blocket senare:
1. Öppna sajten i en vanlig webbläsare, sök fram V60/V90 Recharge
2. Testa om `curl` eller Pythons `requests` (utan webbläsare) ger samma
   innehåll som webbläsaren visar - om ja, samma teknik som Wayke/Bilweb
   fungerar. Om sidan bara visar en tom "laddar..."-platshållare utan JS
   behöver du ett verktyg som kör JavaScript (t.ex. Playwright)
3. Leta efter stabila textetiketter eller mönster i URL:en att bygga en
   regex-parser kring, istället för att lita på CSS-klasser som ändras ofta
4. Lägg till källan i `AKTIVA_KALLOR` i `config.py` när den är klar

## Snabbstart

1. **Skapa ett GitHub-repo** och lägg in alla filer i det här projektet.
2. **Sätt upp e-post:**
   - Mottagaradress är redan ifylld i `config.py` (`fazzious@hotmail.com`)
   - Redigera `EPOST_FRAN` i `config.py` till det konto som ska skicka
   - Om du använder Gmail: skapa ett "app-lösenord" (inte ditt vanliga
     lösenord) under Google-kontots säkerhetsinställningar
   - I GitHub-repot: Settings → Secrets and variables → Actions →
     New repository secret → namn `EPOST_LOSENORD`, värde = app-lösenordet
3. **Verifiera/fixa scraperna** enligt avsnittet ovan (viktigast: Wayke och
   Bytbil, de är sannolikt enklast att komma igång med)
4. **Testa lokalt** (valfritt men rekommenderas):
   ```bash
   pip install -r requirements.txt
   python main.py
   ```
5. **Pusha till GitHub.** Workflow-filen (`.github/workflows/daily.yml`)
   triggar sedan var 30:e minut mellan 06:00-22:00 svensk tid (både
   sommar- och vintertid hanteras automatiskt, se kommentar i filen),
   helt utan att du behöver ha något igång själv - fungerar fint från
   iPad eftersom du bara hanterar det via GitHub-appen eller webben.
6. Du kan även trigga en körning manuellt när som helst: gå till
   **Actions**-fliken i repot → välj workflowen → **Run workflow**.

## Om Actions-minuter (viktigt om du gör repot privat)

Schemat begär körningar var 15:e minut (för att i praktiken hamna nära
30 minuter, se kommentar i `daily.yml`) 06-22 svensk tid, vilket ger
upp till ~72 körningar/dag, vardera 30-80 sekunder enligt loggarna =
ungefär 1 500-2 500 minuter/månad.
- **Publikt repo:** GitHub Actions är gratis och obegränsat.
- **Privat repo:** Gratisnivån ger 2 000 minuter/månad - med det här
  schemat kan du faktiskt nå taket. Om du märker att körningar slutar
  triggas mot slutet av månaden: gör repot publikt (koden avslöjar
  inget känsligt - lösenordet ligger som secret, inte i koden), eller
  dra ner till `*/20` istället för `*/15` i `daily.yml`.

## Justera reglerna

Allt du troligen vill ändra finns i `config.py`:
- Fyndtrösklar (just nu 20 000 / 35 000 kr under marknadsvärde)
- Max miltal, årsmodellintervall
- Vilka källor som är aktiva

Marknadsvärderingen (basprisnivåer per modell/år/variant) finns i
`valuation.py` och bör uppdateras efter vad du faktiskt ser på
marknaden de första veckorna - modellen är en rimlig startpunkt, inte
facit. V90-baspriserna sattes efter en snabb koll av verkliga
Wayke-annonser (visade sig ligga bara måttligt över V60, +15-20k,
inte den stora premie man kanske skulle gissa) - kalibrera vidare med
egen data.

**Känd begränsning (upptäckt vid testkörning):** utrustningsjusteringen
i `valuation.py` matchar bara exakta ord som "core"/"ultimate"/
"inscription". Fritext som "R-Design Pano Drag HK Elstol" matchar
inget och får då ingen justering, vilket kan få välutrustade R-Design-
bilar att se dyrare ut än de "borde" vara. Åtgärda genom att lägga
till fler nyckelord i `UTRUSTNINGSNIVA_JUSTERING` när du ser mönster
i verkliga annonser.

## Filstruktur

```
config.py          - alla inställningar
valuation.py        - marknadsvärdesmodell
dedup.py            - slår ihop samma bil från olika sajter
state.py            - historik: prissänkningar, hur länge en bil legat ute
scoring.py           - fyndscore 0-100 + formatering av meddelande
notify.py            - skickar e-post
main.py              - kör hela flödet
scrapers/            - en fil per sajt
.github/workflows/   - schemat som kör allt automatiskt
```

## Nästa steg om du vill förbättra det

- Byt ut den regelbaserade marknadsvärderingen mot en riktig regression
  när du samlat 30-50 verkliga datapunkter
- Lägg till Telegram-notis som alternativ/komplement till e-post
- Lägg till en enkel webbsida (t.ex. GitHub Pages) som visar historik
  över alla fynd, inte bara dagens
