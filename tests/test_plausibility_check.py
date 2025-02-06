import unittest
from src.tac.core.plausibility_check import PlausibilityChecker

# Create a dummy protoblock that satisfies the required attributes
class DummyProtoBlock:
    def __init__(self):
        self.block_id = "dummy_id"
        self.task_description = "Dummy task description"
        self.test_specification = "Dummy test specification"
        self.write_files = "Dummy write files"
        self.context_files = "Dummy context files"

class TestPlausibilityChecker(unittest.TestCase):
    def test_plausibility_check_success(self):
        # Create dummy git diff string
        dummy_git_diff = (
            "diff --git a/sample.txt b/sample.txt\n"
            "index 1234567..89abcde 100644\n"
            "--- a/sample.txt\n"
            "+++ b/sample.txt\n"
            "@@ -1 +1 @@\n"
            "-Hello World\n"
            "+Hello Python"
        )
        # Create dummy protoblock with required attributes
        dummy_protoblock = DummyProtoBlock()

        # Instantiate the PlausibilityChecker
        checker = PlausibilityChecker()

        # Patch the llm_client's chat_completion to return a controlled response
        def dummy_chat_completion(messages, temperature=None, max_tokens=None, stream=False):
            return "DETAILED ANALYSIS: This is a dummy analysis report. PLAUSIBILITY SCORE RATING: A"
        checker.llm_client.chat_completion = dummy_chat_completion

        # Call check_implementation and get the response
        response = checker.check_implementation(dummy_protoblock, dummy_git_diff)

        # Assert that the response is non-empty and contains expected keywords
        self.assertTrue(response)
        self.assertIn("DETAILED ANALYSIS", response)
        self.assertIn("PLAUSIBILITY SCORE RATING", response)

if __name__ == "__main__":
    unittest.main()
