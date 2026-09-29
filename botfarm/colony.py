"""Die Kolonie: steuert Tagesablauf, Abschalten und Klonen aller Bots.

Regeln pro Handelstag:
  1. Jeder lebende Bot handelt mit seinem Kapital.
  2. Wer am Tagesende nicht im Plus ist, wird sofort abgeschaltet.
     Sein Restkapital geht zurück auf die Karte.
  3. Wer im Plus ist, klont sich. Der Bot entscheidet selbst (über sein Gen
     ``clone_share``), wie viel seines Tagesgewinns er dem Klon mitgibt.
     Der Klon erbt die Strategie mit leichten Mutationen.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass, field

from .bot import Bot, DayResult
from .ledger import Card
from .market import SimulatedMarket
from .strategies import Genome


@dataclass
class ColonyConfig:
    start_capital: float = 50.0
    # Mindestgewinn am Tag, um zu überleben und zu klonen (0 = jeder Cent Plus reicht).
    # Mit 50 muss ein Bot sein Kapital an einem Tag verdoppeln.
    clone_threshold: float = 0.0
    min_clone_capital: float = 1.0  # Kleinere Beträge lohnen keinen Klon
    fee_rate: float = 0.001  # 0,1 % Gebühr pro Kauf/Verkauf
    mutation_rate: float = 0.15
    initial_bots: int = 1  # Startkapital wird gleichmäßig auf so viele Start-Bots verteilt
    # Sicherheitsgrenzen
    max_bots: int = 100  # Obergrenze gleichzeitig laufender Bots
    kill_switch_file: str | None = "STOP"  # existiert die Datei, stoppt alles sofort
    respawn_from_reserve: bool = False  # neuen Bot aus der Kartenreserve starten, wenn alle tot sind
    seed: int | None = None


@dataclass
class DaySummary:
    day: int
    regime: str
    alive: int
    born: int
    killed: int
    total_equity: float
    card_reserve: float
    best_profit: float
    stopped_reason: str | None = None


@dataclass
class Colony:
    config: ColonyConfig = field(default_factory=ColonyConfig)
    market: SimulatedMarket | None = None
    initial_genomes: list[Genome] | None = None  # sonst zufällige Start-Strategien
    card: Card = field(init=False)
    bots: dict[str, Bot] = field(default_factory=dict, init=False)
    day: int = field(default=0, init=False)
    events: list[dict] = field(default_factory=list, init=False)
    summaries: list[DaySummary] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.config.seed)
        if self.market is None:
            self.market = SimulatedMarket(seed=self.rng.randrange(2**32))
        self.card = Card(balance=self.config.start_capital)
        self._next_id = 1
        genomes = self.initial_genomes or [Genome.random(self.rng) for _ in range(max(1, self.config.initial_bots))]
        share = self.config.start_capital / len(genomes)
        for genome in genomes:
            self._spawn_from_card(genome, share)

    # --- Hilfsfunktionen -------------------------------------------------

    def _new_id(self) -> str:
        bot_id = f"bot-{self._next_id:04d}"
        self._next_id += 1
        return bot_id

    def _log(self, kind: str, **data) -> None:
        self.events.append({"day": self.day, "event": kind, **data})

    def _spawn_from_card(self, genome: Genome, amount: float) -> Bot:
        bot_id = self._new_id()
        capital = self.card.withdraw(amount, bot_id, self.day, "Startkapital")
        bot = Bot(bot_id, genome, capital, born_day=self.day)
        self.bots[bot_id] = bot
        self._log("spawn", bot=bot_id, capital=round(capital, 2), genome=genome.to_dict())
        return bot

    @property
    def alive_bots(self) -> list[Bot]:
        return [b for b in self.bots.values() if b.alive]

    @property
    def total_equity(self) -> float:
        return self.card.balance + sum(b.cash for b in self.alive_bots)

    def kill_switch_active(self) -> bool:
        path = self.config.kill_switch_file
        return bool(path) and os.path.exists(path)

    # --- Lebenszyklus ------------------------------------------------------

    def shutdown(self, bot: Bot, reason: str) -> None:
        bot.alive = False
        bot.died_day = self.day
        self.card.deposit(bot.cash, bot.bot_id, self.day, reason)
        self._log("shutdown", bot=bot.bot_id, returned=round(bot.cash, 2), reason=reason)
        bot.cash = 0.0

    def clone(self, parent: Bot, profit: float) -> Bot | None:
        """Eltern-Bot gibt einen Teil seines Tagesgewinns als Startkapital an den Klon."""
        amount = profit * parent.genome.clone_share
        if amount < self.config.min_clone_capital:
            self._log("clone_skipped", bot=parent.bot_id, reason="Gewinn zu klein", amount=round(amount, 2))
            return None
        child_id = self._new_id()
        parent.cash -= amount
        child = Bot(
            bot_id=child_id,
            genome=parent.genome.mutate(self.rng, self.config.mutation_rate),
            cash=amount,
            generation=parent.generation + 1,
            parent_id=parent.bot_id,
            born_day=self.day,
        )
        parent.children.append(child_id)
        self.bots[child_id] = child
        self.card.record_transfer(amount, parent.bot_id, child_id, self.day, "Klon-Startkapital")
        self._log("clone", parent=parent.bot_id, child=child_id, capital=round(amount, 2),
                  generation=child.generation, genome=child.genome.to_dict())
        return child

    def _respawn(self) -> int:
        """Startet neue Zufalls-Bots mit dem, was noch auf der Karte ist."""
        n = max(1, self.config.initial_bots)
        share = min(self.config.start_capital, self.card.balance) / n
        if share < self.config.min_clone_capital:
            return 0
        for _ in range(n):
            self._spawn_from_card(Genome.random(self.rng), share)
        return n

    def run_day(self) -> DaySummary:
        if self.kill_switch_active():
            for bot in self.alive_bots:
                self.shutdown(bot, "Not-Aus")
            return self._summarize(0, 0, 0.0, "Not-Aus (Kill-Switch-Datei gefunden)")

        self.day += 1
        prices = self.market.next_day()
        results: list[tuple[Bot, DayResult]] = [
            (bot, bot.trade_day(prices, self.config.fee_rate)) for bot in self.alive_bots
        ]

        killed = born = 0
        winners: list[tuple[Bot, DayResult]] = []
        for bot, res in results:
            if res.profit > self.config.clone_threshold:
                winners.append((bot, res))
            else:
                self.shutdown(bot, f"nicht profitabel ({res.profit:+.2f} €)")
                killed += 1

        # Die Besten dürfen zuerst klonen, falls das Bot-Limit greift.
        winners.sort(key=lambda br: br[1].profit, reverse=True)
        for bot, res in winners:
            if len(self.alive_bots) >= self.config.max_bots:
                self._log("clone_skipped", bot=bot.bot_id, reason="max_bots erreicht")
                continue
            if self.clone(bot, res.profit):
                born += 1

        if not self.alive_bots and self.config.respawn_from_reserve:
            born += self._respawn()

        best = max((r.profit for _, r in results), default=0.0)
        return self._summarize(born, killed, best, None if self.alive_bots else "alle Bots abgeschaltet")

    def _summarize(self, born: int, killed: int, best: float, stopped: str | None) -> DaySummary:
        s = DaySummary(
            day=self.day,
            regime=self.market.regime.name,
            alive=len(self.alive_bots),
            born=born,
            killed=killed,
            total_equity=self.total_equity,
            card_reserve=self.card.balance,
            best_profit=best,
            stopped_reason=stopped,
        )
        self.summaries.append(s)
        return s

    def run(self, days: int, on_day=None) -> list[DaySummary]:
        for _ in range(days):
            summary = self.run_day()
            if on_day:
                on_day(summary)
            if summary.stopped_reason:
                break
        return self.summaries

    # --- Auswertung --------------------------------------------------------

    def leaderboard(self, n: int = 10) -> list[Bot]:
        return sorted(self.alive_bots, key=lambda b: b.cash, reverse=True)[:n]

    def save_report(self, path: str) -> None:
        report = {
            "config": asdict(self.config),
            "days": [asdict(s) for s in self.summaries],
            "bots": [
                {
                    "id": b.bot_id,
                    "parent": b.parent_id,
                    "generation": b.generation,
                    "born_day": b.born_day,
                    "died_day": b.died_day,
                    "alive": b.alive,
                    "cash": round(b.cash, 2),
                    "children": b.children,
                    "genome": b.genome.to_dict(),
                }
                for b in self.bots.values()
            ],
            "events": self.events,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
