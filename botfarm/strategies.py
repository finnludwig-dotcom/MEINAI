"""Handelsstrategien als "Genom".

Ein Klon erbt das Genom seines Eltern-Bots mit kleinen Mutationen. So
entstehen über die Generationen Varianten; unprofitable werden abgeschaltet.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, replace

KINDS = ("momentum", "mean_reversion", "breakout")

# (min, max) pro Parameter
BOUNDS = {
    "lookback": (5, 120),
    "entry": (0.0005, 0.03),
    "exit": (0.0, 0.02),
    "exposure": (0.05, 1.0),
    "stop_loss": (0.002, 0.05),
    "take_profit": (0.002, 0.08),
    "clone_share": (0.1, 1.0),
}


def _clamp(name: str, value: float) -> float:
    lo, hi = BOUNDS[name]
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class Genome:
    kind: str = "momentum"
    lookback: int = 30
    entry: float = 0.003
    exit: float = 0.001
    exposure: float = 0.5
    stop_loss: float = 0.01
    take_profit: float = 0.02
    clone_share: float = 0.5  # Anteil des Tagesgewinns, den der Bot seinem Klon mitgibt

    @classmethod
    def random(cls, rng: random.Random) -> Genome:
        def u(name: str) -> float:
            return rng.uniform(*BOUNDS[name])

        return cls(
            kind=rng.choice(KINDS),
            lookback=int(u("lookback")),
            entry=u("entry"),
            exit=u("exit"),
            exposure=u("exposure"),
            stop_loss=u("stop_loss"),
            take_profit=u("take_profit"),
            clone_share=u("clone_share"),
        )

    def mutate(self, rng: random.Random, rate: float = 0.15, kind_switch_prob: float = 0.05) -> Genome:
        """Kopie mit multiplikativem Rauschen (±rate) auf allen Parametern."""

        def jitter(name: str, value: float) -> float:
            return _clamp(name, value * (1.0 + rng.gauss(0.0, rate)))

        kind = rng.choice(KINDS) if rng.random() < kind_switch_prob else self.kind
        return replace(
            self,
            kind=kind,
            lookback=int(round(jitter("lookback", self.lookback))),
            entry=jitter("entry", self.entry),
            exit=jitter("exit", max(self.exit, 1e-4)),
            exposure=jitter("exposure", self.exposure),
            stop_loss=jitter("stop_loss", self.stop_loss),
            take_profit=jitter("take_profit", self.take_profit),
            clone_share=jitter("clone_share", self.clone_share),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def target_exposure(genome: Genome, prices: list[float], t: int, in_position: bool,
                    entry_price: float | None, prefix: list[float]) -> float:
    """Gewünschter Anteil des Kapitals im Markt zum Tick t (0 = alles Cash). Nur Long, kein Hebel."""
    price = prices[t]

    # Risikomanagement hat Vorrang
    if in_position and entry_price:
        change = price / entry_price - 1.0
        if change <= -genome.stop_loss or change >= genome.take_profit:
            return 0.0

    if t < genome.lookback:
        return genome.exposure if in_position else 0.0

    ret = price / prices[t - genome.lookback] - 1.0

    if genome.kind == "momentum":
        if not in_position and ret > genome.entry:
            return genome.exposure
        if in_position and ret < -genome.exit:
            return 0.0

    elif genome.kind == "mean_reversion":
        mean = (prefix[t] - prefix[t - genome.lookback]) / genome.lookback
        dev = price / mean - 1.0
        if not in_position and dev < -genome.entry:
            return genome.exposure
        if in_position and dev > genome.exit:
            return 0.0

    elif genome.kind == "breakout":
        window = prices[t - genome.lookback:t]
        high = max(window)
        low = min(window)
        if not in_position and price > high * (1.0 + genome.entry):
            return genome.exposure
        if in_position and price < low * (1.0 + genome.exit):
            return 0.0

    return genome.exposure if in_position else 0.0
