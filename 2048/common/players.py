"""The Player interface every model adapter implements, plus the shared chat-model player.

A player's decide() returns a dict:
    move              "up" | "down" | "left" | "right" | None (unparseable)
    raw               the model's raw answer (for debugging)
    latency_s         seconds for the final successful API request (SDK retries excluded)
    cost              USD reported by OpenRouter (0 if unknown)
    extra             optional adapter-specific fields to log (tokens, probabilities, ...)
"""

from .openrouter import make_client
from .prompts import PROMPT_VERSION, build_messages, parse_move


class PlayerUnavailable(Exception):
    """make_player() can't build this player here (e.g. a native library isn't built yet)."""


class Player:
    name = "base"
    model_id = None
    stop_at_tile = None  # e.g. 2048: the runner ends the game ("target_tile") once this tile appears

    def decide(self, board, score, legal, feedback=None):
        raise NotImplementedError

    def describe(self):
        """Settings recorded in the run header so runs are reproducible."""
        return {"model_id": self.model_id}


# OpenRouter provider routing: send each request to the provider with the lowest recent
# time-to-first-token. Answers are one word, so latency (not throughput) dominates move time.
FASTEST_PROVIDER = {"sort": "latency"}


class ChatPlayer(Player):
    """Any OpenRouter chat model, prompted one move at a time with no history."""

    def __init__(self, name, model_id, reasoning="off", max_tokens=1024, temperature=0.0,
                 provider=FASTEST_PROVIDER):
        self.name = name
        self.model_id = model_id
        self.reasoning = reasoning
        self.provider = provider
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = make_client()

    def describe(self):
        return {
            "model_id": self.model_id,
            "adapter": "chat",
            "prompt_version": PROMPT_VERSION,
            "reasoning": self.reasoning,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "provider": self.provider,
        }

    def _extra_body(self):
        extra = {"usage": {"include": True}}
        if self.provider:
            extra["provider"] = self.provider
        if self.reasoning == "off":
            extra["reasoning"] = {"enabled": False}
        elif self.reasoning != "default":
            extra["reasoning"] = {"effort": self.reasoning}
        return extra

    def decide(self, board, score, legal, feedback=None):
        raw = self.client.chat.completions.with_raw_response.create(
            model=self.model_id,
            messages=build_messages(board, score, legal, feedback),
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            extra_body=self._extra_body(),
        )
        resp = raw.parse()
        text = resp.choices[0].message.content or ""
        usage = resp.usage.model_dump() if resp.usage else {}
        return {
            "move": parse_move(text),
            "raw": text[-500:],
            "latency_s": raw.elapsed.total_seconds(),
            "cost": usage.get("cost") or 0.0,
            "extra": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "provider": getattr(resp, "provider", None),
            },
        }
