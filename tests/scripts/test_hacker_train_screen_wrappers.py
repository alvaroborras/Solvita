from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_main_screen_wrapper_contains_required_training_args():
    text = (ROOT / "scripts" / "run_hacker_train_screen.sh").read_text(encoding="utf-8")

    assert "screen -L -Logfile" in text
    assert "--hacker-candidate-records-path" in text
    assert "--memory-snapshot-dir" in text
    assert "--memory-snapshot-every" in text
    assert "scripts/train_hacker.py" in text


def test_parallel_and_smoke_wrappers_delegate_to_main_wrapper():
    parallel_text = (ROOT / "scripts" / "run_hacker_train_parallel_screen.sh").read_text(encoding="utf-8")
    main_text = (ROOT / "scripts" / "run_hacker_train_screen.sh").read_text(encoding="utf-8")
    smoke_text = (ROOT / "scripts" / "run_hacker_train_smoke_screen.sh").read_text(encoding="utf-8")

    assert 'WORKERS="${WORKERS:-12}"' in main_text
    assert "run_hacker_train_screen.sh" in parallel_text
    assert 'WORKERS="${WORKERS:-12}"' in parallel_text

    assert "run_hacker_train_screen.sh" in smoke_text
    assert 'LIMIT="${LIMIT:-5}"' in smoke_text
