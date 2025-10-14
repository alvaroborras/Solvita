"""Error Parser"""

from typing import Dict, Optional


class ErrorParser:
    """Parse compilation and runtime errors"""
    
    def __init__(self):
        """Initialize error parser"""
        pass
    
    def parse_compilation_error(self, stderr: str) -> Dict:
        """Parse C++ compilation error"""
        pass
    
    def parse_runtime_error(self, stderr: str, test: Dict) -> Dict:
        """Parse runtime error"""
        pass
    
    def parse_wrong_answer(self, expected: str, actual: str, test: Dict) -> Dict:
        """Parse wrong answer error"""
        pass
    
    def extract_error_location(self, error_message: str) -> Optional[int]:
        """Extract line number from error message"""
        pass
    
    def categorize_error(self, error: Dict) -> str:
        """Categorize error type (syntax, logic, TLE, MLE, etc.)"""
        pass

