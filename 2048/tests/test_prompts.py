import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.prompts import build_messages, parse_move, render_board  # noqa: E402


def test_parse_move_plain_and_noisy():
    assert parse_move("left") == "left"
    assert parse_move("  UP.\n") == "up"
    assert parse_move("I'd go down, actually right") == "right"
    assert parse_move("**Move:** Left") == "left"


def test_parse_move_ignores_think_block_and_garbage():
    assert parse_move("<think>maybe up? no, left</think>down") == "down"
    assert parse_move("upward") is None
    assert parse_move("") is None
    assert parse_move(None) is None


def test_render_board_aligns_columns():
    out = render_board([[0, 2, 0, 0], [0, 0, 128, 0], [0] * 4, [2048, 0, 0, 0]])
    assert out.splitlines()[3] == "2048    .    .    ."


def test_build_messages_includes_legal_moves_and_feedback():
    msgs = build_messages([[2, 0, 0, 0]] + [[0] * 4] * 3, 12, ["down", "right"], feedback="x")
    user = msgs[1]["content"]
    assert "Score: 12" in user and "down, right" in user and "Note: x" in user
