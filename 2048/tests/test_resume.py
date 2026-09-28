import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.players import Player  # noqa: E402
from common.resume import ResumeError, find_finished, find_resumable, read_records  # noqa: E402
from common.runner import run_game  # noqa: E402


class StatePlayer(Player):
    """Deterministic in the board (not in call count), so a split game replays identically.
    Answers garbage on the first try whenever the board sum is divisible by 7.
    stop_after: set the stop event once this many moves were decided."""
    name = "state"
    model_id = "fake/state"

    def __init__(self, stop=None, stop_after=None):
        self.stop, self.stop_after, self.decided = stop, stop_after, 0

    def decide(self, board, score, legal, feedback=None):
        total = sum(map(sum, board))
        if feedback is None and total % 7 == 0:
            return {"move": None, "raw": "??", "latency_s": 0.25, "cost": 0.001}
        self.decided += 1
        if self.stop_after and self.decided >= self.stop_after:
            self.stop.set()
        return {"move": legal[total % len(legal)], "raw": "", "latency_s": 0.1, "cost": 0.001}


def moves_of(path):
    return [r for r in read_records(path) if r["type"] == "move"]


def play(tmp, stop_after=None, **kw):
    stop = threading.Event()
    return run_game(StatePlayer(stop, stop_after), tmp, seed=5, stop=stop, **kw)


def test_resumed_game_equals_uninterrupted_game(tmp_path):
    _, full = play(tmp_path / "a", max_moves=150, budget_usd=100)

    path, cut = play(tmp_path / "b", stop_after=40, max_moves=150, budget_usd=100)
    assert cut["reason"] == "interrupted" and cut["moves"] == 40
    assert find_resumable(tmp_path / "b", seed=5) == path

    stop = threading.Event()
    path2, resumed = run_game(StatePlayer(stop), tmp_path / "b", seed=5, stop=stop,
                              max_moves=150, budget_usd=100, resume_path=path)
    assert path2 == path  # same file, continued

    a, b = moves_of(next((tmp_path / "a").glob("*.jsonl"))), moves_of(path)
    assert [m["move"] for m in a] == [m["move"] for m in b]
    assert [m["board"] for m in a] == [m["board"] for m in b]
    for k in ("reason", "moves", "score", "max_tile", "failed_attempts", "milestones", "board"):
        assert resumed[k] == full[k], k
    assert resumed["t_model"] == pytest.approx(full["t_model"])
    assert resumed["cost"] == pytest.approx(full["cost"])
    assert full["failed_attempts"] > 0  # the carry-over was actually exercised

    types = [r["type"] for r in read_records(path)]
    assert types.count("resume") == 1 and types.count("end") == 1 and types[-1] == "end"


def test_resume_after_hard_kill_with_half_written_line(tmp_path):
    path, _ = play(tmp_path, stop_after=30, max_moves=80, budget_usd=100)
    lines = path.read_text().splitlines()[:-1]  # drop the end record, as if killed
    path.write_text("\n".join(lines) + '\n{"type": "mo')  # and cut mid-write
    assert find_resumable(tmp_path, seed=5) == path

    stop = threading.Event()
    _, s = run_game(StatePlayer(stop), tmp_path, seed=5, stop=stop, max_moves=80, budget_usd=100, resume_path=path)
    assert s["moves"] == 80 and s["reason"] == "max_moves"
    for line in path.read_text().splitlines():
        json.loads(line)  # no broken lines left behind
    assert [r for r in read_records(path) if r["type"] == "resume"][0]["previous_end"] == "no end record"


def test_budget_stop_can_resume_with_higher_budget(tmp_path):
    path, s = play(tmp_path, budget_usd=0.02, max_moves=500)
    assert s["reason"] == "budget"
    stop = threading.Event()
    _, s2 = run_game(StatePlayer(stop), tmp_path, seed=5, stop=stop, budget_usd=0.05, max_moves=500,
                     resume_path=find_resumable(tmp_path, seed=5))
    assert s2["reason"] == "budget"
    assert 0.05 <= s2["cost"] < 0.053 and s2["moves"] > s["moves"]  # budget covers the whole game


def test_finished_game_is_not_resumable(tmp_path):
    _, s = play(tmp_path, max_moves=20, budget_usd=100)
    assert s["reason"] == "max_moves"
    assert find_resumable(tmp_path, seed=5) is None
    assert find_resumable(tmp_path, seed=6) is None  # other seeds have nothing


def test_tampered_log_is_refused_and_left_untouched(tmp_path):
    path, _ = play(tmp_path, stop_after=10, max_moves=50, budget_usd=100)
    recs = read_records(path)
    recs[5]["board"][0][0] = 4096
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))
    before = path.read_text()
    with pytest.raises(ResumeError, match="diverges"):
        run_game(StatePlayer(), tmp_path, seed=5, resume_path=path)
    assert path.read_text() == before


def test_find_finished_ignores_unfinished_games(tmp_path):
    play(tmp_path, stop_after=5, max_moves=50, budget_usd=100)  # interrupted: not finished
    assert find_finished(tmp_path, seed=5) is None
    path, s = play(tmp_path, max_moves=20, budget_usd=100)
    assert s["reason"] == "max_moves" and find_finished(tmp_path, seed=5) == path
    assert find_finished(tmp_path, seed=6) is None
