import os
import sys
import fitz
import docx

resumes_dir = os.path.join(os.path.dirname(__file__), '..', 'media', 'resumes')
keywords = ['laravel', 'php', 'django', 'software', 'engineer', 'developer', 'python']

for fname in os.listdir(resumes_dir):
    fpath = os.path.join(resumes_dir, fname)
    if not os.path.isfile(fpath):
        continue
        
    text = ""
    ext = fname.split('.')[-1].lower()
    if ext == 'pdf':
        try:
            doc = fitz.open(fpath)
            text = " ".join([page.get_text() for page in doc])
        except Exception:
            pass
    elif ext == 'docx':
        try:
            doc = docx.Document(fpath)
            text = " ".join([p.text for p in doc.paragraphs])
        except Exception:
            pass
            
    text_lower = text.lower()
    found = [w for w in keywords if w in text_lower]
    if found:
        print(f"File: {fname} | Size: {os.path.getsize(fpath)} | Matched: {found}")
