import os
import tempfile
from tac.blocks.generator import compute_visual_description

def test_visual_description_file_not_found():
    # Provide a file path that does not exist
    non_existing_path = "non_existing_image.png"
    description = compute_visual_description(non_existing_path)
    assert "Image file not found" in description

def test_visual_description_success(monkeypatch):
    # Create a temporary dummy image file
    from PIL import Image
    temp_dir = tempfile.gettempdir()
    image_path = os.path.join(temp_dir, "temp_test_image.png")
    
    # Create a simple image and save it
    img = Image.new("RGB", (100, 100), color="white")
    img.save(image_path)
    
    # Monkeypatch the LLMClient.vision_chat_completion to simulate a vision analysis
    from tac.core.llm import LLMClient, Message
    def fake_vision_chat_completion(self, messages, image_path, temperature=None):
        return "Detailed visual description: A white background with a simple shape."
    
    monkeypatch.setattr(LLMClient, "vision_chat_completion", fake_vision_chat_completion)
    # Also patch the _clean_code_fences method to return the same string
    monkeypatch.setattr(LLMClient, "_clean_code_fences", lambda self, x: x)
    
    description = compute_visual_description(image_path)
    assert "Detailed visual description" in description
    # Cleanup
    os.remove(image_path)