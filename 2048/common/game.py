"""Deterministic 2048 engine. Same seed -> same opening board and same RNG stream."""

import random

MOVES = ("up", "down", "left", "right")
SIZE = 4


def slide_row(row):
    """Slide one row to the left, merging each pair at most once. Returns (row, points)."""
    tiles = [v for v in row if v]
    out, points, i = [], 0, 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            out.append(tiles[i] * 2)
            points += tiles[i] * 2
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    return out + [0] * (len(row) - len(out)), points


def _transpose(b):
    return [list(r) for r in zip(*b)]


def _apply(board, move):
    if move in ("left", "right"):
        rows = [r[:] if move == "left" else r[::-1] for r in board]
    else:
        cols = _transpose(board)
        rows = [c[:] if move == "up" else c[::-1] for c in cols]

    moved, points = [], 0
    for r in rows:
        new, p = slide_row(r)
        moved.append(new)
        points += p

    if move in ("right", "down"):
        moved = [r[::-1] for r in moved]
    if move in ("up", "down"):
        moved = _transpose(moved)
    return moved, points


class Game:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.board = [[0] * SIZE for _ in range(SIZE)]
        self.score = 0
        self.moves = 0
        self._spawn()
        self._spawn()

    def _spawn(self):
        empty = [(r, c) for r in range(SIZE) for c in range(SIZE) if not self.board[r][c]]
        if not empty:
            return None
        r, c = self.rng.choice(empty)
        self.board[r][c] = 4 if self.rng.random() < 0.1 else 2
        return (r, c, self.board[r][c])

    def preview(self, move):
        return _apply(self.board, move)

    def legal_moves(self):
        return [m for m in MOVES if self.preview(m)[0] != self.board]

    @property
    def over(self):
        return not self.legal_moves()

    @property
    def max_tile(self):
        return max(max(r) for r in self.board)

    def move(self, move):
        """Apply a move. Returns {'gained', 'spawn'} or None if the move changes nothing."""
        new, points = self.preview(move)
        if new == self.board:
            return None
        self.board = new
        self.score += points
        self.moves += 1
        return {"gained": points, "spawn": self._spawn()}
