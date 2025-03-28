from PIL import Image

def stitch_images(image_path1: str, image_path2: str, image_path3: str, border: int = 10, border_color: str = "black") -> Image.Image:
    """
    Stitches three images side by side with borders in between. 
    Each image is proportionally rescaled to a uniform target height (the maximum of the input images' heights)
    while preserving their aspect ratios.
    
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
    
    def rescale_to_height(img: Image.Image, target_height: int) -> Image.Image:
        """
        Rescales the image proportionally so that its height becomes target_height.
        """
        if img.height == target_height:
            return img
        scale_factor = target_height / img.height
        new_width = int(round(img.width * scale_factor))
        try:
            resample_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resample_filter = Image.LANCZOS
        return img.resize((new_width, target_height), resample_filter)
    
    # Rescale images to have uniform height
    img1_resized = rescale_to_height(img1, target_height)
    img2_resized = rescale_to_height(img2, target_height)
    img3_resized = rescale_to_height(img3, target_height)
    
    # Compute dimensions for the new image (sum of widths plus borders)
    total_width = img1_resized.width + img2_resized.width + img3_resized.width + 2 * border
    total_height = target_height
    
    # Create a new image with border_color background
    new_img = Image.new("RGB", (total_width, total_height), color=border_color)
    
    # Paste the images side by side
    x_offset = 0
    new_img.paste(img1_resized, (x_offset, 0))
    x_offset += img1_resized.width + border
    new_img.paste(img2_resized, (x_offset, 0))
    x_offset += img2_resized.width + border
    new_img.paste(img3_resized, (x_offset, 0))
    
    return new_img