# V60-fyndfilter

Dagligt automatiskt filter som letar efter Volvo V60 Recharge (T6/T8 AWD),
räknar fram ett marknadsvärde per bil och mejlar dig när en annons ligger
tydligt under vad den borde kosta.

## Status per källa (uppdaterad 2026-08-09)

| Källa | Status | Kommentar |
|---|---|---|
| **Wayke** | ✅ Verifierad | Server-renderad, fungerar med `requests`. Textmönster-baserad parser (etiketter som "Mätarställning:" ändras sällan). |
| **Bilweb** | ✅ Verifierad | Fungerar UTAN JavaScript (bekräftat - sidan visar full data trots att JS är avstängt). Variant/år/ID läses direkt ur annons-URL:en, vilket är extra robust. |
| **Bytbil** | ⚠️ Ej verifierad | Websökningen hittade inte Bytbils faktiska sökresultat den här sessionen. Koden är fortfarande en overifierad mall. Avaktiverad som standard i `config.py`. |
| **Blocket** | ⚠️ Ej verifierad, avaktiverad | Aktivt anti-bot-skydd (Datadome). Kräver mer jobb och försiktighet. Avaktiverad som standard. |

**Med Wayke + Bilweb aktiva täcker du redan en stor del av marknaden** -
Bilweb ensam hade 1 300+ V60-annonser vid testet. Det är en solid start.

Om du vill lägga till Bytbil eller Blocket senare:
1. Öppna sajten i en vanlig webbläsare, sök fram V60 Recharge
2. Testa om `curl` eller Pythons `requests` (utan webbläsare) ger samma
   innehåll som webbläsaren visar - om ja, samma teknik som Wayke/Bilweb
   fungerar. Om sidan bara visar en tom "laddar..."-platshållare utan JS
   behöver du ett verktyg som kör JavaScript (t.ex. Playwright)
3. Leta efter stabila textetiketter (som "Mätarställning:") eller mönster
   i URL:en (som Bilwebs årsmodell-i-slug) att bygga en regex-parser kring,
   istället för att lita på CSS-klasser som ändras ofta
4. Lägg till källan i `AKTIVA_KALLOR` i `config.py` när den är klar

## Snabbstart

1. **Skapa ett GitHub-repo** och lägg in alla filer i det här projektet.
2. **Sätt upp e-post:**
   - Redigera `config.py`: `EPOST_TILL` och `EPOST_FRAN`
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

Med 30-minuters intervall 06-22 blir det ~36 körningar/dag, vardera en
knapp minut = ungefär 1 000-1 500 minuter/månad.
- **Publikt repo:** GitHub Actions är gratis och obegränsat.
- **Privat repo:** Gratisnivån ger 2 000 minuter/månad, så du ligger
  nära taket men bör klara dig. Om du vill vara säker: gör repot
  publikt (koden avslöjar inget känsligt - lösenordet ligger som
  secret, inte i koden) eller dra ner till t.ex. var 45:e minut.

## Justera reglerna

Allt du troligen vill ändra finns i `config.py`:
- Fyndtrösklar (just nu 20 000 / 35 000 kr under marknadsvärde)
- Max miltal, årsmodellintervall
- Vilka källor som är aktiva

Marknadsvärderingen (basprisnivåer per år/variant) finns i `valuation.py`
och bör uppdateras efter vad du faktiskt ser på marknaden de första
veckorna - modellen är en rimlig startpunkt, inte facit.

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
