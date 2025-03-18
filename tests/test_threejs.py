import unittest

from tac.trusty_agents.registry import TrustyAgentRegistry
from tac.trusty_agents.threejs import ThreeJS

# Create a dummy ProtoBlock for testing purposes.
class DummyProtoBlock:
    pass

class TestThreeJSAgent(unittest.TestCase):
    def test_registration(self):
        # Test that the threejs agent is registered in the registry.
        agent_class = TrustyAgentRegistry.get_agent("threejs")
        self.assertIsNotNone(agent_class, "ThreeJS agent not registered in TrustyAgentRegistry")

    def test_check_success(self):
        # Create an instance of the ThreeJS agent and test _check_impl.
        agent = ThreeJS()
        dummy_proto = DummyProtoBlock()
        codebase = {"dummy_file.js": "console.log('test');"}
        code_diff = "dummy diff"
        success, error_analysis, failure_type = agent.check(dummy_proto, codebase, code_diff)
        self.assertTrue(success, "The check should pass successfully.")
        self.assertEqual(error_analysis, "", "Error analysis should be an empty string for a successful check.")
        self.assertEqual(failure_type, "", "Failure type should be an empty string for a successful check.")

if __name__ == "__main__":
    unittest.main()