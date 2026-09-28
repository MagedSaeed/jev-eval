"""Print a leaderboard from every run log under models/*/results/.

    python report.py            # one row per run
    python report.py --best     # best run per model
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from common.resume import read_records  # noqa: E402


def load_runs():
    runs = []
    for path in sorted(ROOT.glob("models/*/results/*.jsonl")):
        records = read_records(path)
        if not records:
            continue
        meta = records[0]
        progress = [r for r in records if r.get("type") in ("move", "end")]
        end = progress[-1] if progress else {}
        if end.get("type") != "end":  # still running or killed hard
            last = end
            end = {"reason": "incomplete", "moves": last.get("n", 0), "max_tile": last.get("max_tile"),
                   "score": last.get("score"), "t_model": last.get("t_model"), "cost": last.get("cost"),
                   "avg_move_s": (last["t_model"] / last["n"]) if last.get("n") else None,
                   "failed_attempts": None, "milestones": {}}
        runs.append({"file": str(path.relative_to(ROOT)), "meta": meta, "end": end})
    return runs


def fmt_time(s):
    if s is None:
        return "-"
    return f"{s:.1f}s" if s < 120 else f"{s / 60:.1f}m"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--best", action="store_true")
    args = ap.parse_args()

    runs = load_runs()
    if args.best:
        best = {}
        for r in runs:
            key = r["meta"]["model"]
            if key not in best or (r["end"]["max_tile"] or 0, r["end"]["score"] or 0) > (
                best[key]["end"]["max_tile"] or 0, best[key]["end"]["score"] or 0):
                best[key] = r
        runs = list(best.values())
    runs.sort(key=lambda r: (-(r["end"]["max_tile"] or 0), -(r["end"]["score"] or 0)))

    header = ["model", "seed", "max", "score", "moves", "avg/move", "t@2048", "t@max", "bad", "cost", "end"]
    rows = []
    for r in runs:
        m, e = r["meta"], r["end"]
        ms = e.get("milestones") or {}
        top = ms.get(str(e["max_tile"])) or {}
        rows.append([
            m["model"], str(m["seed"]), str(e["max_tile"]), str(e["score"]), str(e["moves"]),
            f"{e['avg_move_s']:.2f}s" if e.get("avg_move_s") else "-",
            fmt_time((ms.get("2048") or {}).get("t_model")),
            fmt_time(top.get("t_model")),
            "-" if e.get("failed_attempts") is None else str(e["failed_attempts"]),
            f"${e['cost']:.4f}" if e.get("cost") is not None else "-",
            e["reason"],
        ])
    widths = [max(len(x) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(c.ljust(w) for c, w in zip(row, widths)))
    if not rows:
        print("(no runs yet - try: python play.py qwen3.8-flash)")


if __name__ == "__main__":
    main()
