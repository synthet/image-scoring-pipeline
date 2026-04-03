from PIL import Image
import argparse
import os
import sys


def create_icon(source_paths, output_path):
    """
    Creates a multi-layer .ico file from source images.
    """

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]

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

    images.sort(key=lambda x: x.width, reverse=True)
    base_img = images[0]

    print(f"Using base image size: {base_img.size} for generation.")

    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        base_img.save(output_path, format="ICO", sizes=sizes)
        print(f"Successfully created icon at: {output_path}")

    except Exception as e:
        print(f"Error saving icon: {e}")


def main():
    p = argparse.ArgumentParser(description="Build favicon.ico from one or more PNG sources.")
    p.add_argument(
        "sources",
        nargs="+",
        help="Input image file paths (e.g. PNG).",
    )
    p.add_argument(
        "-o",
        "--output",
        default=os.path.join("static", "favicon.ico"),
        help="Output .ico path (default: static/favicon.ico under cwd).",
    )
    args = p.parse_args()
    missing = [s for s in args.sources if not os.path.isfile(s)]
    if missing:
        print("Missing files:", missing, file=sys.stderr)
        sys.exit(1)
    create_icon(args.sources, os.path.abspath(args.output))


if __name__ == "__main__":
    main()
