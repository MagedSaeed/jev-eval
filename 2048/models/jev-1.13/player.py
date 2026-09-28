"""jev is a "decisions" model: it answers structured questions about a state instead of chatting.

Endpoint: POST https://openrouter.ai/api/alpha/decisions
    {"model", "state": <any JSON>, "questions": {name: {"type": "choice", "instructions", "criteria": {option: description}}}}
Response:
    {"answers": {name: {"choice", "probabilities": {option: p}, "confidence"}}, "usage": {"input_tokens", "output_tokens", "cost"}, "provider"}
"""

from common.openrouter import make_client, post_json
from common.players import Player
from common.prompts import RULES

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

MOVE_DESCRIPTIONS = {
    "up": "slide all tiles up",
    "down": "slide all tiles down",
    "left": "slide all tiles left",
    "right": "slide all tiles right",
}


class JevPlayer(Player):
    def __init__(self, name="jev-1.13", model_id="typesafe/jev-1.13"):
        self.name = name
        self.model_id = model_id
        # jev normally answers in ~1s but occasionally stalls; don't wait a full minute before retrying
        self.client = make_client(timeout=20)

    def describe(self):
        return {"model_id": self.model_id, "adapter": "decisions", "prompt_version": "v1"}

    def decide(self, board, score, legal, feedback=None):
        instructions = RULES + " In the board, 0 means an empty cell."
        if feedback:
            instructions += f" Note: {feedback}"
        body = {
            "model": self.model_id,
            "state": {"board": board, "score": score},
            "questions": {
                "move": {
                    "type": "choice",
                    "instructions": instructions,
                    # offer only legal moves, matching the chat prompt's "moves that change the board"
                    "criteria": {m: MOVE_DESCRIPTIONS[m] for m in legal},
                }
            },
        }
        data, latency = post_json(self.client, DECISIONS_URL, body)
        answer = data["answers"]["move"]
        usage = data.get("usage") or {}
        return {
            "move": answer.get("choice"),
            "raw": str(answer.get("choice")),
            "latency_s": latency,
            "cost": usage.get("cost") or 0.0,
            "extra": {
                "prompt_tokens": usage.get("input_tokens"),
                "completion_tokens": usage.get("output_tokens"),
                "probabilities": answer.get("probabilities"),
                "confidence": answer.get("confidence"),
                "provider": data.get("provider"),
            },
        }


def make_player():
    return JevPlayer()
