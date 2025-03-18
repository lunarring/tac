from tac.trusty_agents.base import TrustyAgent, trusty_agent
from tac.blocks import ProtoBlock
import subprocess

@trusty_agent(
    name="threejs_unit_test",
    description="A trusty agent that runs npm-based unit tests for three.js implementations. This agent executes the 'npm run test:threejs' command to verify that JavaScript code interacting with the three.js library functions correctly. It checks for proper module imports, correct API usage, scene creation, and event handling in three.js applications.",
    protoblock_prompt="Describe the unit tests you've implemented for your three.js code. Focus on explaining what npm-based tests verify in your implementation, such as module loading, scene initialization, object creation, renderer setup, animation loops, event handlers, or WebGL context management. Note any mocking strategies used to test three.js components. Be sure to always shutdown any test servers after tests complete and before starting new tests, check if a server is already running.",
    prompt_target="coding_agent"
)
class ThreeJS(TrustyAgent):
    def _check_impl(self, protoblock: ProtoBlock, codebase: dict, code_diff: str):
        try:
            result = subprocess.run(["npm", "run", "test:threejs"], capture_output=True, text=True)
        except Exception as e:
            return False, str(e), "subprocess_exception"
        
        if result.returncode == 0:
            return True, "", ""
        else:
            error_output = (result.stdout + "\n" + result.stderr).strip()
            return False, error_output, "npm_test_failure"