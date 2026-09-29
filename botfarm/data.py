"""Echte historische Kursdaten als Markt für die Kolonie.

Quelle: öffentliche Minutendaten von data.binance.vision (kein Konto, kein
API-Schlüssel nötig). Die Dateien werden lokal zwischengespeichert.
"""

from __future__ import annotations

import csv
import io
import os
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta

BASE_URL = "https://data.binance.vision/data/spot/daily/klines/{symbol}/1m/{symbol}-1m-{day}.zip"


def _download_day(symbol: str, day: date, cache_dir: str) -> list[float]:
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{symbol}-1m-{day.isoformat()}.zip")
    if not os.path.exists(path):
        url = BASE_URL.format(symbol=symbol, day=day.isoformat())
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    data = resp.read()
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(2 ** (attempt + 1))
        with open(path, "wb") as f:
            f.write(data)
    with zipfile.ZipFile(path) as zf:
        with zf.open(zf.namelist()[0]) as f:
            rows = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            return [float(row[4]) for row in rows if row and row[0].isdigit()]  # Schlusskurs


def load_binance_days(symbol: str, start: date, days: int, cache_dir: str = ".cache/klines",
                      resample_minutes: int = 5) -> list[tuple[date, list[float]]]:
    """Lädt `days` Handelstage ab `start`; jeder Tag als Liste von Schlusskursen."""
    out = []
    for i in range(days):
        day = start + timedelta(days=i)
        closes = _download_day(symbol, day, cache_dir)
        out.append((day, closes[::resample_minutes]))
    return out


@dataclass
class _Label:
    name: str


class HistoricalMarket:
    """Spielt echte Tage nacheinander ab. Gibt None zurück, wenn die Daten zu Ende sind."""

    def __init__(self, days: list[tuple[date, list[float]]], symbol: str = ""):
        self._days = days
        self._index = 0
        self.symbol = symbol
        self.regime = _Label("-")

    def next_day(self) -> list[float] | None:
        if self._index >= len(self._days):
            return None
        day, prices = self._days[self._index]
        self._index += 1
        self.regime = _Label(day.isoformat())
        return prices
