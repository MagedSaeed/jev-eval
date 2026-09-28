# 2048 benchmark

Models play 2048 through OpenRouter. Currently, the pipeline includes:

- **Speed:** average and median model latency per move.
- **Performance:** highest tile reached (2048 and beyond) and also the score.
- **Time to milestones:** model time and move number when each tile (128 … 131072) first appears.
- Invalid answers and cost, as supporting numbers.
- **Baselines:** simple non-LLM bots (random, fixed order, greedy) on the same seeds, to show what a score is worth.

## Layout

```
2048/
├── common/            shared package
│   ├── game.py        seeded 2048 engine
│   ├── prompts.py     board rendering, chat prompt, move parsing
│   ├── openrouter.py  OpenAI SDK client pointed at OpenRouter
│   ├── players.py     Player interface + ChatPlayer (any chat model)
│   ├── resume.py      rebuild a stopped game from its log
│   ├── runner.py      game loop, JSONL logging, tqdm progress
│   └── baselines.py   non-LLM reference players (random, fixed-order, greedy)
├── models/            one folder per model: its adapter + its results
│   ├── jev-1.13/      player.py (decisions API), results/
│   ├── claude-sonnet-5/ player.py, results/
│   ├── gpt-5.6-sol/   player.py, results/
│   ├── qwen3.8-flash/ player.py, results/
│   └── qwen3.8-27b/   player.py, results/
├── algorithms/        same layout as models/, for everything that isn't an LLM
│   ├── random/        player.py, results/
│   ├── fixed-order/   player.py, results/
│   ├── greedy/        player.py, results/
│   └── expectimax/    the solver: player.py (ctypes wrapper), build.sh, results/
├── game_viewer/       replays runs from models/*/results in the browser
├── play.py            run games
├── report.py          leaderboard in the terminal
└── tests/
```

## Setup

The key is read from `OPENROUTER_API_KEY` or from `.env` in any parent folder.

```bash
uv sync                  # or reuse system packages: uv venv --system-site-packages && uv pip install pytest
```

## Run

```bash
python play.py                                      # every model, seed 0, one game at a time
python play.py --parallel                           # models play at the same time
python play.py --no-resume                          # start stopped games seeds over instead of continuing them
python play.py --rerun                              # replay seeds that already have a finished game
python play.py --list                               # available models
python play.py jev-1.13 qwen3.8-flash --seed 0 1 2  # one game per model per seed
python play.py random fixed-order greedy --seed 1 2 3 4 5  # the baselines (free, a second in total)
algorithms/expectimax/build.sh                       # once: fetch + build the expectimax solver (needs git, make, g++)
python play.py expectimax --seed 1 2 3 4 5           # the solver (free; stops at 2048, ~30s per game)
python play.py qwen3.8-27b --budget 0.5 --max-moves 3000
python report.py            # every run (baselines in their own table)
python report.py --best     # best run per model
python game_viewer/serve.py # http://localhost:8048
```

The viewer has three tabs:
- **Games** shows one card per model, replaying on a shared clock. Each card's seed dropdown starts on that model's best run (max tile, then score; marked ★). The sidebar switches models on and off. Drag a card by its header to reorder the cards; the order (and which models are hidden) is remembered in your browser, and "Reset order" in the sidebar goes back to alphabetical.
- **Leaderboard** shows the best run per model, or all runs. Baselines are listed under the models, unranked. Click any column header to sort, and click a row to watch that game.
- **Baselines** shows the non-LLM players under an "Algorithms & baselines" divider (ⓘ explains them): expectimax search first, in a violet card, then the bots in dashed, blue-tinted cards, each with an ⓘ that explains the method (hover, focus or tap). The "Compare with" divider holds the LLM picker: "Choose LLMs" opens a checklist, and the chevron next to an LLM opens its runs so you can pick the seed (the best run is the default, marked ★). The ▲/▼ button next to it moves the LLMs above or below the algorithms. Both rows are centred so the cards line up. These choices are remembered in your browser; a seed picked here is also the one that LLM shows in the Games tab.

URL options: `?play` starts playback automatically, `?t=30` jumps to 30 s of model time, and `#baselines` / `#leaderboard` open those tabs.

