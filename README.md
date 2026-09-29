# Botfarm – selbstklonende Trading-Bots

Eine Kolonie von Trading-Bots, die sich nach einem einfachen Regelwerk selbst
vermehrt oder abschaltet:

1. **Start:** Auf der Karte liegen 50 €. Der erste Bot bekommt dieses Kapital
   (oder es wird mit `--initial-bots N` auf N Bots verteilt).
2. **Handelstag:** Jeder aktive Bot handelt mit seinem eigenen Kapital. Am
   Tagesende werden alle Positionen geschlossen, damit das Ergebnis in Euro
   feststeht.
3. **Nicht profitabel → abgeschaltet.** Wer am Tagesende nicht im Plus ist
   (auch ±0 zählt als nicht profitabel), wird sofort gestoppt. Sein
   Restkapital geht zurück auf die Karte.
4. **Profitabel → Klon.** Wer im Plus ist, klont sich selbst. Der Bot entscheidet
   eigenständig über sein Gen `clone_share` (10–100 %), wie viel seines
   Tagesgewinns er dem Klon als Startkapital mitgibt. Sein eigenes Startkapital
   behält er. Der Klon erbt die Strategie mit leichten Mutationen und läuft ab
   dem nächsten Tag nach denselben Regeln.

Dadurch entsteht eine Art Evolution: Strategien, die Geld verdienen, vermehren
sich, und alle anderen verschwinden.

## Schnellstart

```bash
python3 -m botfarm --days 30 --seed 42
python3 -m botfarm --days 60 --initial-bots 5 --respawn --report report.json
```

Wichtige Optionen:

| Option | Bedeutung |
|---|---|
| `--capital 50` | Guthaben auf der Karte |
| `--clone-threshold 0` | Mindest-Tagesgewinn in € zum Überleben/Klonen. `50` = Bot muss sein Kapital an einem Tag verdoppeln |
| `--min-clone-capital 1` | Kleinere Klon-Beträge werden übersprungen |
| `--fee 0.001` | Gebühr pro Kauf/Verkauf (0,1 %) |
| `--max-bots 100` | Obergrenze gleichzeitig laufender Bots |
| `--initial-bots 1` | Startkapital auf mehrere Bots verteilen |
| `--respawn` | Wenn alle Bots tot sind: neue Bots aus dem Restguthaben der Karte starten |
| `--report datei.json` | Stammbaum, Genome und alle Ereignisse als JSON |

## Test mit echten Kursdaten

Mit `--symbol` spielt die Kolonie echte historische Minutenkurse von Binance
ab (öffentliche Daten, kein Konto nötig, Zwischenspeicher in `.cache/`):

```bash
python3 -m botfarm --symbol BTCUSDT --from 2025-09-20 --days 360 --initial-bots 5 --respawn
```

Ergebnis (360 Tage ab 20.09.2025, 5 Start-Bots, Respawn, je 10 Läufe mit
verschiedenen Seeds, Start 50 €):

| Markt | Gebühr | Endkapital Median | Spanne | Bots erzeugt | Nur kaufen und halten |
|---|---|---|---|---|---|
| BTCUSDT | 0,1 % | 40,09 € | 37,54–43,15 € | ~1170 | 33,81 € |
| BTCUSDT | 0 % | 50,32 € | 46,71–53,00 € | ~1000 | 33,81 € |
| ETHUSDT | 0,1 % | 36,40 € | 33,12–40,93 € | ~1060 | 28,15 € |
| ETHUSDT | 0 % | 47,97 € | 43,99–55,51 € | ~940 | 28,15 € |

Mit realistischen Gebühren verliert die Kolonie 20–27 % pro Jahr. Ohne
Gebühren landet sie ungefähr bei ±0. Das zeigt, dass die Strategien keinen
echten Vorteil haben. Sie verlieren nur weniger als reines Halten, weil sie
in einem fallenden Markt oft Cash halten.

## Sicherheitsmechanismen

- **Nur Paper-Trading:** Gehandelt wird gegen einen simulierten Markt
  (`botfarm/market.py`). Es gibt bewusst keine Anbindung an echte Karten oder
  Broker.
- **Bot-Limit** (`--max-bots`): Die Vermehrung kann nicht unbegrenzt laufen.
  Beim Limit dürfen die profitabelsten Bots zuerst klonen.
- **Not-Aus:** Legt man im Arbeitsverzeichnis eine Datei `STOP` an, werden
  zu Beginn des nächsten Tages alle Bots abgeschaltet und ihr Kapital
  zurückgebucht.
- **Kein Hebel, nur Long:** Ein Bot kann höchstens sein eigenes Kapital
  verlieren, nie mehr.
- **Lückenlose Buchführung:** Jede Zuteilung, Rückbuchung und jeder
  Klon-Übertrag landet in `card.transactions`. Ein Test stellt sicher, dass sich
  das Gesamtkapital nur durch Handelsergebnisse ändert.

## Realitätscheck

Die Simulation zeigt ehrlich, was passiert: Mit zufälligen Strategien ist ein
Bot an einem Tag etwa mit Münzwurf-Wahrscheinlichkeit im Plus. Die
Gebühren sorgen dafür, dass die Kolonie im Mittel **leicht Geld verliert**,
auch wenn viele Bots erzeugt werden. „Profitabel an einem Tag“ ist meist Glück
und keine Fähigkeit. Die Klon-Regel belohnt deshalb häufig Zufallstreffer.
Bevor echtes Geld im Spiel ist, sollte eine Strategie über viele Tage und
Marktphasen hinweg getestet werden, zum Beispiel mit historischen Kursdaten
statt des simulierten Markts.

## Aufbau

```
botfarm/
  data.py        Echte Binance-Kursdaten + HistoricalMarket
  ledger.py      Karte: Guthaben + Buchungsprotokoll
  market.py      Simulierter Markt (GBM mit Bull/Bear/Seitwärts/Volatil-Phasen)
  strategies.py  Strategie-Genom (Momentum, Mean-Reversion, Breakout) + Mutation
  bot.py         Ein Bot: handelt einen Tag, schließt Positionen am Tagesende
  colony.py      Regelwerk: abschalten, klonen, Kapital übertragen, Limits
  __main__.py    Kommandozeile
tests/           Unit-Tests (python3 -m unittest)
```

Einen anderen Markt (z.B. historische Kurse) kann man anbinden, indem man
`Colony(market=...)` ein Objekt mit `next_day() -> list[float]` und
`regime.name` übergibt.
