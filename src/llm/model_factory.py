"""LLM Model Factory"""

from typing import Dict, Any, Optional
from .base_model import BaseLLM


class ModelFactory:
    """Factory for creating LLM model instances"""

    @staticmethod
    def create(model_name: str, config: Dict[str, Any] = None) -> BaseLLM:
        """
        Create LLM model instance.

        Args:
            model_name: Model name (gpt-4, claude-3-sonnet, etc.)
            config: Optional configuration dict

        Returns:
            LLM model instance
        """
        config = config or {}

        # Determine provider from model name
        if 'gpt' in model_name.lower():
            from .openai_model import OpenAIModel
            return OpenAIModel(config)
        elif 'claude' in model_name.lower():
            from .anthropic_model import AnthropicModel
            return AnthropicModel(config)
        else:
            # Fallback to mock LLM for development
            return MockLLM(config)

    @staticmethod
    def create_model(model_type: str, config: Dict) -> BaseLLM:
        """Legacy method for backwards compatibility"""
        return ModelFactory.create(model_type, config)

    @staticmethod
    def create_from_config(config: Dict[str, Any]) -> BaseLLM:
        """
        Create LLM instance from workflow config dict.

        Args:
            config: State config dict containing 'model' and other params

        Returns:
            LLM model instance
        """
        model_name = config.get('model', 'mock')
        return ModelFactory.create(model_name, config)

    @staticmethod
    def create_mock() -> BaseLLM:
        """
        Create mock LLM instance for development/testing.

        Returns:
            MockLLM instance
        """
        return MockLLM({})


class MockLLM(BaseLLM):
    """Mock LLM for testing without API keys"""

    def __init__(self, config: Dict):
        self.config = config

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate mock response"""
        return self._generate_mock_code(prompt)

    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """Generate mock response with system message"""
        return self._generate_mock_code(user)

    def chat(self, messages: list, **kwargs) -> str:
        """Generate mock response from chat messages"""
        # Extract user message content
        user_content = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break

        return self._generate_mock_code(user_content)

    def _generate_mock_code(self, prompt: str) -> str:
        """Generate mock response based on prompt content type"""
        prompt_lower = prompt.lower()

        # Detect if this is a planning request
        planning_keywords = ["design", "optimal", "algorithm_choice", "implementation_steps", "solution_plan"]
        if any(keyword in prompt_lower for keyword in planning_keywords):
            # Return mock planning JSON
            return self._generate_mock_plan(prompt)

        # Otherwise, treat as code generation request
        return self._generate_mock_cpp_code(prompt)

    def _generate_mock_plan(self, prompt: str) -> str:
        """Generate mock planning JSON response"""
        import json

        # Detect problem type from prompt to customize the plan
        prompt_lower = prompt.lower()

        # Choose algorithm based on keywords in prompt
        if "array" in prompt_lower or "two pointer" in prompt_lower:
            algorithm = "Two Pointers"
            steps = [
                "1. Sort the array if needed",
                "2. Initialize two pointers (left and right)",
                "3. Move pointers based on comparison",
                "4. Handle edge cases",
                "5. Return the result"
            ]
            insights = [
                "Two pointers technique reduces time complexity to O(n)",
                "Avoids the need for extra space with hash maps",
                "Works well for sorted or partially sorted arrays"
            ]
        elif "hash" in prompt_lower or "map" in prompt_lower:
            algorithm = "Hash Map"
            steps = [
                "1. Create a hash map to store values",
                "2. Iterate through the input",
                "3. Check if complement exists in map",
                "4. Add current element to map",
                "5. Return the result"
            ]
            insights = [
                "Hash map provides O(1) average case lookup",
                "Single pass through the data achieves O(n) time complexity",
                "Space complexity is O(n) for the map storage"
            ]
        elif "dp" in prompt_lower or "dynamic" in prompt_lower:
            algorithm = "Dynamic Programming"
            steps = [
                "1. Define the state: dp[i] represents...",
                "2. Initialize base case",
                "3. Build the DP table bottom-up",
                "4. Handle transitions carefully",
                "5. Return the final answer"
            ]
            insights = [
                "DP avoids redundant subproblem calculations",
                "Memoization reduces exponential complexity to polynomial",
                "Can be optimized with space-efficient techniques"
            ]
        elif "graph" in prompt_lower or "bfs" in prompt_lower or "dfs" in prompt_lower:
            algorithm = "Graph Traversal (BFS/DFS)"
            steps = [
                "1. Build the graph representation",
                "2. Initialize visited set and queue/stack",
                "3. Perform BFS or DFS traversal",
                "4. Process nodes as they are visited",
                "5. Return accumulated results"
            ]
            insights = [
                "BFS explores level by level using a queue",
                "DFS uses a stack for deeper exploration first",
                "Time complexity is O(V + E) for connected graphs"
            ]
        else:
            # Default algorithm
            algorithm = "Brute Force"
            steps = [
                "1. Parse input",
                "2. Generate all possible combinations",
                "3. Evaluate each combination",
                "4. Keep track of the best solution",
                "5. Return the result"
            ]
            insights = [
                "Simple and straightforward approach",
                "Works for small input sizes",
                "Can be optimized with problem-specific insights"
            ]

        plan_data = {
            "algorithm_choice": algorithm,
            "implementation_steps": steps,
            "solution_plan": {
                "algorithm": algorithm,
                "approach": f"Using {algorithm} to solve the problem optimally",
                "key_insights": insights
            }
        }

        return json.dumps(plan_data)

    def _generate_mock_cpp_code(self, prompt: str) -> str:
        """Generate mock C++ code based on prompt content"""
        prompt_lower = prompt.lower()

        if "fix" in prompt_lower or "error" in prompt_lower or "compilation" in prompt_lower:
            # Generate fixed code with error handling
            return """#include <iostream>
#include <vector>
#include <algorithm>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    cin >> n;

    if (n <= 0) {
        cout << 0 << endl;
        return 0;
    }

    vector<int> arr(n);
    for (int i = 0; i < n; i++) {
        cin >> arr[i];
    }

    // Fixed solution with proper error handling
    int result = 0;
    for (int i = 0; i < n; i++) {
        result += arr[i];
    }

    cout << result << endl;

    return 0;
}
"""
        else:
            # Generate a generic competitive programming solution
            return """#include <iostream>
#include <vector>
#include <algorithm>
#include <map>
#include <set>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    cin >> n;

    vector<int> arr(n);
    for (int i = 0; i < n; i++) {
        cin >> arr[i];
    }

    // Mock solution: process input and output result
    int result = 0;
    for (int i = 0; i < n; i++) {
        result += arr[i];
    }

    cout << result << endl;

    return 0;
}
"""

