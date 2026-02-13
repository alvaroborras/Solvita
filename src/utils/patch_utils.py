"""
Utilities for parsing and applying SEARCH/REPLACE edit blocks.
"""

import re
from typing import List, Tuple, Optional
from difflib import unified_diff


class SearchReplaceBlock:
    """A single SEARCH/REPLACE edit block."""
    def __init__(self, search: str, replace: str):
        self.search = search
        self.replace = replace


def parse_search_replace_blocks(text: str) -> List[SearchReplaceBlock]:
    """
    Parse SEARCH/REPLACE blocks from LLM output.
    
    Expected format:
    <<<<<<< SEARCH
    <exact code to find>
    =======
    <replacement code>
    >>>>>>> REPLACE
    
    Returns:
        List of SearchReplaceBlock objects
    """
    blocks = []
    
    # Pattern to match SEARCH/REPLACE blocks
    pattern = r'<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE'
    
    matches = re.findall(pattern, text, re.DOTALL)
    
    for search, replace in matches:
        blocks.append(SearchReplaceBlock(search, replace))
    
    return blocks


def apply_search_replace_blocks(
    original_code: str,
    blocks: List[SearchReplaceBlock]
) -> Tuple[bool, str, str]:
    """
    Apply SEARCH/REPLACE blocks to original code.
    
    Args:
        original_code: The original code string
        blocks: List of SearchReplaceBlock to apply
    
    Returns:
        (success, patched_code, error_message)
        - success: True if all blocks applied successfully
        - patched_code: The patched code (or original if failed)
        - error_message: Error description if failed
    """
    if not blocks:
        return False, original_code, "No SEARCH/REPLACE blocks found"
    
    current_code = original_code
    
    for i, block in enumerate(blocks):
        # Count occurrences of search string
        count = current_code.count(block.search)
        
        if count == 0:
            return False, original_code, f"Block {i+1}: SEARCH string not found in code"
        elif count > 1:
            return False, original_code, f"Block {i+1}: SEARCH string matches {count} times (must be unique)"
        
        # Apply replacement
        current_code = current_code.replace(block.search, block.replace, 1)
    
    # Check if code actually changed
    if current_code == original_code:
        return False, original_code, "Patch resulted in no changes"
    
    return True, current_code, ""


def compute_unified_diff(original: str, patched: str, filename: str = "solution.cpp") -> str:
    """
    Compute unified diff for logging/debugging.
    
    Args:
        original: Original code
        patched: Patched code
        filename: Filename to show in diff
    
    Returns:
        Unified diff string
    """
    original_lines = original.splitlines(keepends=True)
    patched_lines = patched.splitlines(keepends=True)
    
    diff = unified_diff(
        original_lines,
        patched_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=""
    )
    
    return "".join(diff)
