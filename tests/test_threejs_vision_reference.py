import os
import tempfile
import uuid
from PIL import Image
import shutil

import pytest

# Create a dummy protoblock class for testing purposes
class DummyProtoBlock:
    def __init__(self):
        self.write_files = []
        self.context_files = []
        self.trusty_agent_prompts = {"threejs_vision_reference": "The after state should match the reference design."}

# Create a helper function to generate a dummy image file
def create_dummy_image(color, size=(100, 100)):
    img = Image.new("RGB", size, color=color)
    temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(temp_file, format="PNG")
    temp_file.close()
    return temp_file.name

@pytest.fixture
def dummy_images():
    before_img_path = create_dummy_image("red")
    after_img_path = create_dummy_image("green")
    reference_img_path = create_dummy_image("blue")
    yield before_img_path, after_img_path, reference_img_path
    os.unlink(before_img_path)
    os.unlink(after_img_path)
    os.unlink(reference_img_path)

class DummyLLMClient:
    def __init__(self, response):
        self.response = response

    def vision_chat_completion(self, messages, image_path, temperature=None):
        return self.response

@pytest.fixture
def dummy_agent(dummy_images):
    # Import the agent class here to ensure proper context
    from tac.trusty_agents.threejs_vision_reference import ThreeJSVisionReferenceAgent
    agent = ThreeJSVisionReferenceAgent()
    # Instead of capturing the state via browser, we monkeypatch _capture_state to return our dummy after image
    before_img, after_img, ref_img = dummy_images
    agent.before_screenshot_path = before_img
    # Override _capture_state to return the after image path
    agent._capture_state = lambda: after_img
    agent.set_reference_image(ref_img)
    # Override the llm_client with a dummy that returns "YES" for successful verification
    agent.llm_client = DummyLLMClient("YES - The current state matches the reference image.")
    return agent

def test_threejs_vision_reference_success(dummy_agent):
    dummy_proto = DummyProtoBlock()
    success, analysis, error_type = dummy_agent._check_impl(dummy_proto, "", "")
    # Ensure that the composite image was created
    assert dummy_agent.comparison_path is not None
    assert os.path.exists(dummy_agent.comparison_path)
    # Clean up the composite image created during the test
    os.unlink(dummy_agent.comparison_path)
    # Verify that the analysis indicates success
    assert success is True
    assert "yes" in analysis.lower()
    assert error_type == ""
    
def test_threejs_vision_reference_failure(dummy_agent, dummy_images):
    # Now test failure case by making dummy LLM return "NO"
    dummy_agent.llm_client = DummyLLMClient("NO - The current state does not match the reference image.")
    dummy_proto = DummyProtoBlock()
    success, analysis, error_type = dummy_agent._check_impl(dummy_proto, "", "")
    # Ensure that the composite image was created
    assert dummy_agent.comparison_path is not None
    assert os.path.exists(dummy_agent.comparison_path)
    os.unlink(dummy_agent.comparison_path)
    # Verify that the analysis indicates failure
    assert success is False
    assert "no" in analysis.lower()
    assert error_type == "Visual comparison failed"
    
def test_missing_reference_image(dummy_agent):
    # Test that providing no reference image causes an error
    dummy_agent.reference_image_path = None
    dummy_agent.reference_image = None
    dummy_proto = DummyProtoBlock()
    success, analysis, error_type = dummy_agent._check_impl(dummy_proto, "", "")
    assert success is False
    assert "Reference image not provided" in analysis
    assert error_type == "Missing reference image"