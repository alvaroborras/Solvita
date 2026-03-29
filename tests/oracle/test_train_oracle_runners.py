import scripts.train_oracle as train_oracle


def test_resolve_correct_runners_stops_after_limit(monkeypatch, tmp_path):
    calls = {"compile": 0}

    def fake_compile_cpp(src, exe):
        calls["compile"] += 1
        return True, ""

    monkeypatch.setattr(train_oracle, "compile_cpp", fake_compile_cpp)

    solutions = [{"code": f"// solution {i}"} for i in range(10)]
    runners = train_oracle.resolve_correct_runners(solutions, tmp_path, max_runners=3)

    assert len(runners) == 3
    assert calls["compile"] == 3
