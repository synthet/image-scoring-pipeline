#!/usr/bin/env python3
"""Extract text from PDF and write to Markdown file."""
import os
import re
import sys
from pathlib import Path


def clean_text(text: str) -> str:
    """Remove PDF extraction artifacts (footnote refs, page numbers)."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that are just numbers, number sequences, or bullet-only
        if not stripped:
            cleaned.append("")
            continue
        if re.match(r"^[\d\s•\-]+$", stripped) and len(stripped) < 50:
            continue
        if re.match(r"^\d+$", stripped) and len(stripped) <= 3:
            continue
        cleaned.append(line)
    # Collapse multiple blank lines
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned))
    return result.strip()


def format_table(text: str) -> str:
    """Convert table-like text to markdown table."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 2:
        return text
    # Check if first line looks like headers (Model, Year, Framework, etc.)
    first = lines[0].lower()
    if "model" in first and ("year" in first or "framework" in first or "srcc" in first):
        rows = []
        for line in lines:
            # Split on 2+ spaces or tabs
            cells = re.split(r"\s{2,}|\t", line)
            if len(cells) >= 2:
                rows.append("| " + " | ".join(c.strip() for c in cells) + " |")
        if rows:
            # Add separator after header
            num_cols = rows[0].count("|") - 1
            sep = "|" + "|".join([" --- "] * num_cols) + "|"
            return "\n".join([rows[0], sep] + rows[1:])
    return text


def pdf_to_markdown(pdf_path: str, md_path: str) -> None:
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    title = Path(pdf_path).stem.replace("_", " ")
    lines = [f"# {title}\n", f"*Converted from PDF: {Path(pdf_path).name}*\n"]

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            cleaned = clean_text(text)
            if cleaned:
                lines.append(f"\n## Page {i + 1}\n\n")
                lines.append(cleaned)
                lines.append("\n")

    content = "".join(lines)
    Path(md_path).write_text(content, encoding="utf-8")
    print(f"Wrote {md_path} ({len(reader.pages)} pages)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_to_markdown.py <pdf_path> [md_path]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    md_path = sys.argv[2] if len(sys.argv) > 2 else pdf_path.replace(".pdf", ".md")
    pdf_to_markdown(pdf_path, md_path)
