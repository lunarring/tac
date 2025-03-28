import os
import tempfile
import shutil
from PIL import Image
from tac.trusty_agents.threejs_vision_before_after import ThreeJSVisionBeforeAfterAgent

class DummyProtoBlock:
    def __init__(self):
        self.write_files = []
        self.context_files = []
        self.trusty_agent_prompts = {
            "threejs_vision_before_after": "Expected: left image is red and right image is blue."
        }

def test_threejs_vision_before_after_stitching():
    # Create two temporary images for before (red) and after (blue) states
    tmp_dir = tempfile.mkdtemp()
    try:
        before_path = os.path.join(tmp_dir, "before.png")
        after_path = os.path.join(tmp_dir, "after.png")
        
        # Create a red image: 100x50
        img_before = Image.new("RGB", (100, 50), color="red")
        img_before.save(before_path, format="PNG")
        
        # Create a blue image: 80x60
        img_after = Image.new("RGB", (80, 60), color="blue")
        img_after.save(after_path, format="PNG")
        
        # Instantiate the agent and override _capture_state to return the after image path.
        agent = ThreeJSVisionBeforeAfterAgent()
        # Set the before screenshot path manually
        agent.before_screenshot_path = before_path
        # Override _capture_state so that when capturing after state it returns our after image.
        agent._capture_state = lambda: after_path
        
        # Call _check_impl with a dummy proto block and dummy code inputs.
        dummy_pb = DummyProtoBlock()
        success, analysis, failure = agent._check_impl(dummy_pb, codebase="", code_diff="")
        
        # Load the stitched (comparison) image.
        comparison_img = Image.open(agent.comparison_path)
        
        # Expected dimensions:
        # before image is rescaled from 100x50 to 120x60, dummy (1) remains, after is 80x60,
        # plus 2*border (2*10) = 120 + 1 + 80 + 20 = 221
        expected_width = 221
        expected_height = max(50, 60)  # 60
        assert comparison_img.width == expected_width, f"Expected width {expected_width}, got {comparison_img.width}"
        assert comparison_img.height == expected_height, f"Expected height {expected_height}, got {comparison_img.height}"
        
        # Check left portion contains red (from before image)
        left_pixel = comparison_img.getpixel((50, 30))
        assert left_pixel == (255, 0, 0), f"Expected red in left region, got {left_pixel}"
        
        # The dummy image is inserted between the before and after images.
        # Its x position: rescaled before width (120) + border (10) = 130, width = 1, so pixel at (130, 30) should be black.
        dummy_pixel = comparison_img.getpixel((130, 30))
        assert dummy_pixel == (0, 0, 0), f"Expected black in dummy image region, got {dummy_pixel}"
        
        # Check right portion contains blue (from after image)
        # right image is pasted at x = rescaled before width (120) + border (10) + dummy width (1) + border (10) = 141.
        right_pixel = comparison_img.getpixel((141 + 40, 30))  # 40 pixels into the after image area
        # Blue is (0, 0, 255)
        assert right_pixel == (0, 0, 255), f"Expected blue in right region, got {right_pixel}"
        
    finally:
        # Clean up temporary files and directory
        shutil.rmtree(tmp_dir)
        if agent.comparison_path and os.path.exists(agent.comparison_path):
            os.remove(agent.comparison_path)

if __name__ == "__main__":
    test_threejs_vision_before_after_stitching()
    print("ThreeJSVisionBeforeAfterAgent stitching test passed.")