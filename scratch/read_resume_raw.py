import os
import sys
import pdfplumber

pdf_path = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes', 'Resume_Ramanjeet.pdf')
out_path = os.path.join(os.path.dirname(__file__), 'raw_resume_text.txt')
print("Reading file:", pdf_path)

with pdfplumber.open(pdf_path) as pdf:
    with open(out_path, 'w', encoding='utf-8') as out:
        for i, page in enumerate(pdf.pages):
            out.write(f"--- PAGE {i+1} ---\n")
            text = page.extract_text()
            if text:
                out.write(text)
            out.write("\n\n")
            
print("Written to:", out_path)
