from PIL import Image

def stitch_images(image_path1: str, image_path2: str, border: int = 10, border_color: str = "black") -> Image.Image:
    """
    Stitches two images side by side with a border in between.

    Args:
        image_path1: Path to the first image file.
        image_path2: Path to the second image file.
        border: Width of the border between images.
        border_color: Color of the border.

    Returns:
        A new PIL Image object with the first image on the left, second on the right separated by the border.
    """
    # Open the images
    img1 = Image.open(image_path1).convert("RGB")
    img2 = Image.open(image_path2).convert("RGB")
    
    # Compute dimensions for the new image
    total_width = img1.width + img2.width + border
    total_height = max(img1.height, img2.height)
    
    # Create a new image with border_color background
    new_img = Image.new("RGB", (total_width, total_height), color=border_color)
    
    # Paste the two images
    new_img.paste(img1, (0, 0))
    new_img.paste(img2, (img1.width + border, 0))
    
    return new_img