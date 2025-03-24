from PIL import Image

def stitch_images(image_path1: str, image_path2: str, image_path3: str, border: int = 10, border_color: str = "black") -> Image.Image:
    """
    Stitches three images side by side with borders in between.

    Args:
        image_path1: Path to the first image file.
        image_path2: Path to the second image file.
        image_path3: Path to the third image file.
        border: Width of the border between images.
        border_color: Color of the border.

    Returns:
        A new PIL Image object with the three images arranged side by side separated by borders.
    """
    # Open the images
    img1 = Image.open(image_path1).convert("RGB")
    img2 = Image.open(image_path2).convert("RGB")
    img3 = Image.open(image_path3).convert("RGB")
    
    # Compute dimensions for the new image
    total_width = img1.width + img2.width + img3.width + 2 * border
    total_height = max(img1.height, img2.height, img3.height)
    
    # Create a new image with border_color background
    new_img = Image.new("RGB", (total_width, total_height), color=border_color)
    
    # Paste the images
    new_img.paste(img1, (0, 0))
    new_img.paste(img2, (img1.width + border, 0))
    new_img.paste(img3, (img1.width + border + img2.width + border, 0))
    
    return new_img