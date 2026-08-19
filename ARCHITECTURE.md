# Fiskabilar – arkitektur

Målet är tydliga ansvar utan en stor omskrivning. Vi flyttar en logisk del i taget och behåller befintliga datakontrakt så långt det går.

## Flöde

```text
main.py
  │
  ├── sources/             hämtar och normaliserar källannonser
  │
  ├── matching/            identifierar samma fysiska bil
  │
  ├── history/             state och långtidshistorik
  │
  ├── valuation/            marknadsunderlag och marknadsvärde
  │
  ├── scoring/              fyndscore
  │
  └── notifications/       e-post/notifiering
```

## Ansvarsprinciper

- `sources/` ska inte värdera eller notifiera.
- `matching/` ska inte skicka mejl eller ändra valuation.
- `valuation/` ska inte känna till GitHub Actions eller notifieringar.
- `scoring/` ska beräkna score, inte hämta webbsidor.
- `history/` äger persistence och trend/historiklogik.
- `notifications/` äger utskick.
- `main.py` orkestrerar flödet men ska inte innehålla domänlogik.

## Loggning

Central loggning finns i `app_logging/logger.py`.

```text
QUIET < INFO < DEBUG < TRACE
```

Om `--log-level` saknas är nivån **QUIET**. Därför behöver `daily.yml` inte ändras.

- QUIET: bara viktiga fel/varningar och avsedda slutresultat.
- INFO: normal körningsinformation.
- DEBUG: detaljerad diagnostik.
- TRACE: maximal diagnostik.

## Refaktorering

Detta är ett första strukturellt steg. Stora domänmoduler delas endast när ansvar faktiskt kan separeras utan att skapa onödiga beroenden.
