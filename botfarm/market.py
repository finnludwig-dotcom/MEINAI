"""Simulierter Markt: ein Handelstag besteht aus vielen Kursticks.

Der Kurs folgt einer geometrischen Brownschen Bewegung mit wechselnden
Regimen (Aufwärts-, Abwärts-, Seitwärtsphasen). Deterministisch per Seed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class Regime:
    name: str
    drift: float  # erwartete Rendite pro Tag
    vol: float  # Volatilität pro Tag


REGIMES = [
    Regime("bull", 0.004, 0.02),
    Regime("bear", -0.004, 0.025),
    Regime("sideways", 0.0, 0.012),
    Regime("volatile", 0.0, 0.045),
]


class SimulatedMarket:
    def __init__(self, seed: int | None = None, start_price: float = 100.0, ticks_per_day: int = 390,
                 regime_switch_prob: float = 0.15):
        self.rng = random.Random(seed)
        self.price = start_price
        self.ticks_per_day = ticks_per_day
        self.regime_switch_prob = regime_switch_prob
        self.regime = self.rng.choice(REGIMES)

    def next_day(self) -> list[float]:
        """Liefert die Kursticks des nächsten Handelstags (inkl. Eröffnungskurs)."""
        if self.rng.random() < self.regime_switch_prob:
            self.regime = self.rng.choice(REGIMES)
        n = self.ticks_per_day
        dt = 1.0 / n
        mu, sigma = self.regime.drift, self.regime.vol
        prices = [self.price]
        for _ in range(n):
            shock = self.rng.gauss(0.0, 1.0)
            self.price *= math.exp((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * shock)
            prices.append(self.price)
        return prices
