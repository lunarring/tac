import unittest
import os
import re

class CubeCenteringTest(unittest.TestCase):
    def test_cube_centering(self):
        # Locate the index.html file relative to this test file
        file_path = os.path.join(os.path.dirname(__file__), "..", "src", "tac", "web", "index.html")
        self.assertTrue(os.path.exists(file_path), f"File does not exist: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Use regex to locate the assignment for cube.position.x in the main Three.js scene
        match = re.search(r'cube\.position\.x\s*=\s*([0-9.]+);', content)
        self.assertIsNotNone(match, "cube.position.x assignment not found in index.html")
        value = float(match.group(1))
        self.assertAlmostEqual(value, 0.0, places=3, msg="Cube is not horizontally centered (expected x position 0)")
        
if __name__ == '__main__':
    unittest.main()
    