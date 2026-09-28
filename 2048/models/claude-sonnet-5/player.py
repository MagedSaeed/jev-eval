from common.players import ChatPlayer


def make_player():
    return ChatPlayer(name="claude-sonnet-5", model_id="anthropic/claude-sonnet-5", reasoning="off")
