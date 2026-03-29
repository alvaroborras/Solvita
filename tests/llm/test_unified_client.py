from src.llm.unified_client import UnifiedLLMClient


def test_generate_passes_request_timeout_to_chat_completion(monkeypatch):
    captured = {}

    class DummyCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return "ok"

    class DummyChat:
        def __init__(self):
            self.completions = DummyCompletions()

    class DummyClient:
        def __init__(self):
            self.chat = DummyChat()

    monkeypatch.setattr(UnifiedLLMClient, "_initialize_client", lambda self: DummyClient())

    client = UnifiedLLMClient(
        {
            "base_url": "http://example.test/v1",
            "api_key": "token",
            "model": "demo-model",
            "request_timeout": 17,
        }
    )

    assert client.generate("hello") == "ok"
    assert captured["timeout"] == 17
