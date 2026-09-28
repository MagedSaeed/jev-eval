import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.players import Player  # noqa: E402
from common.runner import run_game  # noqa: E402


class FakePlayer(Player):
    """Answers garbage every 5th call, otherwise the first legal move; 0.5s per call."""
    name = "fake"
    model_id = "fake/model"

    def __init__(self):
        self.calls = 0

    def decide(self, board, score, legal, feedback=None):
        self.calls += 1
        move = None if self.calls % 5 == 0 else legal[0]
        return {"move": move, "raw": "??", "latency_s": 0.5, "cost": 0.001, "extra": {"k": 1}}


def test_run_game_writes_meta_moves_end(tmp_path):
    path, summary = run_game(FakePlayer(), tmp_path, seed=3, max_moves=40)
    recs = [json.loads(line) for line in path.read_text().splitlines()]
    assert recs[0]["type"] == "meta" and recs[0]["model"] == "fake"
    assert recs[-1]["type"] == "end" and recs[-1] == summary
    moves = [r for r in recs if r["type"] == "move"]
    assert len(moves) == summary["moves"] <= 40
    assert summary["failed_attempts"] > 0
    # retried moves are charged for both attempts
    assert any(m["attempts"] == 2 and m["latency_s"] == 1.0 for m in moves)
    assert moves[-1]["t_model"] == summary["t_model"]
    assert moves[0]["k"] == 1


def test_budget_stops_game(tmp_path):
    _, summary = run_game(FakePlayer(), tmp_path, seed=0, budget_usd=0.005)
    assert summary["reason"] == "budget"


def test_invalid_answers_forfeit(tmp_path):
    class Stubborn(FakePlayer):
        def decide(self, *a, **k):
            return {"move": None, "raw": "hmm", "latency_s": 0.1, "cost": 0}

    _, summary = run_game(Stubborn(), tmp_path, max_attempts=3)
    assert summary["reason"] == "invalid_moves" and summary["moves"] == 0


def test_stop_at_tile_ends_the_game(tmp_path):
    class Stopper(FakePlayer):
        stop_at_tile = 16

        def decide(self, board, score, legal, feedback=None):
            return {"move": legal[0], "raw": legal[0], "latency_s": 0.1, "cost": 0}

    path, summary = run_game(Stopper(), tmp_path, seed=0)
    moves = [r for r in map(json.loads, path.read_text().splitlines()) if r["type"] == "move"]
    assert summary["reason"] == "target_tile" and summary["max_tile"] >= 16
    assert moves[-1]["max_tile"] >= 16 and all(m["max_tile"] < 16 for m in moves[:-1])  # stops right away
