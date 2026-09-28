from common.players import ChatPlayer


def make_player():
    return ChatPlayer(name="qwen3.8-flash", model_id="qwen/qwen3.8-flash", reasoning="off")
