import unittest
from tac.blocks.model import ProtoBlock

class TestVisualDescription(unittest.TestCase):
    def test_visual_description_field(self):
        # Create a ProtoBlock instance and set the visual_description directly to simulate vision LLM output
        pb = ProtoBlock(
            task_description="Test task",
            write_files=[],
            context_files=[],
            block_id="test1",
            commit_message="Test commit",
            branch_name="test_branch"
        )
        pb.image_url = "dummy_image.png"
        pb.visual_description = "This image shows a dummy test scene with a clear sky."
        self.assertEqual(pb.visual_description, "This image shows a dummy test scene with a clear sky.")

if __name__ == "__main__":
    unittest.main()