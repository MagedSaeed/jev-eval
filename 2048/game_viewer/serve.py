"""Serve the game viewer and the run logs from ../models/*/results/.

    python game_viewer/serve.py            # http://localhost:8048
    python game_viewer/serve.py --port 9000

Endpoints (always read from disk, so games still being played show up as they grow):
    /                              the viewer (index.html)
    /api/runs                      JSON list of runs: {model, file, size, idle_s, meta, end}
                                   (idle_s = seconds since the log was last written)
    /runs/<model>/<file>           a raw JSONL log
    /runs/<model>/<file>?offset=N  only the bytes after N (the viewer polls this for live games)
    /logos/<model>                 models/<model>/logo.svg|png, if the model folder has one
"""

import argparse
import json
import os
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
MODELS = HERE.parent / "models"
TAIL_BYTES = 64 * 1024  # enough to hold the last record of a log
LOGO_TYPES = {".svg": "image/svg+xml", ".png": "image/png"}


def local_logo(model):
    """A logo shipped in the model's own folder (overrides the viewer's online logo lookup)."""
    for ext in LOGO_TYPES:
        path = MODELS / model / f"logo{ext}"
        if path.is_file():
            return path
    return None


def _first_and_last_record(path):
    """Read only the head and tail of a log; logs of long games can be megabytes."""
    with path.open("rb") as f:
        first = f.readline()
        size = f.seek(0, os.SEEK_END)
        f.seek(max(0, size - TAIL_BYTES))
        tail = f.read().splitlines()
    # latest move/end record; skips a half-written last line and resume markers
    for line in reversed(tail):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") in ("move", "end"):
            return json.loads(first), rec, size
    return json.loads(first), json.loads(first), size


def list_runs():
    runs = []
    for path in sorted(MODELS.glob("*/results/*.jsonl")):
        try:
            meta, last, size = _first_and_last_record(path)
        except ValueError:  # empty or first line not written yet
            continue
        if last.get("type") == "end":
            end = last
        else:  # still being played (or killed): summarize from the latest move
            end = {"reason": "incomplete", "moves": last.get("n", 0),
                   "max_tile": last.get("max_tile", max(max(r) for r in meta["board"])),
                   "score": last.get("score", 0), "t_model": last.get("t_model", 0), "cost": last.get("cost", 0),
                   "avg_move_s": (last["t_model"] / last["n"]) if last.get("n") else None, "milestones": {}}
        model = path.parent.parent.name
        runs.append({"model": model, "file": path.name, "size": size, "local_logo": local_logo(model) is not None,
                     "idle_s": round(time.time() - path.stat().st_mtime, 1), "meta": meta, "end": end})
    return runs


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(HERE), **k)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/api/runs":
            return self._send(json.dumps(list_runs()).encode(), "application/json")
        if url.path.startswith("/runs/"):
            parts = url.path[len("/runs/"):].split("/")
            if len(parts) == 2 and all(p and ".." not in p for p in parts):
                path = MODELS / parts[0] / "results" / parts[1]
                if path.suffix == ".jsonl" and path.is_file():
                    offset = int((parse_qs(url.query).get("offset") or ["0"])[0])
                    with path.open("rb") as f:
                        f.seek(offset)
                        return self._send(f.read(), "application/x-ndjson")
            return self.send_error(404)
        if url.path.startswith("/logos/"):
            model = url.path[len("/logos/"):]
            logo = local_logo(model) if model and "/" not in model and ".." not in model else None
            if logo:
                return self._send(logo.read_bytes(), LOGO_TYPES[logo.suffix])
            return self.send_error(404)
        return super().do_GET()

    def end_headers(self):
        # the viewer page is edited often; make browsers revalidate it instead of reusing a stale copy
        if "Cache-Control" not in "".join(h.decode("latin-1") for h in getattr(self, "_headers_buffer", [])):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8048)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"2048 game viewer: http://localhost:{args.port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
