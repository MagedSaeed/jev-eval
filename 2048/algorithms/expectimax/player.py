"""Expectimax search, by Robert Xiao (nneonneo/2048-ai), called through ctypes.

Build the library once with algorithms/expectimax/build.sh. The board goes over as a 64-bit
integer of tile exponents, 4 bits per cell in row-major order; moves are 0-3 = up, down, left, right
(checked against common/game.py in tests/test_baselines.py).
"""

import ctypes
from pathlib import Path

from common.baselines import BaselinePlayer
from common.players import PlayerUnavailable

LIB = Path(__file__).resolve().parent / "2048-ai" / "bin" / "2048.so"
MOVES = ("up", "down", "left", "right")


def load_library():
    if not LIB.is_file():
        raise PlayerUnavailable(f"expectimax needs its library; build it with {LIB.parents[2] / 'build.sh'}")
    lib = ctypes.CDLL(str(LIB))
    lib.init_tables()
    lib.find_best_move.argtypes = [ctypes.c_uint64]
    lib.find_best_move.restype = ctypes.c_int
    lib.execute_move.argtypes = [ctypes.c_int, ctypes.c_uint64]
    lib.execute_move.restype = ctypes.c_uint64
    return lib


def encode(board):
    """Rows of tile values -> 2048-ai's bitboard (a 4-bit exponent per cell, row-major)."""
    n = 0
    for i, v in enumerate(v for row in board for v in row):
        n |= (v.bit_length() - 1 if v else 0) << (4 * i)
    return n


class ExpectimaxPlayer(BaselinePlayer):
    kind = "solver"
    stop_at_tile = 2048  # the goal of the game; left alone it keeps going
    display_name = "Expectimax search"
    description = (
        "Looks several moves ahead, averaging over every place the next tile can appear (expectimax), "
        "and scores positions with a hand-tuned heuristic: empty cells, monotonic rows, merges, and big "
        "tiles kept on an edge. A search algorithm, not a naive bot: it is here as the ceiling. "
        "Method and code by Robert Xiao (nneonneo), 2048-ai, github.com/nneonneo/2048-ai (MIT), described "
        "in his StackOverflow answer \"What is the optimal algorithm for the game 2048?\" (2014). "
        "Its games stop once it reaches the 2048 tile, the goal of the game; left alone it keeps going.")
    citation = ("Robert Xiao (nneonneo). 2048-ai: expectimax AI for 2048. https://github.com/nneonneo/2048-ai, 2014. "
                "Algorithm: https://stackoverflow.com/a/22498940")

    def __init__(self, name):
        super().__init__(name)
        self.lib = load_library()

    def describe(self):
        return {**super().describe(), "citation": self.citation, "stop_at_tile": self.stop_at_tile}

    def choose(self, board, legal):
        move = self.lib.find_best_move(encode(board))
        return MOVES[move] if 0 <= move < 4 else None


def make_player():
    return ExpectimaxPlayer(name="expectimax")
