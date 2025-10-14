"""Prompt Templates"""

from typing import Dict


class PromptTemplates:
    """Prompt templates for LLM interactions"""
    
    # Problem understanding prompts
    UNDERSTAND_PROBLEM = """
    Analyze the following algorithm problem:
    {problem_description}
    
    Provide:
    1. Problem type classification
    2. Key constraints
    3. Input/output format
    4. Potential approaches
    """
    
    # Test generation prompts
    GENERATE_TESTS = """
    Generate test cases for the following problem:
    {problem_description}
    
    Public tests:
    {public_tests}
    
    Generate {num_tests} additional test cases including edge cases and corner cases.
    """
    
    # Solution planning prompts
    PLAN_SOLUTION = """
    Plan solution approaches for:
    {problem_description}
    
    Retrieved knowledge:
    {knowledge}
    
    Provide multiple approaches ranked by success probability.
    """
    
    # Code generation prompts
    GENERATE_CPP = """
    Generate C++ solution for:
    {problem_description}
    
    Approach:
    {approach}
    
    Requirements:
    - Use standard C++ libraries
    - Optimize for time complexity
    - Handle all edge cases
    """
    
    # Feedback prompts
    ANALYZE_FEEDBACK = """
    Analyze the following test failures:
    {failed_tests}
    
    Current code:
    {code}
    
    Provide:
    1. Error pattern analysis
    2. Root cause
    3. Suggested fix
    """
    
    @staticmethod
    def format_prompt(template: str, **kwargs) -> str:
        """Format prompt template with provided arguments"""
        pass

