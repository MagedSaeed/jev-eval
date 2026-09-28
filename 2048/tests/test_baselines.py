import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.baselines import FixedOrderPlayer, GreedyPlayer, RandomPlayer  # noqa: E402
from common.runner import run_game  # noqa: E402

BASELINES = [RandomPlayer("random"), FixedOrderPlayer("fixed-order"), GreedyPlayer("greedy")]


def moves_of(path):
    return [r["move"] for r in map(json.loads, path.read_text().splitlines()) if r["type"] == "move"]


def test_baselines_play_whole_games_deterministically(tmp_path):
    for player in BASELINES:
        a, sa = run_game(player, tmp_path / player.name / "a", seed=1)
        b, sb = run_game(player, tmp_path / player.name / "b", seed=1)
        assert sa["reason"] == "game_over" and sa["failed_attempts"] == 0 and sa["cost"] == 0
        assert moves_of(a) == moves_of(b) and sa["score"] == sb["score"]
        assert sa["t_model"] == round(0.25 * sa["moves"], 4)  # fixed simulated latency per move
        meta = json.loads(a.read_text().splitlines()[0])
        assert meta["adapter"] == "baseline" and meta["description"]


def test_fixed_order_prefers_left_then_down():
    board = [[2, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    assert FixedOrderPlayer("f").choose(board, ["down", "right"]) == "down"
    assert FixedOrderPlayer("f").choose(board, ["up", "left", "down"]) == "left"


def test_greedy_takes_the_biggest_merge():
    # left/right merge the 8s (16 points); up/down merge the 2s (4 points)
    board = [[8, 8, 0, 0], [2, 0, 0, 0], [2, 0, 0, 0], [0, 0, 0, 0]]
    assert GreedyPlayer("g").choose(board, ["up", "down", "left", "right"]) == "left"


def test_random_only_plays_legal_moves():
    board = [[2, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    assert all(RandomPlayer("r").choose(board, ["down"]) == "down" for _ in range(5))


def test_expectimax_matches_our_engine():
    """2048-ai's board encoding and move numbering must agree with common/game.py exactly."""
    import importlib.util
    import random

    import pytest

    from common.game import _apply
    from common.players import PlayerUnavailable

    path = Path(__file__).resolve().parents[1] / "algorithms" / "expectimax" / "player.py"
    spec = importlib.util.spec_from_file_location("expectimax_player", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        lib = mod.load_library()
    except PlayerUnavailable:
        pytest.skip("expectimax library not built (algorithms/expectimax/build.sh)")

    def decode(n):
        return [[(1 << e) if (e := (n >> (4 * (r * 4 + c))) & 15) else 0 for c in range(4)] for r in range(4)]

    rng = random.Random(0)
    for _ in range(300):
        board = [[rng.choice([0, 0, 2, 4, 8, 16, 32]) for _ in range(4)] for _ in range(4)]
        assert decode(mod.encode(board)) == board
        for i, move in enumerate(mod.MOVES):
            assert decode(lib.execute_move(i, mod.encode(board))) == _apply(board, move)[0]
    board = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 4]]
    assert mod.ExpectimaxPlayer("e").choose(board, ["up", "down", "left", "right"]) in mod.MOVES
