import os
import sys
import fitz

pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Naukri_ROHANKUMAR4y_6m_1_6j3X3oK.pdf')

doc = fitz.open(pdf_path)
print(f"Number of pages: {len(doc)}")
for i, page in enumerate(doc):
    print(f"\n--- PAGE {i+1} ---")
    txt = page.get_text()[:1000]
    print(txt.encode('ascii', errors='ignore').decode('ascii'))
