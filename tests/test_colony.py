import os
import random
import tempfile
import unittest

from botfarm import Bot, Card, Colony, ColonyConfig, Genome, SimulatedMarket
from botfarm.ledger import InsufficientFunds
from botfarm.market import Regime


class TrendMarket:
    """Deterministischer Markt: Kurs steigt/fällt jeden Tick um einen festen Faktor."""

    def __init__(self, step: float, ticks: int = 200):
        self.step = step
        self.ticks = ticks
        self.price = 100.0
        self.regime = Regime("test", 0.0, 0.0)

    def next_day(self):
        prices = [self.price]
        for _ in range(self.ticks):
            self.price *= 1.0 + self.step
            prices.append(self.price)
        return prices


MOMENTUM = Genome(kind="momentum", lookback=5, entry=0.0005, exit=0.0, exposure=1.0,
                  stop_loss=0.05, take_profit=0.08, clone_share=0.5)


def make_colony(step: float, **cfg) -> Colony:
    cfg.setdefault("kill_switch_file", None)
    cfg.setdefault("fee_rate", 0.0)
    return Colony(ColonyConfig(seed=1, **cfg), market=TrendMarket(step), initial_genomes=[MOMENTUM])


class CardTests(unittest.TestCase):
    def test_withdraw_and_deposit(self):
        card = Card(50.0)
        card.withdraw(30.0, "bot-1", 0)
        self.assertAlmostEqual(card.balance, 20.0)
        card.deposit(10.0, "bot-1", 1)
        self.assertAlmostEqual(card.balance, 30.0)
        self.assertEqual([t.kind for t in card.transactions], ["allocate", "return"])

    def test_cannot_overdraw(self):
        with self.assertRaises(InsufficientFunds):
            Card(50.0).withdraw(50.01, "bot-1", 0)


class GenomeTests(unittest.TestCase):
    def test_mutation_stays_in_bounds(self):
        rng = random.Random(0)
        g = Genome.random(rng)
        for _ in range(500):
            g = g.mutate(rng, rate=0.5)
            self.assertGreaterEqual(g.lookback, 5)
            self.assertLessEqual(g.exposure, 1.0)
            self.assertGreaterEqual(g.clone_share, 0.1)
            self.assertLessEqual(g.clone_share, 1.0)


class BotTests(unittest.TestCase):
    def test_positions_closed_at_end_of_day(self):
        bot = Bot("b", MOMENTUM, 50.0)
        res = bot.trade_day(TrendMarket(0.001).next_day(), fee_rate=0.001)
        self.assertGreater(res.trades, 0)
        self.assertEqual(res.trades % 2, 0)  # jeder Kauf wurde wieder verkauft
        self.assertGreater(res.end_equity, 50.0)

    def test_no_trades_means_no_profit(self):
        bot = Bot("b", MOMENTUM, 50.0)
        res = bot.trade_day([100.0] * 50, fee_rate=0.001)
        self.assertEqual(res.trades, 0)
        self.assertEqual(res.profit, 0.0)


class ColonyTests(unittest.TestCase):
    def test_profitable_bot_clones_itself_and_funds_clone_from_profit(self):
        colony = make_colony(0.001)
        colony.run_day()
        self.assertEqual(len(colony.alive_bots), 2)
        parent, child = colony.bots["bot-0001"], colony.bots["bot-0002"]
        self.assertEqual(child.parent_id, parent.bot_id)
        self.assertEqual(child.generation, 1)
        self.assertGreaterEqual(parent.cash, 50.0)  # Eltern-Bot gibt nur Gewinn ab
        self.assertAlmostEqual(parent.cash + child.cash, parent.history[-1])

    def test_population_grows_in_good_market(self):
        colony = make_colony(0.001)
        colony.run(5)
        self.assertGreater(len(colony.alive_bots), 4)
        self.assertGreater(colony.total_equity, 50.0)

    def test_losing_bots_are_shut_down_and_capital_returns_to_card(self):
        colony = make_colony(-0.001, fee_rate=0.001)
        summary = colony.run_day()
        self.assertEqual(len(colony.alive_bots), 0)
        self.assertEqual(summary.stopped_reason, "alle Bots abgeschaltet")
        self.assertAlmostEqual(colony.card.balance, colony.total_equity)
        self.assertLessEqual(colony.card.balance, 50.0)

    def test_break_even_is_not_enough(self):
        colony = make_colony(0.0)
        colony.run_day()
        self.assertEqual(len(colony.alive_bots), 0)

    def test_clone_threshold(self):
        colony = make_colony(0.001, clone_threshold=1000.0)
        colony.run_day()
        self.assertEqual(len(colony.alive_bots), 0)

    def test_max_bots_is_respected(self):
        colony = make_colony(0.001, max_bots=3)
        colony.run(10)
        self.assertLessEqual(len(colony.alive_bots), 3)

    def test_kill_switch_stops_everything(self):
        with tempfile.TemporaryDirectory() as d:
            stop = os.path.join(d, "STOP")
            colony = make_colony(0.001, kill_switch_file=stop)
            colony.run(2)
            open(stop, "w").close()
            summary = colony.run_day()
            self.assertIn("Not-Aus", summary.stopped_reason)
            self.assertEqual(len(colony.alive_bots), 0)
            self.assertAlmostEqual(colony.card.balance, colony.total_equity)

    def test_money_is_conserved(self):
        """Gesamtkapital ändert sich nur durch Handelsergebnisse, nie durch Klonen/Abschalten."""
        colony = Colony(ColonyConfig(seed=3, initial_bots=5, respawn_from_reserve=True, kill_switch_file=None))
        for _ in range(40):
            before = colony.total_equity
            alive_before = {b.bot_id: b.cash for b in colony.alive_bots}
            colony.run_day()
            pnl = sum(colony.bots[i].history[-1] - cash for i, cash in alive_before.items())
            self.assertAlmostEqual(colony.total_equity, before + pnl, places=6)

    def test_simulated_market_is_reproducible(self):
        self.assertEqual(SimulatedMarket(seed=5).next_day(), SimulatedMarket(seed=5).next_day())

    def test_report_is_written(self):
        colony = make_colony(0.001)
        colony.run(3)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "report.json")
            colony.save_report(path)
            self.assertGreater(os.path.getsize(path), 100)


if __name__ == "__main__":
    unittest.main()
