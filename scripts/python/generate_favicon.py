"""
Generate a high-quality favicon.ico from the SVG design.
Creates multiple sizes (16x16, 32x32, 48x48, 64x64) for better display quality.
"""
from PIL import Image, ImageDraw
import os

def create_favicon_icon(size):
    """Create a single icon at the specified size."""
    # Create image with transparent background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Yellow color matching SVG (#FFD700)
    yellow = (255, 215, 0, 255)
    
    # Calculate dimensions based on size
    center = size // 2
    outer_radius = int(size * 0.42)  # Slightly smaller than half to avoid edge clipping
    inner_radius = int(size * 0.125)  # Small inner circle
    
    # Draw outer circle (ring)
    outer_bbox = [
        center - outer_radius,
        center - outer_radius,
        center + outer_radius,
        center + outer_radius
    ]
    draw.ellipse(outer_bbox, outline=yellow, width=max(1, size // 16))
    
    # Draw inner filled circle
    inner_bbox = [
        center - inner_radius,
        center - inner_radius,
        center + inner_radius,
        center + inner_radius
    ]
    draw.ellipse(inner_bbox, fill=yellow)
    
    # Draw crosshairs (only for larger sizes)
    if size >= 32:
        line_width = max(1, size // 24)
        # Vertical line
        draw.line([center, center - outer_radius, center, center + outer_radius], 
                 fill=yellow, width=line_width)
        # Horizontal line
        draw.line([center - outer_radius, center, center + outer_radius, center], 
                 fill=yellow, width=line_width)
    
    return img

def generate_favicon():
    """Generate favicon.ico with multiple sizes."""
    # Create a high-resolution source icon (256x256) for best quality
    # PIL will automatically generate all needed sizes from this using high-quality resampling
    source_size = 256
    source_icon = create_favicon_icon(source_size)
    
    # Define the sizes to include in the ICO file
    # These are the standard favicon sizes browsers use
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    
    # Save as ICO file with multiple sizes
    # PIL will automatically resize the source image to each specified size
    output_path = os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'favicon.ico')
    
    source_icon.save(
        output_path,
        format='ICO',
        sizes=ico_sizes
    )
    
    # Verify the file was created
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"Generated favicon.ico with multiple sizes: {[s[0] for s in ico_sizes]}")
        print(f"Source resolution: {source_size}x{source_size}")
        print(f"File size: {file_size} bytes")
        print(f"Saved to: {output_path}")
    else:
        print(f"Error: Failed to create favicon at {output_path}")

if __name__ == '__main__':
    generate_favicon()
