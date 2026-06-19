#!/usr/bin/env python3
"""
Auto-process CHANGE screenshots to standard dimensions with padding.
Reads from .assets-source/ and outputs to .assets/ with green border.
Usage: python3 process-screenshots.py [input_image] [output_image]
"""

import sys
from PIL import Image, ImageOps

# Configuration
TARGET_WIDTH = 1200  # Standard width for documentation
TARGET_HEIGHT = 800  # Standard height for documentation
BACKGROUND_COLOR = (166, 170, 145)  # Sage green background (#A6AA91)
MIN_BORDER_WIDTH = 40  # Minimum border thickness (pixels) on all sides

def remove_border(img, border_color, tolerance=10):
    """
    Remove uniform border from an image by detecting the background color.
    """
    # Convert to RGB if needed
    if img.mode != 'RGB':
        img = img.convert('RGB')

    width, height = img.size
    pixels = img.load()

    # Find the bounds of non-border content
    left = 0
    right = width - 1
    top = 0
    bottom = height - 1

    # Scan from left
    for x in range(width):
        if not all(abs(pixels[x, y][i] - border_color[i]) <= tolerance
                   for y in range(height) for i in range(3)):
            left = x
            break

    # Scan from right
    for x in range(width - 1, -1, -1):
        if not all(abs(pixels[x, y][i] - border_color[i]) <= tolerance
                   for y in range(height) for i in range(3)):
            right = x
            break

    # Scan from top
    for y in range(height):
        if not all(abs(pixels[x, y][i] - border_color[i]) <= tolerance
                   for x in range(width) for i in range(3)):
            top = y
            break

    # Scan from bottom
    for y in range(height - 1, -1, -1):
        if not all(abs(pixels[x, y][i] - border_color[i]) <= tolerance
                   for x in range(width) for i in range(3)):
            bottom = y
            break

    # Crop to content
    if left < right and top < bottom:
        return img.crop((left, top, right + 1, bottom + 1))
    return img

def has_border(img, border_color, tolerance=15):
    """
    Check if image has a border of the specified color.
    """
    if img.mode != 'RGB':
        img = img.convert('RGB')

    width, height = img.size
    pixels = img.load()

    # Check edges for border color
    # Check top edge
    border_pixels = 0
    total_pixels = 0

    for x in range(min(width, 50)):
        for y in range(min(height, 50)):
            total_pixels += 1
            if all(abs(pixels[x, y][i] - border_color[i]) <= tolerance for i in range(3)):
                border_pixels += 1

    # If more than 80% of edge pixels match border color, it has a border
    return (border_pixels / total_pixels) > 0.8 if total_pixels > 0 else False

def process_image(input_path, output_path):
    """
    Process an image to fit target dimensions with padding.
    Maintains aspect ratio and centers the image.
    """
    try:
        # Open the image
        img = Image.open(input_path)

        # Convert to RGB if needed (handles RGBA, grayscale, etc.)
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Calculate max dimensions allowing for minimum border on all sides
        max_width = TARGET_WIDTH - (2 * MIN_BORDER_WIDTH)
        max_height = TARGET_HEIGHT - (2 * MIN_BORDER_WIDTH)

        # Calculate scaling to fit within max dimensions while maintaining aspect ratio
        img_ratio = img.width / img.height
        max_ratio = max_width / max_height

        if img_ratio > max_ratio:
            # Image is wider - fit to max width
            new_width = max_width
            new_height = int(max_width / img_ratio)
        else:
            # Image is taller - fit to max height
            new_height = max_height
            new_width = int(max_height * img_ratio)

        # Resize image maintaining aspect ratio
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Create background with target dimensions
        background = Image.new('RGB', (TARGET_WIDTH, TARGET_HEIGHT), BACKGROUND_COLOR)

        # Calculate position to center the image
        x_offset = (TARGET_WIDTH - new_width) // 2
        y_offset = (TARGET_HEIGHT - new_height) // 2

        # Paste resized image onto background
        background.paste(img_resized, (x_offset, y_offset))

        # Save the result
        background.save(output_path, 'PNG', optimize=True)
        print(f"✓ Processed: {input_path} -> {output_path}")
        print(f"  Original: {img.width}x{img.height} -> Padded: {TARGET_WIDTH}x{TARGET_HEIGHT}")

    except Exception as e:
        print(f"✗ Error processing {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 process-screenshots.py [input_image] [output_image]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    process_image(input_path, output_path)
