from PIL import Image

def stitch_images(image_path1: str, image_path2: str, image_path3: str, border: int = 10, border_color: str = "black") -> Image.Image:
    """
    Stitches three images side by side with borders in between. 
    Each image is rescaled (padded) vertically to a uniform height (the maximum height of the input images)
    while preserving their original widths and aspect ratios.

    Args:
        image_path1: Path to the first image file.
        image_path2: Path to the second image file.
        image_path3: Path to the third image file.
        border: Width of the border between images.
        border_color: Color of the border.

    Returns:
        A new PIL Image object with the three images arranged side by side separated by borders.
    """
    # Open the images and convert to RGB
    img1 = Image.open(image_path1).convert("RGB")
    img2 = Image.open(image_path2).convert("RGB")
    img3 = Image.open(image_path3).convert("RGB")
    
    # Determine the target height (maximum of the image heights)
    target_height = max(img1.height, img2.height, img3.height)
    
    def pad_to_height(img: Image.Image, target_height: int, border_color: str) -> Image.Image:
        """
        Pads the image vertically to meet the target height.
        Center the original image vertically on a new canvas with the given border_color background.
        """
        if img.height == target_height:
            return img
        new_img = Image.new("RGB", (img.width, target_height), color=border_color)
        top_offset = (target_height - img.height) // 2
        new_img.paste(img, (0, top_offset))
        return new_img

    # Pad images to have uniform height
    img1_padded = pad_to_height(img1, target_height, border_color)
    img2_padded = pad_to_height(img2, target_height, border_color)
    img3_padded = pad_to_height(img3, target_height, border_color)
    
    # Compute dimensions for the new image (sum of widths plus borders)
    total_width = img1_padded.width + img2_padded.width + img3_padded.width + 2 * border
    total_height = target_height
    
    # Create a new image with border_color background
    new_img = Image.new("RGB", (total_width, total_height), color=border_color)
    
    # Paste the images side by side
    x_offset = 0
    new_img.paste(img1_padded, (x_offset, 0))
    x_offset += img1_padded.width + border
    new_img.paste(img2_padded, (x_offset, 0))
    x_offset += img2_padded.width + border
    new_img.paste(img3_padded, (x_offset, 0))
    
    return new_img