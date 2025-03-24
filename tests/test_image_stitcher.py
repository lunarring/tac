import os
import tempfile
from PIL import Image
from tac.utils.image_stitcher import stitch_images

def test_stitch_images():
    # Create temporary image files for testing
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp1, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp2:
        try:
            # Create a red image of size 100x50
            img1 = Image.new("RGB", (100, 50), color="red")
            img1.save(tmp1.name, format="PNG")
            
            # Create a green image of size 50x80
            img2 = Image.new("RGB", (50, 80), color="green")
            img2.save(tmp2.name, format="PNG")
            
            # Define border width
            border = 10
            
            # Stitch images
            stitched = stitch_images(tmp1.name, tmp2.name, border=border, border_color="black")
            
            # Expected dimensions: width = 100 + 50 + 10 = 160, height = max(50, 80) = 80
            expected_width = 160
            expected_height = 80
            assert stitched.width == expected_width, f"Expected width {expected_width}, got {stitched.width}"
            assert stitched.height == expected_height, f"Expected height {expected_height}, got {stitched.height}"
            
            # Check that left portion contains red (inside img1 region)
            left_pixel = stitched.getpixel((50, 25))
            assert left_pixel == (255, 0, 0), f"Expected red in left image region, got {left_pixel}"
            
            # Check that border area is black
            border_pixel = stitched.getpixel((100 + border//2, 25))
            assert border_pixel == (0, 0, 0), f"Expected black in border region, got {border_pixel}"
            
            # Check that right portion contains green (inside img2 region)
            # The right image is pasted at x = 100 + border, so test a point inside it.
            right_pixel = stitched.getpixel((100 + border + 25, 40))
            assert right_pixel == (0, 128, 0) or right_pixel == (0, 255, 0), f"Expected green in right image region, got {right_pixel}"
            
        finally:
            os.unlink(tmp1.name)
            os.unlink(tmp2.name)

if __name__ == "__main__":
    test_stitch_images()
    print("All tests passed.")