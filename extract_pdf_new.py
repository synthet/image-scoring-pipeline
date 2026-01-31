import pypdf
import sys
import os

pdf_path = r"d:\Downloads\Local Image Aesthetic Quality Assessment Models (2024–2025).pdf"
output_path = "pdf_content_2024_2025.txt"

if not os.path.exists(pdf_path):
    print(f"Error: PDF not found at {pdf_path}")
    sys.exit(1)

try:
    reader = pypdf.PdfReader(pdf_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for page in reader.pages:
            text = page.extract_text()
            f.write(text)
            f.write("\n\n")
    print(f"Successfully extracted text to {output_path}")
except Exception as e:
    print(f"Error extracting PDF: {e}")
