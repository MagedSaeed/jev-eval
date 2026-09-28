"""Non-LLM reference players: they show what a score is worth without any intelligence.

Each baseline is a Player like any model, so it goes through the same runner, logs and viewer.
They are deterministic: the same seed always gives the same game, and resuming is exact.

Timing is simulated: a policy decides in microseconds, which would make a baseline finish before
the first LLM move on the viewer's model-time clock. So every move is logged as a fixed
SIM_LATENCY_S (0.25s: a bit faster than the fastest model, jev at ~0.37s). The real compute time
is logged next to it as "compute_s".
"""

import random
import time

from .game import _apply
from .players import Player

FIXED_ORDER = ("left", "down", "right", "up")
SIM_LATENCY_S = 0.25
TIMING_NOTE = (f"Moves are timed at a fixed {SIM_LATENCY_S}s (simulated), a bit faster than the fastest "
               "model, so it plays at a watchable pace on the same clock.")


class BaselinePlayer(Player):
    description = ""
    kind = "baseline"      # "solver" marks a real algorithm (a ceiling), which the viewer styles apart
    display_name = None    # shown instead of the folder name, e.g. "Expectimax search"

    def __init__(self, name):
        self.name = name

    def describe(self):
        return {"model_id": None, "adapter": "baseline", "kind": self.kind, "display_name": self.display_name,
                "description": f"{self.description} {TIMING_NOTE}", "sim_latency_s": SIM_LATENCY_S}

    def choose(self, board, legal):
        raise NotImplementedError

    def decide(self, board, score, legal, feedback=None):
        t0 = time.perf_counter()
        move = self.choose(board, legal)
        return {"move": move, "raw": move, "latency_s": SIM_LATENCY_S, "cost": 0.0,
                "extra": {"compute_s": round(time.perf_counter() - t0, 6)}}


class RandomPlayer(BaselinePlayer):
    description = ("Picks one of the legal moves uniformly at random. "
                   "The floor: a model below this is worse than not thinking at all.")

    def choose(self, board, legal):
        # seeded from the position (not a running stream), so games replay and resume exactly
        return random.Random(repr(board)).choice(legal)


class FixedOrderPlayer(BaselinePlayer):
    description = ("Always tries left, then down, then right, then up, and plays the first one that "
                   "changes the board. It never looks at the tiles, yet this piles them into the "
                   "bottom-left corner: the classic 2048 strategy in four lines.")

    def choose(self, board, legal):
        return next(m for m in FIXED_ORDER if m in legal)


class GreedyPlayer(BaselinePlayer):
    description = ("Plays the move that scores the most points right now (the biggest merges), "
                   "with no look-ahead. Ties go left, then down, right, up.")

    def choose(self, board, legal):
        return max(legal, key=lambda m: (_apply(board, m)[1], -FIXED_ORDER.index(m)))
