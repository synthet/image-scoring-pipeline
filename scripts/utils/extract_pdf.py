import pypdf
import sys

pdf_path = r"d:\Downloads\Modern Image Aesthetic Quality Assessment Models (Local Deployment Ready).pdf"
output_path = "pdf_content.txt"

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
