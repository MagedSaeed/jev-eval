"""Shared OpenRouter client (OpenAI SDK pointed at OpenRouter)."""

import logging
import os
from pathlib import Path

import httpx
from openai import OpenAI
from tqdm import tqdm

BASE_URL = "https://openrouter.ai/api/v1"


class _TqdmRetryHandler(logging.Handler):
    """Surface the SDK's otherwise-silent retries (timeouts, 429/5xx) above the progress bars."""

    def emit(self, record):
        tqdm.write(f"  ! {record.getMessage()}")


_sdk_log = logging.getLogger("openai._base_client")
_sdk_log.setLevel(logging.INFO)
_sdk_log.addHandler(_TqdmRetryHandler())
_sdk_log.propagate = False


def load_api_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for parent in Path(__file__).resolve().parents:
        env = parent / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("OPENROUTER_API_KEY not found in environment or any parent .env")


def make_client(timeout=60, max_retries=5):
    """timeout is per HTTP attempt; a stalled request is abandoned and retried after it."""
    return OpenAI(
        base_url=BASE_URL,
        api_key=load_api_key(),
        timeout=timeout,
        max_retries=max_retries,
        default_headers={"X-Title": "jev-eval 2048"},
    )


def post_json(client, url, body):
    """POST to a non-OpenAI OpenRouter endpoint with the SDK's retry/timeout handling.
    Returns (json, latency_s of the final successful request)."""
    resp = client.post(url, body=body, cast_to=httpx.Response)
    return resp.json(), resp.elapsed.total_seconds()
