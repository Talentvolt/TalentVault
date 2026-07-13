import os
import sys
import fitz

pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Ankit_Web__development.pdf')

doc = fitz.open(pdf_path)
print(f"Number of pages: {len(doc)}")
for i, page in enumerate(doc):
    print(f"\n--- PAGE {i+1} ---")
    print(page.get_text()[:1000])
