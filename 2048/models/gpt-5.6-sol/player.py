from common.players import ChatPlayer


def make_player():
    return ChatPlayer(name="gpt-5.6-sol", model_id="openai/gpt-5.6-sol", reasoning="off")
