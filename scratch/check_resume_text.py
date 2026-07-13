import os
import sys
import fitz
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Resume_Ramanjeet.pdf')

doc = fitz.open(pdf_path)
print(f"Number of pages: {len(doc)}")
for i, page in enumerate(doc):
    print(f"\n--- PAGE {i+1} ---")
    print(page.get_text()[:1000])
