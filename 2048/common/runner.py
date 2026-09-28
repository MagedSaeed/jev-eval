"""Plays one game with a Player and streams every move to a JSONL log.

Log format (one JSON object per line):
    {"type": "meta", ...}    run settings + initial board
    {"type": "move", ...}    one per accepted move
    {"type": "resume", ...}  a stopped game was continued here (see common/resume.py)
    {"type": "end",  ...}    end reason + summary (written even on crash/Ctrl-C)

"Model time" (t_model) is the sum of API latencies for accepted moves and their failed
attempts, so network backoff and our own overhead do not count against a model.
"t_wall" is seconds since the game first started, so a resumed game shows its break.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

from .game import Game
from .resume import MILESTONES, rebuild

STAMP = "%Y%m%dT%H%M%SZ"


def run_game(player, results_dir, seed=0, max_moves=10000, budget_usd=3.0, max_attempts=3,
             position=0, leave=True, stop=None, resume_path=None):
    """stop: optional threading.Event; when set, the game ends as 'interrupted' before the next move.
    resume_path: a log of a stopped game to continue (same file) instead of starting fresh.
    max_moves and budget_usd always apply to the whole game, including moves before a resume."""
    now = datetime.now(timezone.utc)
    stamp = now.strftime(STAMP)

    if resume_path:
        path = Path(resume_path)
        game, st = rebuild(path, seed)
        t_model, cost, failed_attempts = st["t_model"], st["cost"], st["failed_attempts"]
        latencies, milestones = st["latencies"], st["milestones"]
        started = datetime.strptime(st["meta"]["started_at"], STAMP).replace(tzinfo=timezone.utc)
        wall0 = started.timestamp()
        # drop the old end record (and any half-written line), then mark where we pick up
        path.write_text("".join(json.dumps(r) + "\n" for r in st["keep"]))
        header = {
            "type": "resume",
            "at_move": game.moves,
            "resumed_at": stamp,
            "previous_end": st["previous_end"],
            "max_moves": max_moves,
            "budget_usd": budget_usd,
            "max_attempts": max_attempts,
            "t_model": round(t_model, 4),
            "cost": round(cost, 6),
            "failed_attempts": failed_attempts,
        }
        mode = "a"
    else:
        game = Game(seed=seed)
        results_dir = Path(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)
        path = results_dir / f"{stamp}_seed{seed}.jsonl"
        t_model, cost, failed_attempts, latencies, milestones = 0.0, 0.0, 0, [], {}
        wall0 = now.timestamp()
        header = {
            "type": "meta",
            "model": player.name,
            **player.describe(),
            "seed": seed,
            "started_at": stamp,
            "max_moves": max_moves,
            "budget_usd": budget_usd,
            "max_attempts": max_attempts,
            "board": [r[:] for r in game.board],
        }
        mode = "w"

    reason = "unknown"
    # a resumed game's bar starts at its logged move count and stats, not at zero
    bar = tqdm(total=max_moves, initial=game.moves, dynamic_ncols=True, unit="mv",
               desc=f"{player.name} seed={seed}" + (" (resumed)" if resume_path else ""),
               position=position, leave=leave)

    def show_stats(refresh):
        bar.set_postfix(max=game.max_tile, score=game.score, cost=f"${cost:.4f}",
                        avg=f"{t_model / game.moves:.2f}s" if game.moves else "-", refresh=refresh)

    if game.moves:
        show_stats(refresh=True)

    with path.open(mode) as log:
        def write(rec):
            log.write(json.dumps(rec) + "\n")
            log.flush()

        write(header)
        try:
            while True:
                if stop is not None and stop.is_set():
                    reason = "interrupted"
                    break
                if player.stop_at_tile and game.max_tile >= player.stop_at_tile:
                    reason = "target_tile"
                    break
                legal = game.legal_moves()
                if not legal:
                    reason = "game_over"
                    break
                if game.moves >= max_moves:
                    reason = "max_moves"
                    break
                if cost >= budget_usd:
                    reason = "budget"
                    break

                move_latency, feedback, attempts, decision = 0.0, None, 0, None
                for attempts in range(1, max_attempts + 1):
                    decision = player.decide(game.board, game.score, legal, feedback)
                    move_latency += decision["latency_s"]
                    cost += decision.get("cost") or 0.0
                    if decision["move"] in legal:
                        break
                    failed_attempts += 1
                    feedback = (
                        f"your previous answer {decision.get('raw', '')[:80]!r} was not a legal move. "
                        f"Answer with one of: {', '.join(legal)}."
                    )
                else:
                    t_model += move_latency
                    reason = "invalid_moves"
                    break

                t_model += move_latency
                latencies.append(move_latency)
                result = game.move(decision["move"])
                for m in MILESTONES:
                    if game.max_tile >= m and m not in milestones:
                        milestones[m] = {"move": game.moves, "t_model": round(t_model, 3)}

                write({
                    "type": "move",
                    "n": game.moves,
                    "move": decision["move"],
                    "attempts": attempts,
                    "latency_s": round(move_latency, 4),
                    "t_model": round(t_model, 4),
                    "t_wall": round(time.time() - wall0, 3),
                    "gained": result["gained"],
                    "spawn": result["spawn"],
                    "score": game.score,
                    "max_tile": game.max_tile,
                    "board": [r[:] for r in game.board],
                    "cost": round(cost, 6),
                    **(decision.get("extra") or {}),
                })
                show_stats(refresh=False)
                bar.update(1)
        except KeyboardInterrupt:
            reason = "interrupted"
        except Exception as e:  # keep the partial log usable
            reason = f"error: {e}"
            tqdm.write(f"  ! {player.name} seed={seed}: {reason}")
        finally:
            summary = {
                "type": "end",
                "reason": reason,
                "moves": game.moves,
                "score": game.score,
                "max_tile": game.max_tile,
                "t_model": round(t_model, 3),
                "t_wall": round(time.time() - wall0, 3),
                "avg_move_s": round(t_model / game.moves, 4) if game.moves else None,
                "median_move_s": round(sorted(latencies)[len(latencies) // 2], 4) if latencies else None,
                "failed_attempts": failed_attempts,
                "cost": round(cost, 6),
                "milestones": {str(k): v for k, v in milestones.items()},
                "board": [r[:] for r in game.board],
            }
            write(summary)
            bar.set_description(f"{player.name} seed={seed} [{reason}]")
            bar.close()

    return path, summary
