import os
import unittest
from tac.agents.trusty.performance import PerformanceTestingAgent

class DummyGeneral:
    test_path = "dummy_tests"

class DummyConfig:
    general = DummyGeneral()

class TestPerformanceTestingAgentUtilities(unittest.TestCase):
    def setUp(self):
        # Create an instance without calling __init__ to avoid triggering full initialization.
        self.agent = PerformanceTestingAgent.__new__(PerformanceTestingAgent)
        # Assign a dummy config with a test_path to simulate configuration.
        self.agent.config = DummyConfig()

    def test_clean_function_name(self):
        # Test that clean_function_name removes invalid characters and adjusts the starting character.
        input_name = "123 fn-(test)"
        expected = "f_123fntest"
        result = self.agent.clean_function_name(input_name)
        self.assertEqual(result, expected)

    def test_get_test_function(self):
        # Test that get_test_function returns the proper test file path.
        dummy_function_name = "myFunc"
        expected = os.path.join(self.agent.config.general.test_path, f"test_performance_{dummy_function_name}.py")
        result = self.agent.get_test_function(dummy_function_name)
        self.assertEqual(result, expected)

if __name__ == "__main__":
    unittest.main()