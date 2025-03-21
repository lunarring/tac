from tac.trusty_agents.base import TrustyAgent, trusty_agent
from tac.blocks import ProtoBlock
import subprocess
import os

@trusty_agent(
    name="threejs_unit_test",
    description="A trusty agent that runs npm-based unit tests for three.js implementations. This agent executes the 'npm run test:threejs' command to verify that JavaScript code interacting with the three.js library functions correctly. It checks for proper module imports, correct API usage, scene creation, and event handling in three.js applications.",
    protoblock_prompt="""Describe the unit tests you've implemented for your three.js code. Explain that your npm-based tests verify module loading (ensuring Three.js loads correctly), scene and object initialization (creating the scene, camera, renderer, and mesh), proper renderer setup and animation loop functionality, and any event or WebGL context management. Mention that you're using jsdom to simulate a browser environment for testing. Also note that your project includes a package.json in the root directory to manage dependencies and run tests. For example, the package.json should include scripts like "test": "mocha tests/*.js", have three as a dependency, and chai, jsdom, and mocha as devDependencies. Then run npm install followed by npm test to execute the tests.""",
    prompt_target="coding_agent"
)
class ThreeJS(TrustyAgent):
    def _check_impl(self, protoblock: ProtoBlock, codebase: dict, code_diff: str):
        try:
            result = subprocess.run(["npm", "test"], capture_output=True, text=True)
            print(f"npm test result: {result.stdout}")
        except Exception as e:
            return False, str(e), "subprocess_exception"
        
        if result.returncode == 0:
            return True, "", ""
        else:
            error_output = (result.stdout + "\n" + result.stderr).strip()
            return False, error_output, "npm_test_failure"

if __name__ == "__main__":
    # Switch to the project directory
    os.chdir("/Users/jjj/git/tmp_tac/struct")
    
    # Install dependencies first
    try:
        subprocess.run(["npm", "install"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e.stderr}")
        exit(1)
    
    # Example usage of the ThreeJS trusty agent
    from tac.blocks import ProtoBlock
    
    # Create a protoblock with test description
    test_block = ProtoBlock(
        task_description="""Test Three.js implementation:
        - Scene initialization
        - Camera setup
        - Basic mesh rendering
        - Animation loop
        """,
        write_files=[],
        context_files=[],
        block_id="threejs_test",
        trusty_agents=["threejs_unit_test"]  # Explicitly set the trusty agent
    )
    
    # Initialize the agent
    agent = ThreeJS()
    
    # Run the check
    success, message, error_type = agent.check(test_block, {}, "")
    
    print(f"Test {'passed' if success else 'failed'}")
    if not success:
        print(f"Error: {message}")