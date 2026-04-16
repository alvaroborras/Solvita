"""Backward-compatibility shim — re-exports from single_pass.py.

Historical benchmark results reference mode="gpt52_single_pass".  New code
should import from src.benchmark.modes.single_pass directly.
"""

from src.benchmark.modes.single_pass import (  # noqa: F401
    build_single_pass_config as build_gpt52_single_pass_config,
    build_single_pass_prompt,
    run_single_pass_case as run_gpt52_single_pass_case,
)

__all__ = [
    "build_gpt52_single_pass_config",
    "build_single_pass_prompt",
    "run_gpt52_single_pass_case",
]
