"""Solvita Agent Entry Point"""

import argparse
import json
from pathlib import Path
from src.agent import SolvitaAgent


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Solvita - Algorithm Problem Solving Agent")
    parser.add_argument("--input", type=str, required=True, help="Input problem file (JSON)")
    parser.add_argument("--output", type=str, default="solution.cpp", help="Output solution file")
    parser.add_argument("--model", type=str, default="gpt-4", help="LLM model to use")
    parser.add_argument("--config", type=str, default="config", help="Config directory path")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    return parser.parse_args()


def load_problem(input_path: str) -> dict:
    """Load problem from JSON file"""
    pass


def save_solution(solution: dict, output_path: str) -> None:
    """Save solution to file"""
    pass


def main():
    """Main entry point"""
    args = parse_args()
    
    # Load problem
    problem_input = load_problem(args.input)
    
    # Initialize agent
    agent = SolvitaAgent(config_path=args.config)
    
    # Solve problem
    solution = agent.solve(problem_input)
    
    # Save solution
    save_solution(solution, args.output)
    
    print(f"Solution saved to {args.output}")


if __name__ == "__main__":
    main()

