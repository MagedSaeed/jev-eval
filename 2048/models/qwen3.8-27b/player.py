from common.players import ChatPlayer


def make_player():
    return ChatPlayer(name="qwen3.8-27b", model_id="qwen/qwen3.8-27b", reasoning="off")
