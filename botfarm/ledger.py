"""Die Karte: zentrales Konto, von dem alle Bots ihr Kapital bekommen.

Jede Geldbewegung wird protokolliert, damit nachvollziehbar bleibt, woher
jeder Euro kommt und wohin er geht. Geld wird nie erzeugt oder vernichtet,
außer durch Handelsgewinne/-verluste der Bots.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class InsufficientFunds(Exception):
    pass


@dataclass
class Transaction:
    day: int
    kind: str
    amount: float
    source: str
    target: str
    note: str = ""


@dataclass
class Card:
    """Konto mit nicht zugeteiltem Guthaben (Reserve) und Buchungsprotokoll."""

    balance: float
    transactions: list[Transaction] = field(default_factory=list)

    def withdraw(self, amount: float, bot_id: str, day: int, note: str = "") -> float:
        if amount <= 0:
            raise ValueError("Betrag muss positiv sein")
        if amount > self.balance + 1e-9:
            raise InsufficientFunds(f"Karte hat nur {self.balance:.2f} €, angefragt {amount:.2f} €")
        self.balance -= amount
        self.transactions.append(Transaction(day, "allocate", amount, "card", bot_id, note))
        return amount

    def deposit(self, amount: float, bot_id: str, day: int, note: str = "") -> None:
        if amount < 0:
            raise ValueError("Betrag darf nicht negativ sein")
        self.balance += amount
        self.transactions.append(Transaction(day, "return", amount, bot_id, "card", note))

    def record_transfer(self, amount: float, source: str, target: str, day: int, note: str = "") -> None:
        """Bot-zu-Bot-Übertrag (z.B. Eltern-Bot finanziert seinen Klon)."""
        self.transactions.append(Transaction(day, "transfer", amount, source, target, note))
