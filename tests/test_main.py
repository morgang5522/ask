import json

import ask.main as ask_main


class DummyResponse:
    """Simple stand-in for the requests.Response API we rely on."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _llm_config():
    return ask_main.LLMConfig(
        base_url="http://localhost:1234",
        endpoint="/v1/chat/completions",
        model="stub",
        temperature=0.0,
    )


def test_call_llm_parses_valid_json(monkeypatch):
    """LLM responses that contain valid JSON should be returned as dicts."""

    def fake_post(*args, **kwargs):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"type": "answer", "message": "hi", "command": ""}
                        )
                    }
                }
            ]
        }
        return DummyResponse(payload)

    monkeypatch.setattr(ask_main.requests, "post", fake_post)

    result = ask_main.call_llm(_llm_config(), [])

    assert result == {"type": "answer", "message": "hi", "command": "", "follow_up": False}


def test_call_llm_handles_non_json(monkeypatch):
    """When the LLM returns non-JSON, we should fall back to a readable error."""

    def fake_post(*args, **kwargs):
        payload = {"choices": [{"message": {"content": "plain text"}}]}
        return DummyResponse(payload)

    monkeypatch.setattr(ask_main.requests, "post", fake_post)

    result = ask_main.call_llm(_llm_config(), [])

    assert result["type"] == "question"
    assert "plain text" in result["message"]
    assert result["follow_up"] is False


def test_session_round_trip(tmp_path, monkeypatch):
    """save_session + load_session should preserve the conversation log."""

    session_dir = tmp_path / "ask-cli"
    session_dir.mkdir()

    # Force session_path() to use our temp directory.
    monkeypatch.setattr(ask_main, "config_dir", lambda: str(session_dir))

    messages = [{"role": "user", "content": "hello"}]
    ask_main.save_session(messages)

    loaded = ask_main.load_session()

    assert loaded == messages
