import os
import tempfile
from PIL import Image
from tac.utils.image_stitcher import stitch_images

def test_stitch_images():
    # Create temporary image files for testing
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp1, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp2, \
         tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp3:
        try:
            # Create a red image of size 100x50
            img1 = Image.new("RGB", (100, 50), color="red")
            img1.save(tmp1.name, format="PNG")
            
            # Create a green image of size 50x80
            img2 = Image.new("RGB", (50, 80), color="green")
            img2.save(tmp2.name, format="PNG")
            
            # Create a blue image of size 80x60
            img3 = Image.new("RGB", (80, 60), color="blue")
            img3.save(tmp3.name, format="PNG")
            
            # Define border width
            border = 10
            
            # Stitch images
            stitched = stitch_images(tmp1.name, tmp2.name, tmp3.name, border=border, border_color="black")
            
            # Expected dimensions: width = 100 + 50 + 80 + 2*border = 250, height = max(50, 80, 60) = 80
            expected_width = 250
            expected_height = 80
            assert stitched.width == expected_width, f"Expected width {expected_width}, got {stitched.width}"
            assert stitched.height == expected_height, f"Expected height {expected_height}, got {stitched.height}"
            
            # Check that left portion contains red (inside img1 region)
            left_pixel = stitched.getpixel((50, 25))
            assert left_pixel == (255, 0, 0), f"Expected red in left image region, got {left_pixel}"
            
            # Check that first border area is black
            border1_pixel = stitched.getpixel((100 + border//2, 25))
            assert border1_pixel == (0, 0, 0), f"Expected black in first border region, got {border1_pixel}"
            
            # Check that middle portion contains green (inside img2 region)
            # The second image is pasted at x = img1.width + border
            green_pixel = stitched.getpixel((100 + border + 25, 40))
            assert green_pixel == (0, 128, 0) or green_pixel == (0, 255, 0), f"Expected green in middle image region, got {green_pixel}"
            
            # Check that second border area is black, located after img2
            border2_pixel = stitched.getpixel((100 + border + 50 + border//2, 40))
            assert border2_pixel == (0, 0, 0), f"Expected black in second border region, got {border2_pixel}"
            
            # Check that right portion contains blue (inside img3 region)
            # The third image is pasted at x = img1.width + border + img2.width + border = 170
            blue_pixel = stitched.getpixel((170 + 20, 30))
            assert blue_pixel == (0, 0, 255), f"Expected blue in right image region, got {blue_pixel}"
            
        finally:
            os.unlink(tmp1.name)
            os.unlink(tmp2.name)
            os.unlink(tmp3.name)

if __name__ == "__main__":
    test_stitch_images()
    print("All tests passed.")