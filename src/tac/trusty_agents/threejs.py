from tac.trusty_agents.base import TrustyAgent, trusty_agent
from tac.blocks import ProtoBlock
import subprocess

@trusty_agent(
    name="threejs",
    description="A trusty agent for three.js integration checks",
    protoblock_prompt="Dummy prompt for three.js agent",
    prompt_target=""
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