import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from src.utils import prompt_templates as pt


def test_load_prompt_templates_returns_dict():
    root = pt.load_prompt_templates()
    assert "abstract_problem" in root
    assert "generate_code" in root


def test_get_nested_template_resolves_key():
    root = pt.load_prompt_templates()
    s = pt.get_nested_template(root, "abstract_problem.system")
    assert isinstance(s, str)
    assert len(s) > 10


def test_get_nested_template_raises_on_missing():
    root = pt.load_prompt_templates()
    with pytest.raises(KeyError):
        pt.get_nested_template(root, "does.not.exist")


def test_render_placeholders():
    out = pt.render_placeholders("Hello <NAME>", {"NAME": "world"})
    assert out == "Hello world"


def test_clear_prompt_template_cache():
    pt.clear_prompt_template_cache()
    pt.load_prompt_templates()
