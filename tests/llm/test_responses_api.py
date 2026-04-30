"""Sub-H: UnifiedLLMClient Responses API path with reasoning_effort."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _make_client(monkeypatch, **extras):
    """Construct a UnifiedLLMClient with stubbed self.client (no real network)."""
    monkeypatch.setenv("SOLVITA_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("SOLVITA_API_KEY", "sk-test")
    monkeypatch.setenv("SOLVITA_MODEL", "gpt-5.4")
    monkeypatch.delenv("SOLVITA_USE_RESPONSES_API", raising=False)
    monkeypatch.delenv("SOLVITA_REASONING_EFFORT", raising=False)
    from src.llm.unified_client import UnifiedLLMClient
    cfg = {"provider": "openai_compatible", **extras}
    client = UnifiedLLMClient(cfg)
    return client


def _stub_responses_create(client, *, output_items, usage=None):
    """Replace client.client.responses.create with a stub returning a fake response."""
    captured = {}
    fake_response = SimpleNamespace(
        output=output_items,
        usage=usage or SimpleNamespace(input_tokens=100, output_tokens=50),
    )

    class _Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return fake_response

    class _FakeOpenAI:
        def __init__(self):
            self.responses = _Responses()
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: None))

    client.client = _FakeOpenAI()
    return captured


def test_responses_api_routes_when_use_responses_api_true(monkeypatch):
    client = _make_client(monkeypatch, use_responses_api=True)
    captured = _stub_responses_create(client, output_items=[
        SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="hello")])
    ])
    out = client.chat([{"role": "user", "content": "hi"}])
    assert out == "hello"
    assert captured["model"] == "gpt-5.4"
    assert isinstance(captured["input"], list)
    assert captured["input"][0]["role"] == "user"


def test_responses_api_routes_when_reasoning_effort_set(monkeypatch):
    client = _make_client(monkeypatch, reasoning_effort="high")
    captured = _stub_responses_create(client, output_items=[
        SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="answer")])
    ])
    client.chat([{"role": "user", "content": "q"}])
    assert captured["reasoning"] == {"effort": "high"}


def test_responses_api_passes_reasoning_effort_xhigh(monkeypatch):
    client = _make_client(monkeypatch, use_responses_api=True, reasoning_effort="xhigh")
    captured = _stub_responses_create(client, output_items=[
        SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="x")])
    ])
    client.chat([{"role": "user", "content": "q"}])
    assert captured["reasoning"] == {"effort": "xhigh"}


def test_responses_api_skips_reasoning_block_in_output(monkeypatch):
    """Output containing a 'reasoning' item before the message: only message text returned."""
    client = _make_client(monkeypatch, use_responses_api=True)
    captured = _stub_responses_create(client, output_items=[
        SimpleNamespace(type="reasoning", id="rs_1"),
        SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="final answer")]),
    ])
    out = client.chat([{"role": "user", "content": "q"}])
    assert out == "final answer"


def test_responses_api_concatenates_multiple_output_text_chunks(monkeypatch):
    client = _make_client(monkeypatch, use_responses_api=True)
    captured = _stub_responses_create(client, output_items=[
        SimpleNamespace(
            type="message",
            content=[
                SimpleNamespace(type="output_text", text="part1 "),
                SimpleNamespace(type="output_text", text="part2"),
            ],
        )
    ])
    out = client.chat([{"role": "user", "content": "q"}])
    assert out == "part1 part2"


def test_responses_api_extracts_system_into_instructions(monkeypatch):
    client = _make_client(monkeypatch, use_responses_api=True)
    captured = _stub_responses_create(client, output_items=[
        SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="ok")])
    ])
    client.chat([
        {"role": "system", "content": "You are a competitive programmer."},
        {"role": "user", "content": "Solve it."},
    ])
    assert captured["instructions"] == "You are a competitive programmer."
    # System should NOT appear in the input list (moved to instructions)
    assert all(m["role"] != "system" for m in captured["input"])


def test_responses_api_assistant_messages_use_output_text(monkeypatch):
    client = _make_client(monkeypatch, use_responses_api=True)
    captured = _stub_responses_create(client, output_items=[
        SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text="ok")])
    ])
    client.chat([
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi back"},
        {"role": "user", "content": "now help"},
    ])
    inp = captured["input"]
    assert inp[1]["role"] == "assistant"
    assert inp[1]["content"][0]["type"] == "output_text"
    assert inp[1]["content"][0]["text"] == "hi back"
    assert inp[0]["content"][0]["type"] == "input_text"


def test_chat_completions_path_unchanged_when_no_responses_flag(monkeypatch):
    """Default path (no use_responses_api, no reasoning_effort) still uses chat.completions."""
    monkeypatch.setenv("SOLVITA_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("SOLVITA_API_KEY", "sk-test")
    monkeypatch.setenv("SOLVITA_MODEL", "gpt-5.4")
    monkeypatch.delenv("SOLVITA_USE_RESPONSES_API", raising=False)
    monkeypatch.delenv("SOLVITA_REASONING_EFFORT", raising=False)

    from src.llm.unified_client import UnifiedLLMClient
    client = UnifiedLLMClient({"provider": "openai_compatible"})

    chat_called = {"n": 0}
    responses_called = {"n": 0}

    class _Resp:
        def create(self, **kw):
            responses_called["n"] += 1
            raise AssertionError("responses.create should not be called")

    class _ChatCompletions:
        def create(self, **kw):
            chat_called["n"] += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
            )

    class _FakeOpenAI:
        def __init__(self):
            self.responses = _Resp()
            self.chat = SimpleNamespace(completions=_ChatCompletions())

    client.client = _FakeOpenAI()
    out = client.chat([{"role": "user", "content": "q"}])
    assert chat_called["n"] == 1
    assert responses_called["n"] == 0


def test_env_var_enables_responses_api(monkeypatch):
    """SOLVITA_USE_RESPONSES_API=1 enables responses API even without config flag."""
    monkeypatch.setenv("SOLVITA_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("SOLVITA_API_KEY", "sk-test")
    monkeypatch.setenv("SOLVITA_MODEL", "gpt-5.4")
    monkeypatch.setenv("SOLVITA_USE_RESPONSES_API", "1")

    from src.llm.unified_client import UnifiedLLMClient
    client = UnifiedLLMClient({"provider": "openai_compatible"})
    assert client.use_responses_api is True


def test_env_var_sets_reasoning_effort(monkeypatch):
    monkeypatch.setenv("SOLVITA_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("SOLVITA_API_KEY", "sk-test")
    monkeypatch.setenv("SOLVITA_MODEL", "gpt-5.4")
    monkeypatch.setenv("SOLVITA_REASONING_EFFORT", "xhigh")

    from src.llm.unified_client import UnifiedLLMClient
    client = UnifiedLLMClient({"provider": "openai_compatible"})
    assert client.reasoning_effort == "xhigh"
