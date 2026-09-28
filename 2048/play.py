"""Run 2048 games for one or more models.

    python play.py                          # every model, seed 0, one game at a time
    python play.py --parallel               # models play at the same time
    python play.py --no-resume              # start stopped seeds over instead of continuing them
    python play.py --rerun                  # play seeds again even if they already have a finished game
    python play.py qwen3.8-flash jev-1.13 --seed 0 --budget 1.0
    python play.py --list

Each model lives in models/<name>/player.py (exposing make_player()); logs go to
models/<name>/results/<timestamp>_seed<seed>.jsonl.
"""

import argparse
import importlib.util
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
sys.path.insert(0, str(ROOT))

from tqdm import tqdm  # noqa: E402

from common.resume import ResumeError, find_finished, find_resumable  # noqa: E402
from common.runner import run_game  # noqa: E402


def available_models():
    return sorted(p.parent.name for p in MODELS.glob("*/player.py"))


def load_player(name):
    path = MODELS / name / "player.py"
    if not path.exists():
        raise SystemExit(f"unknown model {name!r}; available: {', '.join(available_models())}")
    spec = importlib.util.spec_from_file_location(f"models.{name}.player", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_player()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*", help="model folder names under models/ (default: all)")
    ap.add_argument("--list", action="store_true", help="list available models")
    ap.add_argument("--seed", type=int, nargs="+", default=[0], help="one game per seed")
    ap.add_argument("--max-moves", type=int, default=10000)
    ap.add_argument("--budget", type=float, default=3.0, help="USD cap per game")
    ap.add_argument("--max-attempts", type=int, default=3, help="tries per move before forfeit")
    ap.add_argument("--parallel", action=argparse.BooleanOptionalAction, default=False,
                    help="play different models at the same time (default: off); seeds of one model run in sequence")
    ap.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True,
                    help="continue the latest unfinished game of each model/seed (interrupted, error, budget, "
                         "invalid_moves or killed) in the same log; seeds with none start fresh (default: on)")
    ap.add_argument("--rerun", action="store_true",
                    help="play a model/seed even if it already has a finished game (game_over or max_moves); "
                         "by default those are skipped")
    args = ap.parse_args()

    if args.list:
        print("\n".join(available_models()))
        return
    args.models = args.models or available_models()

    players = {name: load_player(name) for name in args.models}
    stop = threading.Event()

    def play(name, seed, position, leave):
        results = MODELS / name / "results"
        done = None if args.rerun else find_finished(results, seed)
        if done:
            tqdm.write(f"{name} seed={seed}: already finished in {done.relative_to(ROOT)}, skipping (use --rerun to play again)")
            return
        resume_path = find_resumable(results, seed) if args.resume else None
        if resume_path:
            tqdm.write(f"{name} seed={seed}: resuming {resume_path.relative_to(ROOT)}")
        elif args.resume:
            tqdm.write(f"{name} seed={seed}: nothing to resume, starting a new game")
        try:
            path, s = run_game(
                players[name], results, seed=seed, max_moves=args.max_moves,
                budget_usd=args.budget, max_attempts=args.max_attempts,
                position=position, leave=leave, stop=stop, resume_path=resume_path,
            )
        except ResumeError as e:
            tqdm.write(f"{name} seed={seed}: cannot resume ({e}); log left untouched")
            return
        tqdm.write(f"{name} seed={seed} {s['reason']}: {s['moves']} moves, max tile {s['max_tile']}, "
                   f"score {s['score']}, avg {s['avg_move_s']}s/move, ${s['cost']:.4f} "
                   f"-> {path.relative_to(ROOT)}")
        if s["reason"] == "interrupted":  # Ctrl-C lands inside run_game; stop the whole run, not just this game
            stop.set()

    if args.parallel and len(args.models) > 1:
        # one thread per model (its seeds run in sequence), one progress bar row per model
        def model_worker(i, name):
            for seed in args.seed:
                if stop.is_set():
                    return
                play(name, seed, position=i, leave=True)

        with ThreadPoolExecutor(max_workers=len(args.models)) as pool:
            futures = [pool.submit(model_worker, i, n) for i, n in enumerate(args.models)]
            try:
                while not all(f.done() for f in futures):
                    time.sleep(0.2)
            except KeyboardInterrupt:  # Ctrl-C only reaches the main thread; tell games to wrap up
                stop.set()
                tqdm.write("  ! interrupted - finishing in-flight moves and writing end records...")
            for f in futures:
                f.result()
    else:
        jobs = [(name, seed) for name in args.models for seed in args.seed]
        overall = tqdm(jobs, desc="games", unit="game", position=0, disable=len(jobs) == 1)
        for name, seed in overall:
            if stop.is_set():
                tqdm.write("  ! interrupted - remaining games not started (run play.py again to continue)")
                break
            play(name, seed, position=0 if len(jobs) == 1 else 1, leave=len(jobs) == 1)


if __name__ == "__main__":
    main()
