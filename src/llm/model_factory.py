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
        """Generate mock C++ code based on prompt content"""
        # Detect what kind of code to generate based on prompt
        if "competition" in prompt.lower() or "algorithm" in prompt.lower():
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
    cout << arr[0] << endl;

    return 0;
}
"""
        elif "fix" in prompt.lower() or "error" in prompt.lower():
            # Generate fixed code
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

    // Fixed solution
    cout << arr[0] << endl;

    return 0;
}
"""
        else:
            # Default mock code
            return """#include <iostream>
#include <vector>
using namespace std;

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    cin >> n;

    cout << n << endl;

    return 0;
}
"""

