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
            
            # Calculate expected widths after rescaling:
            # For img1: new width = 100 * (80/50) = 160, for img2: remains 50, for img3: new width = 80 * (80/60) ≈ 107.
            expected_img1_width = int(round(100 * (80/50)))
            expected_img2_width = int(round(50 * (80/80)))
            expected_img3_width = int(round(80 * (80/60)))
            expected_width = expected_img1_width + expected_img2_width + expected_img3_width + 2 * border
            expected_height = 80  # max height remains 80
            assert stitched.width == expected_width, f"Expected width {expected_width}, got {stitched.width}"
            assert stitched.height == expected_height, f"Expected height {expected_height}, got {stitched.height}"
            
            # Check that left portion contains red (inside img1 region)
            left_pixel = stitched.getpixel((50, 40))
            assert left_pixel == (255, 0, 0), f"Expected red in left image region, got {left_pixel}"
            
            # Check that first border area is black
            border1_x = expected_img1_width
            border1_pixel = stitched.getpixel((border1_x + border//2, 40))
            assert border1_pixel == (0, 0, 0), f"Expected black in first border region, got {border1_pixel}"
            
            # Check that middle portion contains green (inside img2 region)
            green_x = expected_img1_width + border + expected_img2_width//2
            green_pixel = stitched.getpixel((green_x, 40))
            assert green_pixel == (0, 128, 0) or green_pixel == (0, 255, 0), f"Expected green in middle image region, got {green_pixel}"
            
            # Check that second border area is black, located after img2
            border2_x = expected_img1_width + border + expected_img2_width
            border2_pixel = stitched.getpixel((border2_x + border//2, 40))
            assert border2_pixel == (0, 0, 0), f"Expected black in second border region, got {border2_pixel}"
            
            # Check that right portion contains blue (inside img3 region)
            blue_x = expected_img1_width + border + expected_img2_width + 2*border + 20  # 20 pixels inside img3 region
            blue_pixel = stitched.getpixel((blue_x, 40))
            assert blue_pixel == (0, 0, 255), f"Expected blue in right image region, got {blue_pixel}"
            
        finally:
            os.unlink(tmp1.name)
            os.unlink(tmp2.name)
            os.unlink(tmp3.name)

if __name__ == "__main__":
    test_stitch_images()
    print("All tests passed.")