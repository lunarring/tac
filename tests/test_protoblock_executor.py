import unittest

class DummyAgent:
    def run(self, protoblock):
        # Verify that all required keys exist
        required_keys = ['task', 'test', 'write_files', 'context_files', 'commit_message']
        for key in required_keys:
            if key not in protoblock:
                raise ValueError(f"Missing required key: {key}")
        return {'status': 'success', 'message': 'Protoblock executed successfully'}

class TestProtoblockExecutor(unittest.TestCase):
    def test_dummy_agent_success(self):
        protoblock = {
            'task': 'dummy task',
            'test': 'dummy test',
            'write_files': {'dummy.py': 'print("Hello")'},
            'context_files': {'config.yaml': 'key: value'},
            'commit_message': 'dummy commit'
        }
        agent = DummyAgent()
        response = agent.run(protoblock)
        self.assertEqual(response.get('status'), 'success')
        self.assertEqual(response.get('message'), 'Protoblock executed successfully')

if __name__ == '__main__':
    unittest.main()
