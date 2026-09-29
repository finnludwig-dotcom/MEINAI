"""Kommandozeile: python -m botfarm --days 30 --seed 42"""

from __future__ import annotations

import argparse

from .colony import Colony, ColonyConfig, DaySummary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="botfarm", description="Selbstklonende Trading-Bots (Paper-Trading).")
    p.add_argument("--days", type=int, default=30, help="Anzahl simulierter Handelstage")
    p.add_argument("--seed", type=int, default=None, help="Zufalls-Seed für reproduzierbare Läufe")
    p.add_argument("--capital", type=float, default=50.0, help="Guthaben auf der Karte / Startkapital")
    p.add_argument("--clone-threshold", type=float, default=0.0,
                   help="Mindest-Tagesgewinn in € zum Überleben/Klonen (50 = Kapital verdoppeln)")
    p.add_argument("--min-clone-capital", type=float, default=1.0)
    p.add_argument("--fee", type=float, default=0.001, help="Gebühr pro Trade (0.001 = 0,1 %%)")
    p.add_argument("--max-bots", type=int, default=100, help="Sicherheitsgrenze für gleichzeitige Bots")
    p.add_argument("--initial-bots", type=int, default=1, help="Startkapital auf so viele Bots verteilen")
    p.add_argument("--respawn", action="store_true",
                   help="Neuen Bot aus der Kartenreserve starten, wenn alle abgeschaltet sind")
    p.add_argument("--report", type=str, default=None, help="JSON-Report mit allen Bots und Ereignissen")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    colony = Colony(ColonyConfig(
        start_capital=args.capital,
        clone_threshold=args.clone_threshold,
        min_clone_capital=args.min_clone_capital,
        fee_rate=args.fee,
        max_bots=args.max_bots,
        initial_bots=args.initial_bots,
        respawn_from_reserve=args.respawn,
        seed=args.seed,
    ))

    def show(s: DaySummary) -> None:
        if args.quiet:
            return
        print(f"Tag {s.day:3d} | {s.regime:8s} | aktiv {s.alive:3d} | +{s.born:3d} neu | "
              f"-{s.killed:3d} abgeschaltet | Gesamt {s.total_equity:9.2f} € | "
              f"Karte {s.card_reserve:8.2f} € | bester Tag {s.best_profit:+8.2f} €")
        if s.stopped_reason:
            print(f"Stopp: {s.stopped_reason}")

    colony.run(args.days, on_day=show)

    print()
    print(f"Ergebnis nach {colony.day} Tagen: {len(colony.alive_bots)} aktive Bots, "
          f"{len(colony.bots)} Bots insgesamt erzeugt, Gesamtkapital {colony.total_equity:.2f} € "
          f"(Start {args.capital:.2f} €, {colony.total_equity - args.capital:+.2f} €)")
    top = colony.leaderboard()
    if top:
        print("\nTop-Bots:")
        for b in top:
            print(f"  {b.bot_id}  Gen {b.generation:2d}  {b.cash:9.2f} €  {b.genome.kind:14s}  "
                  f"Eltern {b.parent_id or '-'}")
    if args.report:
        colony.save_report(args.report)
        print(f"\nReport gespeichert: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
