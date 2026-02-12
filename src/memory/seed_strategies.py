"""Seed strategies for cold-starting the memory system."""

from typing import List, Dict
from src.memory.types import StrategyType

SEED_STRATEGIES: List[Dict] = [
    # --- General / Standard ---
    {
        "text": "ALWAYS use testlib's rnd.next(L, R) for uniform integers. Do NOT use rand() or std::random_device.",
        "kind": StrategyType.WARNING,
        "tags": ["general", "random"],
    },
    {
        "text": "To shuffle a vector, use rnd.shuffle(v.begin(), v.end()). Do NOT use std::shuffle with default engine.",
        "kind": StrategyType.ADVICE,
        "tags": ["general", "random"],
    },
    {
        "text": "Output exactly what is asked. Do NOT print debug info or prompts like 'Enter n:'.",
        "kind": StrategyType.WARNING,
        "tags": ["general", "io"],
    },
    {
        "text": "Use println() for the last element or vectors to ensure proper newline termination.",
        "kind": StrategyType.ADVICE,
        "tags": ["general", "io"],
    },
    {
        "text": "When generating distinct values, use std::set or std::unordered_set. If n is large and range is small, ensure n <= range size.",
        "kind": StrategyType.WARNING,
        "tags": ["general", "distinct"],
    },
    {
        "text": "For floating point outputs, use std::fixed and std::setprecision(X) to match problem requirement.",
        "kind": StrategyType.ADVICE,
        "tags": ["general", "float"],
    },
    {
        "text": "Use fast I/O (cin.tie(NULL)) to avoid TLE on large inputs.",
        "kind": StrategyType.ADVICE,
        "tags": ["general", "performance"],
    },

    # --- Graphs & Trees ---
    {
        "text": "To generate a random tree, use Prüfer sequence or randomly attach node i (for i=2..n) to parent in [1..i-1] and shuffle labels.",
        "kind": StrategyType.ADVICE,
        "tags": ["graph", "tree"],
    },
    {
        "text": "A tree specifically means n nodes and n-1 edges with no cycles and connectivity. Do not just generate random edges.",
        "kind": StrategyType.WARNING,
        "tags": ["graph", "tree"],
    },
    {
        "text": "To ensure a connected graph with m edges: first generate a random spanning tree (n-1 edges), then add m-(n-1) random edges.",
        "kind": StrategyType.ADVICE,
        "tags": ["graph", "connected"],
    },
    {
        "text": "Prevent self-loops (u != v) and multi-edges (use std::set<std::pair<int,int>> to track existing edges).",
        "kind": StrategyType.WARNING,
        "tags": ["graph", "simple_graph"],
    },

    # --- Strings ---
    {
        "text": "To generate a palindrome of length L: generate first floor(L/2) chars randomly, then mirror them.",
        "kind": StrategyType.ADVICE,
        "tags": ["string", "palindrome"],
    },
    {
        "text": "Strictly follow character set constraints (e.g., lowercase only 'a'-'z').",
        "kind": StrategyType.WARNING,
        "tags": ["string", "charset"],
    },
    {
        "text": "Ensure string length is at least 1 unless empty strings are explicitly allowed.",
        "kind": StrategyType.WARNING,
        "tags": ["string", "length"],
    },

    # --- Math & Arrays ---
    {
        "text": "A permutation of length n MUST contain numbers 1..n exactly once. Use std::iota and rnd.shuffle.",
        "kind": StrategyType.ADVICE,
        "tags": ["math", "permutation"],
    },
    {
        "text": "For queries [L, R], ensure 1 <= L <= R <= n.",
        "kind": StrategyType.WARNING,
        "tags": ["math", "interval"],
    },
    {
        "text": "When n * n can exceed 2^31-1, use long long for calculations.",
        "kind": StrategyType.WARNING,
        "tags": ["math", "overflow"],
    },
    {
        "text": "If constraints say values up to 10^18, use long long, not int.",
        "kind": StrategyType.WARNING,
        "tags": ["math", "overflow"],
    },
]
