"""Benchmark execution modes."""

from .pipeline import run_pipeline_benchmark_case
from .single_pass import run_single_pass_case

__all__ = ["run_pipeline_benchmark_case", "run_single_pass_case"]
