"""Problem Parser"""

from typing import Dict, List


class ProblemParser:
    """Parser for algorithm problem descriptions"""
    
    def __init__(self):
        """Initialize problem parser"""
        pass
    
    def parse(self, problem_input: Dict) -> Dict:
        """
        Parse problem input
        
        Args:
            problem_input: Raw problem input with description and public tests
            
        Returns:
            Parsed problem structure
        """
        pass
    
    def extract_constraints(self, description: str) -> Dict:
        """Extract constraints from problem description"""
        pass
    
    def extract_input_format(self, description: str) -> str:
        """Extract input format from problem description"""
        pass
    
    def extract_output_format(self, description: str) -> str:
        """Extract output format from problem description"""
        pass
    
    def identify_problem_type(self, description: str) -> List[str]:
        """Identify problem type (DP, graph, math, etc.)"""
        pass

