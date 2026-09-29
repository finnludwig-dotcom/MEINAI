"""Ein einzelner Trading-Bot mit eigenem Kapital."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import accumulate

from .strategies import Genome, target_exposure


@dataclass
class DayResult:
    bot_id: str
    start_equity: float
    end_equity: float
    trades: int

    @property
    def profit(self) -> float:
        return self.end_equity - self.start_equity


@dataclass
class Bot:
    bot_id: str
    genome: Genome
    cash: float
    generation: int = 0
    parent_id: str | None = None
    born_day: int = 0
    alive: bool = True
    died_day: int | None = None
    children: list[str] = field(default_factory=list)
    history: list[float] = field(default_factory=list)  # Kapital am Ende jedes Tages

    def trade_day(self, prices: list[float], fee_rate: float) -> DayResult:
        """Handelt einen Tag und schließt am Ende alle Positionen (Daytrading).

        Dadurch ist das Kapital am Tagesende eindeutig in Euro messbar.
        """
        start = self.cash
        units = 0.0
        entry_price: float | None = None
        trades = 0

        prefix = list(accumulate(prices, initial=0.0))
        last = len(prices) - 1
        for t, price in enumerate(prices):
            equity = self.cash + units * price
            target = 0.0 if t == last else target_exposure(
                self.genome, prices, t, units > 0, entry_price, prefix)

            if units == 0 and target > 0:
                spend = equity * target
                fee = spend * fee_rate
                units = (spend - fee) / price
                self.cash -= spend
                entry_price = price
                trades += 1
            elif units > 0 and target == 0:
                proceeds = units * price
                self.cash += proceeds - proceeds * fee_rate
                units = 0.0
                entry_price = None
                trades += 1

        self.history.append(self.cash)
        return DayResult(self.bot_id, start, self.cash, trades)
