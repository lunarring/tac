import sys
import time
import io
import subprocess
import unittest
from src.tac.agents.aider_agent import AiderAgent
from src.tac.protoblock.protoblock import ProtoBlock

class DummyProcess:
    def __init__(self, output_lines, delay=0.01):
        self.output_lines = output_lines
        self.index = 0
        self.returncode = 0
        self.stdout = self
        self.stderr = self

    def readline(self):
        if self.index < len(self.output_lines):
            line = self.output_lines[self.index]
            self.index += 1
            time.sleep(0.01)
            return line
        return ""

    def poll(self):
        if self.index >= len(self.output_lines):
            return 0
        return None

    def communicate(self):
        remaining_stdout = ''.join(self.output_lines[self.index:])
        remaining_stderr = ""
        self.index = len(self.output_lines)
        return (remaining_stdout, remaining_stderr)

    def kill(self):
        self.returncode = -1

class DummyProtoBlock(ProtoBlock):
    task_description = "dummy task"
    test_specification = "dummy test"
    test_data_generation = "dummy data"
    write_files = []
    context_files = []
    block_id = "dummyid"
    branch_name = None
    commit_message = "dummy commit"
    test_results = None

class TestAiderAgentRealTimeOutput(unittest.TestCase):
    def test_real_time_output(self):
        # Prepare dummy output lines
        output_lines = ["Line 1\n", "Line 2\n", "Line 3\n"]
        # Monkeypatch subprocess.Popen in AiderAgent to use DummyProcess
        original_popen = subprocess.Popen
        subprocess.Popen = lambda *args, **kwargs: DummyProcess(output_lines)
        try:
            config = {'aider': {'model': 'dummy-model', 'model_settings': {'timeout': 10}}}
            agent = AiderAgent(config)
            dummy_proto = DummyProtoBlock()
            # Capture stdout
            new_stdout = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = new_stdout
            agent.run(dummy_proto)
            sys.stdout = old_stdout
            output = new_stdout.getvalue()
            # Verify that real-time output was printed
            self.assertIn("Line 1", output)
            self.assertIn("Line 2", output)
            self.assertIn("Line 3", output)
        finally:
            subprocess.Popen = original_popen

if __name__ == '__main__':
    unittest.main()
