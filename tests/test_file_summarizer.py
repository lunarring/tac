import os
import tempfile
import unittest

# Import the FileSummarizer from the source
from src.tac.utils.file_summarizer import FileSummarizer

class DummyLLMClient:
    def chat_completion(self, messages):
        # For testing, simply echo back the prompt details with inserted markers.
        prompt = messages[-1].content if hasattr(messages[-1], 'content') else messages[-1]['content']
        # Create a dummy summary using markers so _analyze_file parsing is bypassed.
        response = ""
        if "func_a" in prompt:
            response += "[FUNCTION] func_a\nThis function does something important.\n"
        if "func_b" in prompt:
            response += "[FUNCTION] func_b\nThis function does another task.\n"
        if "MyClass" in prompt:
            response += "[CLASS] MyClass\nThis class encapsulates functionality.\n  [METHOD] method\nThis method performs an operation.\n"
        return response.strip()

class TestFileSummarizer(unittest.TestCase):
    def setUp(self):
        self.summarizer = FileSummarizer()
        # Override the LLM client with our dummy client for deterministic tests.
        self.summarizer.llm_client = DummyLLMClient()
        # Reduce timeout for tests
        self.summarizer.timeout = 5

    def test_analyze_file_summary(self):
        test_code = '''
def func_a():
    pass

def func_b():
    pass

class MyClass:
    def method(self):
        pass
'''
        # Create a temporary python file with test code.
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            tmp.write(test_code)
            tmp_path = tmp.name

        try:
            analysis = self.summarizer._analyze_file(tmp_path)
            # Ensure no error was returned
            self.assertIsNone(analysis.get("error"), f"Unexpected error: {analysis.get('error')}")
            summary = analysis.get("content")
            # Check that the summary includes details for the functions and class.
            self.assertIn("func_a", summary, "Summary missing func_a details.")
            self.assertIn("func_b", summary, "Summary missing func_b details.")
            self.assertIn("MyClass", summary, "Summary missing MyClass details.")
        finally:
            os.remove(tmp_path)

if __name__ == '__main__':
    unittest.main()
