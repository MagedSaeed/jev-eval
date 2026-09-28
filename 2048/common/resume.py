"""Continue a stopped game from its log.

Resuming is exact: a seed fixes the whole tile-spawn stream, so replaying the logged moves
from the opening board reproduces the board *and* the RNG state; and prompts are stateless
(current board only), so the model sees exactly what it would have seen without the break.
Every replayed board is checked against the log, and a mismatch refuses to resume.
"""

import json
from pathlib import Path

from .game import Game

FINISHED = {"game_over", "max_moves", "target_tile"}  # these games are over; everything else can continue
MILESTONES = [2 ** k for k in range(7, 18)]  # 128 ... 131072


class ResumeError(Exception):
    pass


def read_records(path):
    """All complete JSON records; a half-written last line (killed mid-write) is dropped."""
    records = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            break
    return records


def find_finished(results_dir, seed):
    """Any log for this seed whose game really ended (game_over / max_moves), or None."""
    for path in sorted(Path(results_dir).glob(f"*_seed{seed}.jsonl"), reverse=True):
        end = next((r for r in reversed(read_records(path)) if r.get("type") == "end"), None)
        if end and end["reason"] in FINISHED:
            return path
    return None


def find_resumable(results_dir, seed):
    """Newest log for this seed whose game didn't finish, or None."""
    for path in sorted(Path(results_dir).glob(f"*_seed{seed}.jsonl"), reverse=True):
        records = read_records(path)
        if not records or records[0].get("type") != "meta":
            continue
        end = next((r for r in reversed(records) if r.get("type") == "end"), None)
        if end is None or end["reason"] not in FINISHED:
            return path
        return None  # the newest run for this seed finished; start fresh rather than dig up older ones
    return None


def rebuild(path, seed):
    """Replay a log. Returns (game, state) where state holds the running totals to carry on."""
    records = read_records(path)
    meta = records[0]
    if meta.get("type") != "meta" or meta.get("seed") != seed:
        raise ResumeError(f"{path.name}: not a log for seed {seed}")

    game = Game(seed=seed)
    if game.board != meta["board"]:
        raise ResumeError(f"{path.name}: opening board differs from seed {seed}")

    moves = [r for r in records if r.get("type") == "move"]
    milestones, latencies = {}, []
    for rec in moves:
        result = game.move(rec["move"])
        if result is None or game.board != rec["board"] or list(result["spawn"] or []) != list(rec["spawn"] or []):
            raise ResumeError(f"{path.name}: replay diverges from the log at move {rec['n']}")
        latencies.append(rec["latency_s"])
        for m in MILESTONES:
            if game.max_tile >= m and m not in milestones:
                milestones[m] = {"move": rec["n"], "t_model": round(rec["t_model"], 3)}

    # Running totals come from the latest record that carries them: a move, a previous
    # resume marker, or the end record (which also counts failed attempts after the last move).
    totals = [r for r in records if r.get("type") in ("move", "resume", "end")]
    latest = totals[-1] if totals else {}
    if latest.get("type") in ("resume", "end"):
        failed = latest["failed_attempts"]
    else:  # killed hard: last resume marker's count + failures on the moves since
        marks = [i for i, r in enumerate(records) if r.get("type") == "resume"]
        base = records[marks[-1]]["failed_attempts"] if marks else 0
        failed = base + sum(r["attempts"] - 1 for r in records[(marks[-1] if marks else 0):] if r.get("type") == "move")

    end = next((r for r in reversed(records) if r.get("type") == "end"), None)
    state = {
        "t_model": latest.get("t_model", 0.0),
        "cost": latest.get("cost", 0.0),
        "failed_attempts": failed,
        "latencies": latencies,
        "milestones": milestones,
        "previous_end": end["reason"] if end else "no end record",
        # everything up to the last accepted move (earlier resume markers included) is kept
        "keep": records[: records.index(moves[-1]) + 1] if moves else [meta],
        "meta": meta,
    }
    return game, state
