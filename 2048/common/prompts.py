"""Board rendering, the shared chat prompt, and move parsing."""

import re

PROMPT_VERSION = "v1"

RULES = (
    "You are playing the game 2048 on a 4x4 board. Each move slides all tiles in one "
    "direction; two equal tiles that collide merge into their sum. After each move a new "
    "2 or 4 appears in a random empty cell. The game ends when no move changes the board. "
    "Goal: build the largest tile possible (2048 and beyond)."
)
SYSTEM = RULES + "\nReply with exactly one word: up, down, left, or right."

_MOVE_RE = re.compile(r"\b(up|down|left|right)\b", re.IGNORECASE)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def render_board(board):
    width = max(len(str(v)) for r in board for v in r)
    return "\n".join(" ".join(str(v or ".").rjust(width) for v in r) for r in board)


def build_messages(board, score, legal, feedback=None):
    user = (
        f"Score: {score}\nBoard ('.' = empty):\n{render_board(board)}\n\n"
        f"Moves that change the board: {', '.join(legal)}\nYour move?"
    )
    if feedback:
        user += f"\n\nNote: {feedback}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse_move(text):
    """Last direction word in the visible answer (ignoring <think> blocks), or None."""
    if not text:
        return None
    found = _MOVE_RE.findall(_THINK_RE.sub("", text))
    return found[-1].lower() if found else None
