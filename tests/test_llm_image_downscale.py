import unittest
from PIL import Image
from src.tac.core.llm import LLMClient

class TestDownscaleImage(unittest.TestCase):
    def setUp(self):
        self.client = LLMClient()
    
    def test_downscale_larger_image(self):
        # Image size: 1000x500, target: 800x800 -> expected size: 800x400
        img = Image.new("RGB", (1000, 500), color="red")
        result = self.client.downscale_image(img, 800, 800)
        self.assertEqual(result.size, (800, 400))
    
    def test_downscale_taller_image(self):
        # Image size: 300x600, target: 400x400 -> expected size: 200x400
        img = Image.new("RGB", (300, 600), color="green")
        result = self.client.downscale_image(img, 400, 400)
        self.assertEqual(result.size, (200, 400))
    
    def test_no_downscale_smaller_image(self):
        # Image size: 200x200 is smaller than target: 400x400, so it should remain unchanged.
        img = Image.new("RGB", (200, 200), color="blue")
        result = self.client.downscale_image(img, 400, 400)
        self.assertEqual(result.size, (200, 200))
    
    def test_invalid_target_dimensions(self):
        img = Image.new("RGB", (500, 500), color="yellow")
        with self.assertRaises(ValueError):
            self.client.downscale_image(img, 0, 500)
        with self.assertRaises(ValueError):
            self.client.downscale_image(img, 500, -1)

if __name__ == '__main__':
    unittest.main()