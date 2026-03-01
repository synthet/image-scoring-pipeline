from PIL import Image
import os
import shutil

def create_icon(source_paths, output_path):
    """
    Creates a multi-layer .ico file from source images.
    """
    
    # Sizes for the icon
    # Standard sizes: 256, 128, 64, 48, 32, 16
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    
    # Load source images
    images = []
    for path in source_paths:
        try:
            img = Image.open(path)
            images.append(img)
            print(f"Loaded image: {path} ({img.size})")
        except Exception as e:
            print(f"Failed to load {path}: {e}")

    if not images:
        print("No source images loaded.")
        return

    # Use the largest image as the base for high-res
    # Sort by width descending
    images.sort(key=lambda x: x.width, reverse=True)
    base_img = images[0]

    # Prepare input for save
    # We can just pass the base image and save with sizes=... 
    # But for better quality, if we have multiple inputs, we could try to pick the best fit.
    # For now, resampling the largest one is usually fine for downscaling.

    print(f"Using base image size: {base_img.size} for generation.")

    try:
        # Create directory if not exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Save as ICO
        # append_images is not needed if we just want one image resizing to multiple sizes? 
        # Actually Pillow's save(format='ICO', sizes=...) does the resizing of the image object calling save().
        
        base_img.save(output_path, format='ICO', sizes=sizes)
        print(f"Successfully created icon at: {output_path}")
        
    except Exception as e:
        print(f"Error saving icon: {e}")

if __name__ == "__main__":
    # Source images provided by user
    source_images = [
        r"C:\Users\owner\.gemini\antigravity\brain\68e4573e-d26a-4844-97e9-a44ff8c0c225\media__1771199416231.png",
        r"C:\Users\owner\.gemini\antigravity\brain\68e4573e-d26a-4844-97e9-a44ff8c0c225\media__1771199416234.png"
    ]
    
    # Output path
    output_icon = r"d:\Projects\image-scoring\static\favicon.ico"
    
    # Install pillow if needed (assuming it's in the env, but just in case instructions needed)
    # pip install Pillow
    
    create_icon(source_images, output_icon)
