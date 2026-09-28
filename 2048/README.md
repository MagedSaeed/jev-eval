# 2048 benchmark

Models play 2048 through OpenRouter. Currently, the pipeline includes:

- **Speed:** average and median model latency per move.
- **Performance:** highest tile reached (2048 and beyond) and also the score.
- **Time to milestones:** model time and move number when each tile (128 … 131072) first appears.
- Invalid answers and cost, as supporting numbers.

## Layout

```
2048/
├── common/            shared package
│   ├── game.py        seeded 2048 engine
│   ├── prompts.py     board rendering, chat prompt, move parsing
│   ├── openrouter.py  OpenAI SDK client pointed at OpenRouter
│   ├── players.py     Player interface + ChatPlayer (any chat model)
│   ├── resume.py      rebuild a stopped game from its log
│   └── runner.py      game loop, JSONL logging, tqdm progress
├── models/            one folder per model: its adapter + its results
│   ├── jev-1.13/      player.py (decisions API), results/
│   ├── claude-sonnet-5/ player.py, results/
│   ├── gpt-5.6-sol/   player.py, results/
│   ├── qwen3.8-flash/ player.py, results/
│   └── qwen3.8-27b/   player.py, results/
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
python play.py qwen3.8-27b --budget 0.5 --max-moves 3000
python report.py            # every run
python report.py --best     # best run per model
python game_viewer/serve.py # http://localhost:8048
```

The viewer has two tabs:
- **Games** shows one card per model, replaying on a shared clock. Each card's seed dropdown starts on that model's best run (max tile, then score; marked ★). The sidebar switches models on and off. Drag a card by its header to reorder the cards; the order (and which models are hidden) is remembered in your browser, and "Reset order" in the sidebar goes back to alphabetical.
- **Leaderboard** shows the best run per model, or all runs. Click any column header to sort, and click a row to watch that game.

URL options: `?play` starts playback automatically, `?t=30` jumps to 30 s of model time, and `#leaderboard` opens the leaderboard tab.

Logos come from [LobeHub Icons](https://github.com/lobehub/lobe-icons) through jsDelivr, matched by the provider in the model's OpenRouter ID. A `logo.svg` or `logo.png` in a model's folder overrides that, which is how a model LobeHub doesn't cover (jev) gets a logo; without one it shows a lettered badge.

## Rules of the benchmark

- **Same game for everyone:** a seed fixes the opening board and the random stream of new tiles. Boards still diverge once models choose different moves, so compare models over several seeds.
- **Stateless prompting:** each call sees only the current board, the score and the list of legal moves; there is no move history. Thus, each call is a single trun call rather than multi turn.
- **Chat models** answer with one word. The last `up/down/left/right` in the answer is used.
- **jev** is a decisions model. It gets the board as `state` and a `choice` question whose options are the legal moves. Its per-move probabilities and confidence are logged.
- **Invalid answers:** each move allows up to 3 attempts (`--max-attempts`), with feedback after a bad answer. Every attempt's latency counts toward that move. If all attempts fail, the game ends as `invalid_moves`.
- **Model time** (`t_model`) is the sum of per-move latencies, measured on the final successful HTTP request. Network retries and backoff are excluded, so a flaky connection does not penalise a model. Wall-clock time is logged separately as `t_wall`.
- **Parallel runs** (`--parallel`, off by default) play each model in its own thread. Model latency is measured per request, so, in theory, running models side by side doesn't change their timings.
- **Finished seeds are skipped:** if a model already has a game on a seed that ended in `game_over` or `max_moves`, `play.py` skips that model/seed. Pass `--rerun` to play it again. Games stopped by the budget, an error or Ctrl-C don't count as finished; they are continued instead.
- **Stop conditions:** no legal move (`game_over`), `--max-moves` (default 10000), or `--budget` USD per game (default 3.0).
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
