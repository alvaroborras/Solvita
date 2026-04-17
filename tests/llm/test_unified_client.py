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


def test_anthropic_provider_calls_messages_api(monkeypatch):
    captured = {}

    class _Block:
        text = "anthropic-ok"

    class _Resp:
        content = [_Block()]

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp()

    class _DummyAnthropicClient:
        def __init__(self):
            self.messages = _Messages()

    monkeypatch.setattr(UnifiedLLMClient, "_initialize_client", lambda self: _DummyAnthropicClient())

    client = UnifiedLLMClient(
        {
            "base_url": "http://anthropic.local",
            "api_key": "token",
            "model": "claude-opus-4-6-20260205",
            "provider": "anthropic",
            "request_timeout": 21,
        }
    )
    out = client.generate_with_system("sys", "hello")
    assert out == "anthropic-ok"
    assert captured["model"] == "claude-opus-4-6-20260205"
    assert captured["timeout"] == 21
    assert captured["system"] == "sys"
    assert captured["messages"][0]["role"] == "user"


def test_dashscope_provider_calls_generation(monkeypatch):
    class _Message:
        content = "dashscope-ok"

    class _Choice:
        message = _Message()

    class _Output:
        choices = [_Choice()]

    class _Resp:
        status_code = 200
        output = _Output()

    captured = {}

    class _DummyGeneration:
        @staticmethod
        def call(**kwargs):
            captured.update(kwargs)
            return _Resp()

    import sys
    import types

    fake_dashscope = types.ModuleType("dashscope")
    fake_dashscope.Generation = _DummyGeneration
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope)
    monkeypatch.setattr(UnifiedLLMClient, "_initialize_client", lambda self: object())

    client = UnifiedLLMClient(
        {
            "base_url": "http://dashscope.local",
            "api_key": "token",
            "model": "qwen3.6-plus",
            "provider": "dashscope",
            "max_tokens": 321,
            "temperature": 0.3,
        }
    )
    out = client.generate("hello")
    assert out == "dashscope-ok"
    assert captured["model"] == "qwen3.6-plus"
    assert captured["max_tokens"] == 321
    assert captured["temperature"] == 0.3
    assert captured["messages"][0]["content"] == "hello"