Logos come from [LobeHub Icons](https://github.com/lobehub/lobe-icons) through jsDelivr, matched by the provider in the model's OpenRouter ID. A `logo.svg` or `logo.png` in a model's folder overrides that, which is how a model LobeHub doesn't cover (jev) gets a logo; without one it shows a lettered badge.

## Baselines

Every non-LLM player (the simple bots and the expectimax solver) lives in `algorithms/<name>/player.py`, exactly like models, and go through the same runner, logs and viewer. `play.py` and `report.py` treat both folders the same way; a name in `models/` wins over the same name in `algorithms/`.

- **random** picks one of the legal moves at random. It is the floor: a model below it is worse than not thinking at all.
- **fixed-order** always tries left, then down, then right, then up. It never looks at the tiles, but this keeps the biggest tile in the bottom-left corner, the classic 2048 strategy.
- **greedy** plays the move that scores the most points right now, with no look-ahead; ties go left, down, right, up.

All three are deterministic (random seeds its choice from the board), so a seed always gives the same game and resuming is exact. Cost is 0.

**Their timing is simulated.** A bot decides in microseconds, which would make it finish before the first LLM move on the model-time clock. So every baseline move is logged with a fixed `latency_s` of 0.25s (`SIM_LATENCY_S` in `common/baselines.py`). That's a bit faster than the fastest model (jev, ~0.37s), and the ⓘ text says so. The real compute time is logged next to it as `compute_s`.

### The solver: expectimax search

`algorithms/expectimax/` wraps Robert Xiao's (nneonneo) [2048-ai](https://github.com/nneonneo/2048-ai) (MIT), a C++ expectimax search. It looks several moves ahead, averages over every place the next tile can spawn, and scores positions with a hand-tuned heuristic (empty cells, monotonic rows, merges, big tiles on an edge). The method is described in his StackOverflow answer, ["What is the optimal algorithm for the game 2048?"](https://stackoverflow.com/a/22498940). Unlike the other baselines it is a real algorithm, so it's the ceiling: it reaches 2048 on every seed.

- `build.sh` clones the repo at a pinned commit and builds `bin/2048.so`. The clone is git-ignored. The only change is a force-included `quiet.h` that silences the library's per-move debug printing; the search itself is untouched.
- `player.py` calls `find_best_move` through `ctypes`. `tests/test_baselines.py` checks that its board encoding and move numbering agree with `common/game.py` exactly, and is skipped if the library isn't built.
- **It stops at 2048**, the goal of the game (`stop_at_tile = 2048`; the runner ends the game with reason `target_tile`, which counts as finished). Left alone it keeps going. Its ⓘ says so.
- It uses the same simulated 0.25s per move as the other baselines, so a game to 2048 (~950 moves) takes about 4 minutes on the model-time clock.
- If the library isn't built, `python play.py` with no model names skips it with a note; naming it explicitly stops with the build instructions.
- The viewer shows it as **Expectimax search**, first in the Baselines row and group, in a violet card with a gradient ring and a spark logo, so it reads as an algorithm rather than one more bot. Its ⓘ gives the method and the credits. This comes from `kind = "solver"` and `display_name` in the player, which are logged in its `meta` line.

To add a baseline, subclass `BaselinePlayer` in `common/baselines.py`, set `description` (the viewer shows it in the ⓘ), implement `choose(board, legal)`, and add `algorithms/<name>/player.py` with `make_player()`.

## Rules of the benchmark

- **Same game for everyone:** a seed fixes the opening board and the random stream of new tiles. Boards still diverge once models choose different moves, so compare models over several seeds.
- **Stateless prompting:** each call sees only the current board, the score and the list of legal moves; there is no move history. Thus, each call is a single trun call rather than multi turn.
- **Chat models** answer with one word. The last `up/down/left/right` in the answer is used.
- **jev** is a decisions model. It gets the board as `state` and a `choice` question whose options are the legal moves. Its per-move probabilities and confidence are logged.
- **Invalid answers:** each move allows up to 3 attempts (`--max-attempts`), with feedback after a bad answer. Every attempt's latency counts toward that move. If all attempts fail, the game ends as `invalid_moves`.
- **Model time** (`t_model`) is the sum of per-move latencies, measured on the final successful HTTP request. Network retries and backoff are excluded, so a flaky connection does not penalise a model. Wall-clock time is logged separately as `t_wall`.
- **Parallel runs** (`--parallel`, off by default) play each model in its own thread. Model latency is measured per request, so, in theory, running models side by side doesn't change their timings.
- **Finished seeds are skipped:** if a model already has a game on a seed that ended in `game_over` or `max_moves`, `play.py` skips that model/seed. Pass `--rerun` to play it again. Games stopped by the budget, an error or Ctrl-C don't count as finished; they are continued instead.
- **Stop conditions:** no legal move (`game_over`), `--max-moves` (default 10000), `--budget` USD per game (default 3.0), or a player's own target tile (`target_tile`; only the expectimax solver sets one, at 2048).
- Chat models run with `reasoning` off and `temperature` 0 by default. Change this in the model's `player.py`. Currently, models play without thinking.
- **Provider routing:** chat models send `provider: {"sort": "latency"}`, so OpenRouter picks the provider that has recently been fastest to start answering, even when it costs more. The provider that served each move is logged. jev is served only by TypeSafe.

## Resuming stopped games

`python play.py` continues each model/seed's latest unfinished game in its original log (on by default; `--no-resume` starts over instead). That covers games stopped by Ctrl-C, an error, the budget cap, too many invalid answers, or a hard kill with no `end` line. Seeds with no unfinished game start fresh. Ctrl-C stops the whole run; running `play.py` again continues the stopped game and starts the ones that hadn't begun.

- **Resuming is exact.** The seed fixes every new tile, so replaying the logged moves rebuilds both the board and the random generator's state. Prompts contain only the current board, so the model can't tell there was a break. A resumed game is move-for-move identical to one that never stopped; `tests/test_resume.py` checks this.
- **Every replayed board is checked against the log.** If one doesn't match, the resume is refused and the log is left untouched.
- **`--budget` and `--max-moves` cover the whole game,** including moves made before the break. So `--budget 5` gives a game that stopped at the $3 default another $2 to spend.
- **The break is recorded.** The old `end` line is replaced by a `resume` record, and a new `end` is written when the game stops again. `t_model` is unaffected; `t_wall` counts from the first start, so it includes the break.

## Adding a model

Create `models/<name>/player.py` with a `make_player()` function:

```python
from common.players import ChatPlayer

def make_player():
    return ChatPlayer(name="<name>", model_id="<openrouter/model-id>", reasoning="off")
```

A model that isn't chat-based implements `Player.decide()` itself; see `models/jev-1.13/player.py`.

## Log format

`models/<name>/results/<UTC timestamp>_seed<seed>.jsonl` holds one JSON object per line:

- a `meta` line with the settings and the initial board,
- one `move` line per accepted move (board after the move, spawned tile, latency, `t_model`, cost, tokens, provider, and adapter extras),
- a `resume` line wherever a stopped game was continued, with the new limits and the running totals,
- an `end` line with the end reason, summary and milestones. This line is written even after Ctrl-C or an error.

## Tests

```bash
python -m pytest -q
```
