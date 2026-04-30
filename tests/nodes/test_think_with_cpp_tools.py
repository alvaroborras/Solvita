"""Sub-E: <run_cpp> tool in think turn — compile + execute C++ in sandbox."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_split_run_cpp_block_with_input():
    from src.nodes.generate_code import _split_run_cpp_block
    block = """INPUT_BEGIN
3 4
1 2
INPUT_END
#include <iostream>
int main(){int n,m,a,b;std::cin>>n>>m>>a>>b;std::cout<<a+b<<"\\n";return 0;}
"""
    stdin_text, src = _split_run_cpp_block(block)
    assert stdin_text == "3 4\n1 2\n"
    assert "#include" in src
    assert "INPUT_BEGIN" not in src


def test_split_run_cpp_block_without_input():
    from src.nodes.generate_code import _split_run_cpp_block
    block = "#include <iostream>\nint main(){std::cout<<42;return 0;}"
    stdin_text, src = _split_run_cpp_block(block)
    assert stdin_text == ""
    assert "main()" in src


def test_extract_run_cpp_blocks():
    from src.nodes.generate_code import _extract_run_cpp_blocks
    txt = "Some text\n<run_cpp>\n#include <iostream>\nint main(){return 0;}\n</run_cpp>\nDone."
    blocks = _extract_run_cpp_blocks(txt)
    assert len(blocks) == 1
    stdin, src = blocks[0]
    assert stdin == ""
    assert "main()" in src


def test_extract_run_cpp_blocks_multiple():
    from src.nodes.generate_code import _extract_run_cpp_blocks
    txt = (
        "<run_cpp>int main(){return 0;}</run_cpp>"
        " then "
        "<run_cpp>\nINPUT_BEGIN\n5\nINPUT_END\nint main(){int n;std::cin>>n;return 0;}</run_cpp>"
    )
    blocks = _extract_run_cpp_blocks(txt)
    assert len(blocks) == 2
    assert blocks[0][0] == ""
    assert blocks[1][0] == "5\n"


def test_extract_run_cpp_blocks_case_insensitive():
    from src.nodes.generate_code import _extract_run_cpp_blocks
    txt = "<RUN_CPP>int main(){return 0;}</RUN_CPP>"
    assert len(_extract_run_cpp_blocks(txt)) == 1


def test_format_cpp_tool_results_compiled_ok():
    from src.nodes.generate_code import _format_cpp_tool_results
    blocks = [("3 4\n", "int main(){...}")]
    results = [(True, 0, "7\n", "")]
    out = _format_cpp_tool_results(blocks, results)
    assert "compile: OK" in out
    assert "exit_code: 0" in out
    assert "7" in out
    assert "stdin" in out


def test_format_cpp_tool_results_compile_failed():
    from src.nodes.generate_code import _format_cpp_tool_results
    blocks = [("", "this is not c++")]
    results = [(False, -1, "", "syntax error")]
    out = _format_cpp_tool_results(blocks, results)
    assert "compile: FAILED" in out
    assert "syntax error" in out


def test_run_cpp_block_real_compile_and_run():
    """End-to-end: compile a tiny C++ program and verify stdout."""
    from src.nodes.generate_code import _run_cpp_block
    src = """
    #include <iostream>
    int main(){
        int a, b;
        std::cin >> a >> b;
        std::cout << a + b << std::endl;
        return 0;
    }
    """
    compiled, retcode, stdout, stderr = _run_cpp_block("3 4\n", src)
    assert compiled is True
    assert retcode == 0
    assert stdout.strip() == "7"


def test_run_cpp_block_compile_error():
    from src.nodes.generate_code import _run_cpp_block
    compiled, _retcode, _stdout, stderr = _run_cpp_block("", "this is not C++")
    assert compiled is False
    assert stderr  # some error message present


def test_execute_think_python_tools_handles_cpp_block(monkeypatch):
    """Mixed python+cpp block extraction: both kinds get executed in same iter."""
    from src.nodes import generate_code as gc

    py_runs = []
    cpp_runs = []

    monkeypatch.setattr(gc, "run_python", lambda b: (py_runs.append(b), (0, "py-out\n", ""))[1])
    monkeypatch.setattr(gc, "_run_cpp_block", lambda stdin, src: (cpp_runs.append((stdin, src)), (True, 0, "cpp-out\n", ""))[1])

    chat_calls = {"n": 0}
    def fake_chat(llm, hist, *, user_content, **kwargs):
        chat_calls["n"] += 1
        return "Verified. VERDICT: PROCEED", [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": "Verified. VERDICT: PROCEED"},
        ], list(hist)

    monkeypatch.setattr(gc, "chat_with_history", fake_chat)

    initial = (
        "Algorithm idea\n"
        "<run_python>print('hi')</run_python>\n"
        "<run_cpp>int main(){return 0;}</run_cpp>"
    )
    final, new, persisted, n_calls, n_blocks = gc._execute_think_python_tools(
        llm=object(),
        initial_response=initial,
        history=[],
    )
    assert n_calls == 1
    assert n_blocks == 2
    assert len(py_runs) == 1
    assert len(cpp_runs) == 1


def test_cpp_tools_disabled_skips_cpp_blocks(monkeypatch):
    """enable_cpp=False ignores <run_cpp> blocks."""
    from src.nodes import generate_code as gc

    cpp_runs = []
    monkeypatch.setattr(gc, "_run_cpp_block", lambda stdin, src: (cpp_runs.append((stdin, src)), (True, 0, "x", ""))[1])

    final, new, persisted, n_calls, n_blocks = gc._execute_think_python_tools(
        llm=object(),
        initial_response="<run_cpp>int main(){return 0;}</run_cpp>",
        history=[],
        enable_cpp=False,
    )
    assert cpp_runs == []
    assert n_calls == 0
    assert n_blocks == 0
