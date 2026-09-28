import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.game import Game, slide_row  # noqa: E402


def test_slide_row_merges_once_per_pair():
    assert slide_row([2, 2, 2, 2]) == ([4, 4, 0, 0], 8)
    assert slide_row([2, 2, 4, 0]) == ([4, 4, 0, 0], 4)
    assert slide_row([0, 0, 2, 2]) == ([4, 0, 0, 0], 4)
    assert slide_row([4, 4, 8, 0]) == ([8, 8, 0, 0], 8)
    assert slide_row([2, 4, 8, 16]) == ([2, 4, 8, 16], 0)


def test_new_game_has_two_tiles_and_is_seeded():
    a, b = Game(seed=7), Game(seed=7)
    assert a.board == b.board
    assert sum(1 for r in a.board for v in r if v) == 2


def test_moves_in_all_directions():
    g = Game(seed=0)
    g.board = [[2, 0, 0, 2], [0, 0, 0, 0], [0, 0, 0, 0], [2, 0, 0, 0]]
    assert g.preview("left")[0][0] == [4, 0, 0, 0]
    assert g.preview("right")[0][0] == [0, 0, 0, 4]
    board, gained = g.preview("up")
    assert board[0] == [4, 0, 0, 2] and gained == 4
    board, _ = g.preview("down")
    assert board[3] == [4, 0, 0, 2]


def test_invalid_move_does_not_change_state():
    g = Game(seed=0)
    g.board = [[2, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    assert "up" not in g.legal_moves()
    before = [r[:] for r in g.board]
    assert g.move("up") is None
    assert g.board == before


def test_valid_move_spawns_tile_and_scores():
    g = Game(seed=1)
    g.board = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    result = g.move("left")
    assert result is not None
    assert g.score == 4
    assert g.board[result["spawn"][0]][result["spawn"][1]] in (2, 4)
    assert sum(1 for r in g.board for v in r if v) == 2


def test_game_over_detection():
    g = Game(seed=0)
    g.board = [[2, 4, 2, 4], [4, 2, 4, 2], [2, 4, 2, 4], [4, 2, 4, 2]]
    assert g.legal_moves() == []
    assert g.over
    g.board[0][1] = 2
    assert not g.over


def test_max_tile():
    g = Game(seed=0)
    g.board = [[2, 4096, 0, 0], [0] * 4, [0] * 4, [0] * 4]
    assert g.max_tile == 4096
