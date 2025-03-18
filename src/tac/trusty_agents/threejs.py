from tac.trusty_agents.base import TrustyAgent, trusty_agent
from tac.blocks import ProtoBlock

@trusty_agent(
    name="threejs",
    description="A trusty agent for three.js integration checks",
    protoblock_prompt="Dummy prompt for three.js agent",
    prompt_target=""
)
class ThreeJS(TrustyAgent):
    def _check_impl(self, protoblock: ProtoBlock, codebase: dict, code_diff: str):
        # Dummy implementation that always returns a successful check.
        return True, "", ""