import os
import django
import re
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from services.resume_intelligence import ResumeIntelligenceService

pdf_path = "scratch/harneet_resume.pdf"
with open(pdf_path, 'rb') as f:
    file_bytes = f.read()

ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, "harneet_resume.pdf")
text = ocr_result["text"]
lines = [l.strip() for l in text.split('\n') if l.strip()]

date_range_regex = re.compile(
    r'\b(\d{1,2}[-/]\d{2,4}|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\s*[-–to\s]+\s*(\d{1,2}[-/]\d{2,4}|present|current|today|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\b',
    re.IGNORECASE
)

designation_keywords = [
    'manager', 'developer', 'executive', 'engineer', 'lead', 'associate', 'specialist', 'director', 
    'analyst', 'consultant', 'officer', 'administrator', 'coordinator', 'technician', 'representative', 
    'intern', 'programmer', 'architect', 'head', 'founder', 'co-founder', 'ceo', 'cto', 'supervisor',
    'leader', 'operator', 'agent', 'specialist', 'strategist', 'consultant', 'advisor', 'expert', 'auditor'
]

current_section = None
for line_str in lines:
    heading_type = ResumeIntelligenceService.detect_heading_type(line_str)
    old_section = current_section
    if heading_type:
        if heading_type == "SUMMARY" and current_section in ["WORK", "EDU", "PROJECT", "SKILLS", "CERT"]:
            pass
        else:
            current_section = heading_type
    else:
        date_match = date_range_regex.search(line_str)
        if date_match:
            non_date_text = line_str.replace(date_match.group(0), "").strip()
            non_date_text = re.sub(r'^[|/\-\s\.,:]+|[|/\-\s\.,:]+$', '', non_date_text).strip()
            if len(non_date_text) > 3 and any(char.isalpha() for char in non_date_text):
                words_in_line = re.sub(r'[^a-zA-Z\s]', ' ', line_str).lower().split()
                if any(w in designation_keywords for w in words_in_line):
                    current_section = "WORK"

    if current_section != old_section:
        print(f"Transition: {old_section} -> {current_section} on line: '{line_str}'")
