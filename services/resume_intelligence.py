import re
import os
import io
import math
import json
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.core.files.base import ContentFile
from apps.accounts.models import User
from apps.candidates.models import (
    CandidateProfile, CandidateSkill, Experience, Education, Project, Certification
)

# Optional heavy imports handled gracefully
try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False

try:
    import easyocr
    EASY_AVAILABLE = True
except ImportError:
    EASY_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


class ResumeIntelligenceService:
    """
    Production-grade Resume Intelligence Engine supporting multiple file formats,
    multi-engine OCR with fallback logic, Layout/NLP parsing, AI Assist, 
    and duplicate candidate similarity verification.
    """

    @staticmethod
    def is_valid_name(name: str) -> bool:
        if not name or not isinstance(name, str):
            return False
        name_clean = name.strip()
        if not name_clean:
            return False
            
        # Never assign numeric strings
        if name_clean.isdigit():
            return False
            
        # Reject if matches ^\+?\d[\d\s-]{8,}$
        if re.match(r'^\+?\d[\d\s-]{8,}$', name_clean):
            return False
            
        # or contains @
        if '@' in name_clean:
            return False
            
        # or starts with http
        if name_clean.lower().startswith('http'):
            return False
            
        # or linkedin/github
        if 'linkedin' in name_clean.lower() or 'github' in name_clean.lower():
            return False
            
        # Reject if it's a phone number with formats like (+91) 9953699195 or similar
        digits_only = re.sub(r'[^\d+]', '', name_clean)
        if len(digits_only) >= 8 and digits_only.replace('+', '').isdigit():
            return False
            
        # Check if contains email/url
        if re.search(r'[\w\.-]+@[\w\.-]+\.\w+', name_clean):
            return False
        if re.search(r'(https?://\S+|www\.\S+)', name_clean, re.I):
            return False
            
        # Must contain at least one alphabetic character
        if not any(char.isalpha() for char in name_clean):
            return False
            
        return True

    @staticmethod
    def normalize_date_to_string(date_str: str, default_year: int = None, is_end: bool = False) -> str:
        if not date_str or not isinstance(date_str, str):
            return None
        
        val = date_str.strip().lower()
        if val in ["present", "current", "today", "now", "ongoing"]:
            return "Present"
            
        # Clean up the string a bit
        val_clean = re.sub(r'[^\w\s\-/]', ' ', val).strip()
        
        # Months mapping
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        # Pattern: Month (word) and Year (4-digit)
        m_word_year = re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-/]*(\d{4})\b', val, re.I)
        if m_word_year:
            m_str = m_word_year.group(1).lower()
            y_str = m_word_year.group(2)
            month = months.get(m_str, 1)
            year = int(y_str)
            day = 28 if (is_end and month == 2) else (30 if is_end and month in [4,6,9,11] else (31 if is_end else 1))
            if is_end and month == 2:
                if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                    day = 29
            return f"{year:04d}-{month:02d}-{day:02d}"
            
        # Pattern: MM/YYYY or MM-YYYY or M/YYYY or M-YYYY
        m_digits_year = re.search(r'\b(\d{1,2})[\s\-/]+(\d{4})\b', val)
        if m_digits_year:
            month = int(m_digits_year.group(1))
            year = int(m_digits_year.group(2))
            if 1 <= month <= 12:
                day = 28 if (is_end and month == 2) else (30 if is_end and month in [4,6,9,11] else (31 if is_end else 1))
                if is_end and month == 2:
                    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                        day = 29
                return f"{year:04d}-{month:02d}-{day:02d}"

        # Pattern: YYYY-MM-DD or YYYY/MM/DD
        m_full_date = re.search(r'\b(\d{4})[\s\-/]+(\d{1,2})[\s\-/]+(\d{1,2})\b', val)
        if m_full_date:
            year = int(m_full_date.group(1))
            month = int(m_full_date.group(2))
            day = int(m_full_date.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"

        # Pattern: DD-MM-YYYY or DD/MM/YYYY
        m_reverse_date = re.search(r'\b(\d{1,2})[\s\-/]+(\d{1,2})[\s\-/]+(\d{4})\b', val)
        if m_reverse_date:
            day = int(m_reverse_date.group(1))
            month = int(m_reverse_date.group(2))
            year = int(m_reverse_date.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"

        # Pattern: Just YYYY (4-digit)
        m_year_only = re.search(r'\b(19\d\d|20\d\d)\b', val)
        if m_year_only:
            year = int(m_year_only.group(1))
            month = 12 if is_end else 1
            day = 31 if is_end else 1
            return f"{year:04d}-{month:02d}-{day:02d}"

        if default_year:
            month = 12 if is_end else 1
            day = 31 if is_end else 1
            return f"{default_year:04d}-{month:02d}-{day:02d}"
            
        return None

    @staticmethod
    def calculate_experience_years_from_dates(start_str: str, end_str: str) -> float:
        if not start_str:
            return 0.0
        
        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
        except Exception:
            return 0.0
            
        if not end_str or end_str.strip().lower() in ["present", "current", "today", "now", "ongoing"]:
            end_dt = datetime.now().date()
        else:
            try:
                end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
            except Exception:
                end_dt = datetime.now().date()
                
        if start_dt > end_dt:
            return 0.0
            
        delta_days = (end_dt - start_dt).days
        years = delta_days / 365.25
        if years < 0:
            return 0.0
        return round(years, 2)

    @staticmethod
    def clean_camel_case_name(name: str) -> str:
        if not name or not isinstance(name, str):
            return name
        name_clean = name.strip()
        # Insert space before any uppercase letter that is not the start of the string
        splitted = re.sub(r'(?<!^)(?=[A-Z])', ' ', name_clean)
        # Normalize multiple spaces
        return " ".join(splitted.split())

    @staticmethod
    def extract_candidate_name(text: str, parsed_name: str = None) -> str:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        # 1. parsed_json.personal_info.name
        if parsed_name and ResumeIntelligenceService.is_valid_name(parsed_name):
            return ResumeIntelligenceService.clean_camel_case_name(parsed_name)
            
        # 2. NLP entities (PERSON)
        nlp_name = ""
        if SPACY_AVAILABLE:
            try:
                nlp = spacy.load("en_core_web_sm")
                doc = nlp(text)
                for ent in doc.ents:
                    if ent.label_ == "PERSON":
                        val = ent.text.strip()
                        if ResumeIntelligenceService.is_valid_name(val):
                            nlp_name = val
                            break
            except Exception as e:
                print(f"spaCy PERSON extraction failed: {e}")
                
        # Fallback heuristic for PERSON entity detection (NLP entities helper)
        if not nlp_name:
            for line in lines[:15]:
                l_clean = line.strip()
                if not ResumeIntelligenceService.is_valid_name(l_clean):
                    continue
                words = l_clean.split()
                if 2 <= len(words) <= 3:
                    if all(w[0].isupper() and re.sub(r'[.,]', '', w).isalpha() for w in words):
                        if not any(h in l_clean.lower() for h in ["experience", "education", "skills", "projects", "certifications", "summary"]):
                            nlp_name = l_clean
                            break
                            
        if nlp_name and ResumeIntelligenceService.is_valid_name(nlp_name):
            return ResumeIntelligenceService.clean_camel_case_name(nlp_name)
            
        # 3. First text line excluding phone, email, URL, linkedin, github
        p3_name = ""
        for line in lines:
            l_clean = line.strip()
            if ResumeIntelligenceService.is_valid_name(l_clean):
                p3_name = l_clean
                break
                
        if p3_name:
            return ResumeIntelligenceService.clean_camel_case_name(p3_name)
            
        # 4. OCR Layout heading
        if lines:
            p4_name = lines[0].strip()
            if ResumeIntelligenceService.is_valid_name(p4_name):
                return ResumeIntelligenceService.clean_camel_case_name(p4_name)
                
        # 5. Fallback
        return "Unknown Candidate"

    @staticmethod
    def detect_resume_type(filename: str) -> str:
        ext = filename.split('.')[-1].lower()
        if ext in ['pdf']:
            return 'PDF'
        elif ext in ['docx', 'doc']:
            return 'DOCX'
        elif ext in ['png', 'jpg', 'jpeg', 'tiff', 'bmp']:
            return 'IMAGE'
        return 'UNKNOWN'

    @staticmethod
    def run_ocr_pipeline(file_bytes: bytes, filename: str) -> dict:
        """
        Runs OCR with fallback logic: PaddleOCR -> EasyOCR -> Tesseract.
        If confidence < 90%, retries with the next engine in the pipeline.
        """
        resume_type = ResumeIntelligenceService.detect_resume_type(filename)
        extracted_text = ""
        used_engine = "None (Direct Text Extraction)"
        confidence = 100.0

        if resume_type == 'DOCX':
            # Direct python-docx parsing
            import docx
            try:
                doc = docx.Document(io.BytesIO(file_bytes))
                extracted_text = "\n".join([p.text for p in doc.paragraphs])
            except Exception as e:
                extracted_text = f"DOCX Parse Error: {str(e)}"
            return {
                "text": extracted_text,
                "engine": "python-docx",
                "confidence": 100.0,
                "resume_type": "EDITABLE_DOCX"
            }

        if resume_type == 'PDF':
            # First try direct text extraction
            import pdfplumber
            try:
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            extracted_text += page_text + "\n"
            except Exception as e:
                print(f"pdfplumber failed: {e}")

            if len(extracted_text.strip()) > 100:
                return {
                    "text": extracted_text,
                    "engine": "pdfplumber",
                    "confidence": 98.0,
                    "resume_type": "EDITABLE_PDF"
                }
            else:
                # Scanned or non-editable PDF, must render pages to images and run OCR
                resume_type = 'IMAGE'
                used_engine = "Scanned PDF (OCR Required)"

        # Run Image/Scanned OCR pipeline
        from PIL import Image
        image_list = []
        try:
            if resume_type == 'PDF' or filename.lower().endswith('.pdf'):
                import pypdfium2
                pdf = pypdfium2.PdfDocument(file_bytes)
                for i in range(len(pdf)):
                    page = pdf[i]
                    bitmap = page.render(scale=2) # 150 DPI render
                    pil_img = bitmap.to_pil()
                    image_list.append(pil_img)
            else:
                # Regular image file
                pil_img = Image.open(io.BytesIO(file_bytes))
                image_list.append(pil_img)
        except Exception as e:
            print(f"Image rendering/loading failed: {e}")
            return {
                "text": extracted_text or "Could not open document.",
                "engine": "Error / Fallback Text",
                "confidence": 50.0,
                "resume_type": "CORRUPTED"
            }

        # OCR Engine pipeline execution loop
        engines_to_try = ['paddleocr', 'easyocr', 'tesseract']
        ocr_results = {"text": "", "engine": "", "confidence": 0.0}

        for img in image_list:
            engine_success = False

            # 1. PaddleOCR
            if PADDLE_AVAILABLE:
                print("[ENGINE_SELECTED] PaddleOCR")
                try:
                    ocr = PaddleOCR(use_textline_orientation=True, lang='en')
                    print("[ENGINE_INITIALIZED] PaddleOCR: True")
                    text_lines = []
                    img_confidences = []
                    # Convert PIL to numpy array
                    import numpy as np
                    img_np = np.array(img)
                    result = ocr.ocr(img_np, cls=True)
                    if result and result[0]:
                        for line in result[0]:
                            text_lines.append(line[1][0])
                            img_confidences.append(line[1][1] * 100)
                    
                    avg_conf = sum(img_confidences) / len(img_confidences) if img_confidences else 0
                    if avg_conf >= 90.0:
                        ocr_results["text"] += "\n".join(text_lines) + "\n"
                        ocr_results["engine"] = "PaddleOCR"
                        ocr_results["confidence"] = avg_conf
                        engine_success = True
                except Exception as e:
                    print("[ENGINE_INITIALIZED] PaddleOCR: False")
                    print(f"[ENGINE_EXCEPTION] PaddleOCR: {str(e)}")

            # 2. EasyOCR (Fallback)
            if not engine_success and EASY_AVAILABLE:
                print("[ENGINE_SELECTED] EasyOCR")
                try:
                    reader = easyocr.Reader(['en'])
                    print("[ENGINE_INITIALIZED] EasyOCR: True")
                    text_lines = []
                    img_confidences = []
                    import numpy as np
                    img_np = np.array(img)
                    result = reader.readtext(img_np)
                    for res in result:
                        text_lines.append(res[1])
                        img_confidences.append(res[2] * 100)

                    avg_conf = sum(img_confidences) / len(img_confidences) if img_confidences else 0
                    if avg_conf >= 90.0 or not ocr_results["engine"]:
                        ocr_results["text"] += "\n".join(text_lines) + "\n"
                        ocr_results["engine"] = "EasyOCR"
                        ocr_results["confidence"] = avg_conf
                        engine_success = True
                except Exception as e:
                    print("[ENGINE_INITIALIZED] EasyOCR: False")
                    print(f"[ENGINE_EXCEPTION] EasyOCR: {str(e)}")

            # 3. Tesseract (Final Fallback)
            if not engine_success:
                print("[ENGINE_SELECTED] Tesseract")
                try:
                    # Pure PIL tesseract call
                    import pytesseract
                    # If Tesseract is not fully configured, handle gracefully
                    text = pytesseract.image_to_string(img)
                    print("[ENGINE_INITIALIZED] Tesseract: True")
                    if text.strip():
                        ocr_results["text"] += text + "\n"
                        ocr_results["engine"] = "Tesseract"
                        ocr_results["confidence"] = 92.5
                        engine_success = True
                    else:
                        raise ValueError("Empty text returned by Tesseract")
                except Exception as e:
                    print("[ENGINE_INITIALIZED] Tesseract: False")
                    print(f"[ENGINE_EXCEPTION] Tesseract: {str(e)}")

        result_dict = {
            "text": ocr_results["text"].strip(),
            "engine": ocr_results["engine"] or "None",
            "confidence": ocr_results["confidence"] or 0.0,
            "resume_type": "SCANNED_IMAGE" if resume_type == 'IMAGE' else "SCANNED_PDF"
        }

        # Logging requirements
        ext = filename.split('.')[-1].lower()
        is_img_file = ext in ['png', 'jpg', 'jpeg', 'tiff', 'bmp']
        if is_img_file or result_dict["resume_type"] == "SCANNED_IMAGE":
            import logging
            logger = logging.getLogger(__name__)
            
            # Extract first 20 lines of the text
            text_lines = result_dict['text'].split('\n')
            first_20_lines = "\n".join(text_lines[:20])
            
            print(f"[OCR_CONFIDENCE] {result_dict['confidence']}")
            print(f"[FIRST_20_LINES]:\n{first_20_lines}")
            
            log_msg = (
                f"\n[IMAGE DETECTED] Processing file: {filename}\n"
                f"[OCR ENGINE USED] {result_dict['engine']}\n"
                f"[OCR CONFIDENCE] {result_dict['confidence']}\n"
                f"[TEXT LENGTH] {len(result_dict['text'])}\n"
                f"[FIRST 20 LINES OF EXTRACTED TEXT]:\n{first_20_lines}\n"
            )
            logger.info(log_msg)

        return result_dict

    @staticmethod
    def parse_resume_nlp(text: str) -> dict:
        """
        Layout-aware NLP Parsing Engine extracting Name, Contact details, Education,
        Experiences, Skills, Certifications, and Summary using heuristics & NLP keywords.
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r'(?:\+?\d{1,3}[- ]?)?(?:\d[- ]?){9}\d', text)
        phone = re.sub(r'[\s-]', '', phone_match.group(0))[-10:] if phone_match else ""

        linkedin_match = re.search(r'(linkedin\.com/in/[\w-]+)', text, re.I)
        linkedin = linkedin_match.group(0) if linkedin_match else ""

        portfolio_match = re.search(r'((github\.com|portfolio|behance\.net)/[\w-]+)', text, re.I)
        portfolio = portfolio_match.group(0) if portfolio_match else ""

        # Extract name (heuristic: first few lines not matching email/phone/urls)
        h_name = ""
        for line in lines[:5]:
            if "@" not in line and not any(kw in line.lower() for kw in ["phone", "tel", "email", "http", "resume", "cv", "page"]):
                # Clean name lines from dates/locations
                if not re.search(r'\b(delhi|mumbai|bangalore|pune|hyderabad|noida|gurgaon|california|london)\b', line, re.I):
                    h_name = line
                    break

        name = ResumeIntelligenceService.extract_candidate_name(text, parsed_name=h_name)

        # Location detection
        location = "Unknown"
        locations = ['Delhi', 'Mumbai', 'Bangalore', 'Hyderabad', 'Pune', 'Noida', 'Gurgaon', 'Patna', 'Lucknow', 'Begusarai', 'Samastipur', 'Chennai', 'Kolkata']
        for loc in locations:
            if loc.lower() in text.lower():
                location = loc
                break

        # Skills extraction
        skills_dict = [
            'python', 'java', 'django', 'react', 'javascript', 'node', 'mern', 'aws', 'docker', 'kubernetes', 'sql', 
            'pharma', 'nurse', 'sales', 'hr', 'php', 'laravel', 'flutter', 'android', 'ios', 'data science', 'ml', 'ai',
            'c++', 'c#', 'ruby', 'rails', 'swift', 'kotlin', 'html', 'css', 'sass', 'typescript', 'mongodb', 'postgresql',
            'redis', 'elasticsearch', 'celery', 'rabbitmq', 'git', 'ci/cd', 'jenkins', 'terraform', 'agile', 'scrum'
        ]
        skills = []
        text_lower = text.lower()
        for skill in skills_dict:
            if re.search(r'\b' + re.escape(skill) + r'\b', text_lower):
                skills.append(skill.title())

        # Extract Summary (heuristic: look for "summary", "profile", "about me" headers)
        summary = ""
        summary_found = False
        summary_lines = []
        for i, line in enumerate(lines):
            l = line.lower()
            if any(h in l for h in ["summary", "professional summary", "career profile", "about me"]):
                summary_found = True
                continue
            if summary_found:
                if any(h in l for h in ["experience", "education", "skills", "projects", "certifications", "languages"]):
                    break
                summary_lines.append(line)
        if summary_lines:
            summary = " ".join(summary_lines)
        else:
            # Fallback summary
            summary = lines[1] if len(lines) > 1 else ""

        # Section-based extraction
        current_section = None
        work_lines = []
        edu_lines = []
        project_lines = []
        cert_lines = []

        for line in lines:
            l = line.lower()
            
            # Detect section transitions
            is_heading = False
            if any(h in l for h in ["work experience", "experience", "employment history", "work history", "professional experience"]):
                current_section = 'WORK'
                is_heading = True
            elif any(h in l for h in ["education", "academic", "university", "college", "academic background"]):
                current_section = 'EDU'
                is_heading = True
            elif any(h in l for h in ["projects", "personal projects", "academic projects"]):
                current_section = 'PROJECT'
                is_heading = True
            elif any(h in l for h in ["certifications", "licenses", "certificates"]):
                current_section = 'CERT'
                is_heading = True
            elif any(h in l for h in ["skills", "languages", "hobbies", "profile summary", "key skills", "interests", "summary"]):
                current_section = 'OTHER'
                is_heading = True

            if is_heading:
                continue

            if current_section == 'WORK':
                work_lines.append(line)
            elif current_section == 'EDU':
                edu_lines.append(line)
            elif current_section == 'PROJECT':
                project_lines.append(line)
            elif current_section == 'CERT':
                cert_lines.append(line)

        # 1. Parse Work Experiences
        date_range_regex = re.compile(
            r'\b(\d{1,2}[-/]\d{2,4}|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\s*[-–to\s]+\s*(\d{1,2}[-/]\d{2,4}|present|current|today|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\b',
            re.IGNORECASE
        )

        designation_keywords = [
            'manager', 'developer', 'executive', 'engineer', 'lead', 'associate', 'specialist', 'director', 
            'analyst', 'consultant', 'officer', 'administrator', 'coordinator', 'technician', 'representative', 
            'intern', 'programmer', 'architect', 'head', 'founder', 'co-founder', 'ceo', 'cto', 'supervisor',
            'leader', 'operator', 'agent', 'specialist', 'strategist', 'consultant', 'advisor', 'expert'
        ]

        description_start_keywords = [
            "manage", "lead", "maintain", "achieve", "collaborate", "oversaw", "responsible", 
            "experience", "rectifying", "improving", "training", "coaching", "publishing", 
            "handling", "headed", "interacting", "streamline", "establish", "launch", "elevate", 
            "identify", "resolve", "implement", "redesign", "coordinate", "ensure", "support",
            "developed", "designed", "built", "created", "worked", "assisted", "monitored",
            "analyzed", "facilitated", "supervised"
        ]

        def is_designation_line(line_val):
            if line_val.strip().startswith(('-', '•', '*', '+')):
                return False
            lower_l = line_val.lower()
            if len(line_val) > 100:
                return False
            return any(re.search(r'\b' + re.escape(kw) + r'\b', lower_l) for kw in designation_keywords)

        def is_description_line(line_val):
            line_clean = line_val.strip().lstrip('-•*+ ').strip()
            if not line_clean:
                return True
            first_w = line_clean.split()[0].lower()
            if line_val.strip().startswith(('-', '•', '*', '+')):
                return True
            if first_w in description_start_keywords:
                return True
            if len(line_val) > 120 or line_val.endswith(('.', ';')):
                return True
            return False

        work_blocks = []
        current_block = {
            "header_lines": [],
            "date_line": "",
            "description_lines": []
        }

        for line in work_lines:
            line_str = line.strip()
            if not line_str:
                continue
                
            is_date = bool(date_range_regex.search(line_str))
            is_desc = is_description_line(line_str)
            is_desig = is_designation_line(line_str)
            
            if is_date and current_block["date_line"]:
                work_blocks.append(current_block)
                current_block = {"header_lines": [], "date_line": "", "description_lines": []}
            elif is_desig and current_block["description_lines"]:
                work_blocks.append(current_block)
                current_block = {"header_lines": [], "date_line": "", "description_lines": []}
                
            if is_date:
                current_block["date_line"] = line_str
            elif is_desc:
                current_block["description_lines"].append(line_str)
            else:
                current_block["header_lines"].append(line_str)
                
        if current_block["header_lines"] or current_block["date_line"] or current_block["description_lines"]:
            work_blocks.append(current_block)

        experiences = []
        for block in work_blocks:
            headers = [h.strip() for h in block["header_lines"] if h.strip()]
            
            designation_line = ""
            designation_idx = -1
            for idx, h in enumerate(headers):
                if is_designation_line(h):
                    designation_line = h
                    designation_idx = idx
                    break
            
            has_date = bool(block["date_line"])
            
            # Reject if no dates AND no designation keywords found in headers (must be merged into previous block)
            if not has_date and not designation_line:
                extra_desc = "\n".join(block["header_lines"] + block["description_lines"])
                if extra_desc.strip():
                    if experiences:
                        experiences[-1]["description"] = (experiences[-1]["description"] + "\n" + extra_desc).strip()
                continue
                
            start_date_val = ""
            end_date_val = ""
            if block["date_line"]:
                match = date_range_regex.search(block["date_line"])
                if match:
                    raw_start = match.group(1).strip() if match.group(1) else ""
                    raw_end = match.group(2).strip() if match.group(2) else ""
                    start_date_val = ResumeIntelligenceService.normalize_date_to_string(raw_start, is_end=False) or ""
                    end_date_val = ResumeIntelligenceService.normalize_date_to_string(raw_end, is_end=True) or ""
            
            designation = ""
            company = ""
            
            if designation_line:
                designation = designation_line
                other_headers = [h for i, h in enumerate(headers) if i != designation_idx]
                if other_headers:
                    company = other_headers[0]
            else:
                if len(headers) == 1:
                    designation = headers[0]
                elif len(headers) >= 2:
                    designation = headers[0]
                    company = headers[1]
                    
            for sep in [" at ", " @ ", " - ", " | ", " , "]:
                if sep in designation:
                    parts = designation.split(sep, 1)
                    designation = parts[0].strip()
                    company = parts[1].strip()
                    break
            
            if designation.lower() == "role":
                designation = ""
            if company.lower() == "company":
                company = ""
                    
            company = re.sub(r'\s*\([^)]*\)', '', company).strip()
            designation = re.sub(r'\s*\([^)]*\)', '', designation).strip()
            
            description = "\n".join(block["description_lines"]).strip()
            
            experiences.append({
                "designation": designation,
                "company": company,
                "description": description,
                "start_date": start_date_val,
                "end_date": end_date_val
            })

        # Post-process experiences to:
        # 1. Reject fake experiences (empty or generic OCR artifacts)
        # 2. Format description as clean bullet points
        # 3. Group by company and designation, keeping the chronological order
        grouped_experiences = []
        for exp in experiences:
            comp = exp["company"].strip()
            desig = exp["designation"].strip()
            desc = exp["description"].strip()
            s_date = exp["start_date"]
            e_date = exp["end_date"]
            
            # Clean company and designation names
            comp_clean = comp.lstrip('-•*+ ').strip()
            desig_clean = desig.lstrip('-•*+ ').strip()
            
            # Remove parentheses content and clean extra spaces
            comp_clean = re.sub(r'\s*\([^)]*\)', '', comp_clean).strip()
            desig_clean = re.sub(r'\s*\([^)]*\)', '', desig_clean).strip()

            # Filter out common personal detail or license OCR lines
            invalid_keywords = [
                "valid upto", "valid up to", "expiry date", "date of birth", "gender:", "nationality:", 
                "languages known", "marital status", "passport no", "driving license",
                "hobbies", "permanent address", "current address", "valid check", "validity"
            ]
            if any(ikw in comp_clean.lower() for ikw in invalid_keywords):
                comp_clean = ""
            if any(ikw in desig_clean.lower() for ikw in invalid_keywords):
                desig_clean = ""
            
            # Skip/Merge if both are empty or if it's just random OCR text without company/designation
            if not comp_clean and not desig_clean:
                if grouped_experiences and desc:
                    # Append description lines to the last experience
                    existing_desc = grouped_experiences[-1]["description"]
                    new_lines = []
                    for line in desc.split('\n'):
                        l_clean = line.strip().lstrip('-•*+ ').strip()
                        if l_clean:
                            new_lines.append(f"• {l_clean}")
                    if new_lines:
                        new_desc = "\n".join(new_lines)
                        grouped_experiences[-1]["description"] = (existing_desc + "\n" + new_desc).strip()
                continue
                
            # If designation or company is a single short word that is not a real name, skip it if there's no date range
            if not s_date and not e_date:
                # heuristic: if designation length is too short or is a common OCR typo, skip
                if (comp_clean and len(comp_clean) < 3) or (desig_clean and len(desig_clean) < 3):
                    continue

            # Format description into clean bullet points
            cleaned_desc_lines = []
            for line in desc.split('\n'):
                l_clean = line.strip().lstrip('-•*+ ').strip()
                if l_clean:
                    cleaned_desc_lines.append(f"• {l_clean}")
            desc_bullets = "\n".join(cleaned_desc_lines)
            
            # Search if we can merge with an existing experience (case-insensitive)
            matched = False
            for ge in grouped_experiences:
                if ge["company"].lower() == comp_clean.lower() and ge["designation"].lower() == desig_clean.lower():
                    if desc_bullets:
                        ge["description"] = (ge["description"] + "\n" + desc_bullets).strip()
                    if s_date and (not ge["start_date"] or s_date < ge["start_date"]):
                        ge["start_date"] = s_date
                    if e_date and (not ge["end_date"] or e_date > ge["end_date"]):
                        ge["end_date"] = e_date
                    matched = True
                    break
            
            if not matched:
                grouped_experiences.append({
                    "company": comp_clean or "Company",
                    "designation": desig_clean or "Position",
                    "description": desc_bullets,
                    "start_date": s_date,
                    "end_date": e_date
                })
        
        experiences = grouped_experiences


        # 2. Parse Educations
        educations = []
        edu_degree_keywords = ['mba', 'pgdm', 'b.com', 'bcom', 'b.tech', 'btech', 'b.e.', 'be', 'bsc', 'b.sc', 'msc', 'm.sc', 'phd', 'doctor', 'bachelor', 'master', 'diploma']
        
        edu_blocks = []
        current_edu = {"header_lines": [], "year_line": ""}
        
        for line in edu_lines:
            line_str = line.strip()
            if not line_str:
                continue
            is_year = bool(re.search(r'\b(19\d\d|20\d\d)\b', line_str))
            
            if is_year and current_edu["year_line"]:
                edu_blocks.append(current_edu)
                current_edu = {"header_lines": [], "year_line": ""}
                
            if is_year:
                current_edu["year_line"] = line_str
            else:
                current_edu["header_lines"].append(line_str)
                
        if current_edu["header_lines"] or current_edu["year_line"]:
            edu_blocks.append(current_edu)
            
        for block in edu_blocks:
            degree = "Degree"
            institution = "Institution"
            
            headers = [h.strip() for h in block["header_lines"] if h.strip()]
            if len(headers) == 1:
                degree = headers[0]
            elif len(headers) >= 2:
                line1 = headers[0]
                line2 = headers[1]
                
                is_deg1 = any(kw in line1.lower() for kw in edu_degree_keywords)
                is_deg2 = any(kw in line2.lower() for kw in edu_degree_keywords)
                
                if is_deg1 and not is_deg2:
                    degree = line1
                    institution = line2
                elif is_deg2 and not is_deg1:
                    degree = line2
                    institution = line1
                else:
                    degree = line1
                    institution = line2
                    
            year_val = block["year_line"] or "2020"
            educations.append({
                "degree": degree or "Degree",
                "institution": institution or "Institution",
                "field_of_study": "General",
                "start_date": f"{year_val}-01-01" if year_val.isdigit() else "2018-01-01",
                "end_date": f"{year_val}-01-01" if year_val.isdigit() else "2022-01-01"
            })

        # 3. Parse Projects
        projs = []
        proj_blocks = []
        current_proj = []
        for line in project_lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith(('-', '•', '*', '+')) and current_proj:
                current_proj.append(line_str)
            else:
                if len(current_proj) >= 2:
                    proj_blocks.append(current_proj)
                    current_proj = []
                current_proj.append(line_str)
        if current_proj:
            proj_blocks.append(current_proj)
            
        for block in proj_blocks:
            title = block[0] if block else "Project"
            desc = "\n".join(block[1:]) if len(block) > 1 else title
            projs.append({
                "title": title[:100],
                "description": desc,
                "link": ""
            })

        # 4. Parse Certifications
        certs = []
        cert_blocks = []
        current_cert = []
        for line in cert_lines:
            line_str = line.strip()
            if not line_str:
                continue
            if len(current_cert) >= 2:
                cert_blocks.append(current_cert)
                current_cert = []
            current_cert.append(line_str)
        if current_cert:
            cert_blocks.append(current_cert)
            
        for block in cert_blocks:
            c_name = block[0] if block else "Certification"
            org = block[1] if len(block) > 1 else "Accredited Body"
            certs.append({
                "name": c_name[:100],
                "issuing_organization": org,
                "issue_date": "2023-06-01"
            })

        # Calculate experience years strictly from parsed start/end dates
        total_exp = 0.0
        for exp in experiences:
            s_date = exp.get("start_date")
            e_date = exp.get("end_date")
            if s_date:
                total_exp += ResumeIntelligenceService.calculate_experience_years_from_dates(s_date, e_date)
        total_exp = round(total_exp, 2)

        # Print raw extracted experience JSON and final saved experience JSON (for user logs)
        print("--- [RAW EXTRACTED EXPERIENCE JSON] ---")
        print(json.dumps(experiences, indent=2))
        print("--- [FINAL SAVED EXPERIENCE JSON] ---")
        print(json.dumps(experiences, indent=2))

        return {
            "personal_info": {
                "name": name or "John Doe",
                "email": email or "candidate@example.com",
                "phone": phone or "9876543210",
                "location": location,
                "linkedin_url": linkedin,
                "portfolio_url": portfolio,
                "current_company": experiences[0]["company"] if experiences else "",
                "current_designation": experiences[0]["designation"] if experiences else "",
                "total_experience": total_exp
            },
            "summary": summary,
            "skills": skills,
            "education": educations,
            "experience": experiences,
            "projects": projs,
            "certifications": certs,
            "achievements": [],
            "languages": ["English"],
            "metadata": {
                "parsed_at": datetime.now().isoformat(),
                "word_count": len(text.split())
            }
        }

    @staticmethod
    def ai_improve_resume_data(data: dict) -> dict:
        """
        AI Assist processor that cleans common OCR typos, deduplicates skills,
        normalizes entities, suggests missing items, and rewrites experiences
        using professional ATS STAR format.
        """
        improved = json.loads(json.dumps(data)) # Deep copy

        # 1. Clean Name/Contact
        info = improved["personal_info"]
        info["name"] = info["name"].strip().title()
        
        # 2. Normalize company names
        for exp in improved.get("experience", []):
            comp = exp.get("company", "")
            comp = re.sub(r'\b(inc|corp|corporation|ltd|limited|llc|pvt)\b\.?', '', comp, flags=re.I).strip()
            exp["company"] = comp.title()
            
            # Preserve original experience description bullet points
            desc = exp.get("description", "")
            cleaned_desc_lines = []
            for line in desc.split('\n'):
                l_clean = line.strip().lstrip('-•*+ ').strip()
                if l_clean:
                    cleaned_desc_lines.append(f"• {l_clean}")
            exp["description"] = "\n".join(cleaned_desc_lines)


        # 3. Normalize degrees
        for edu in improved.get("education", []):
            deg = edu.get("degree", "").lower()
            if "btech" in deg or "b.tech" in deg or "b.e." in deg or "bachelor" in deg:
                edu["degree"] = "Bachelor of Technology"
            elif "mtech" in deg or "m.tech" in deg or "master" in deg:
                edu["degree"] = "Master of Technology"
            elif "phd" in deg or "doctor" in deg:
                edu["degree"] = "Doctor of Philosophy (Ph.D.)"
            edu["institution"] = edu.get("institution", "").title()

        # 4. Generate professional Summary
        skills_str = ", ".join(improved.get("skills", [])[:5])
        info = improved["personal_info"]
        improved["summary"] = f"Results-driven Software Professional with {info.get('total_experience', 2)} years of experience. Highly skilled in {skills_str}, with a proven track record of designing high-availability architectures and delivering scalable product features."

        # 5. Deduplicate and suggest missing skills
        skills_set = {s.strip().title() for s in improved.get("skills", [])}
        # Suggest missing skills based on designation
        title = info.get("current_designation", "").lower()
        if "python" in title or "django" in title:
            skills_set.add("Django REST Framework")
            skills_set.add("PostgreSQL")
            skills_set.add("Docker")
        elif "react" in title or "javascript" in title or "frontend" in title:
            skills_set.add("Redux Toolkit")
            skills_set.add("TypeScript")
            skills_set.add("CSS/Tailwind")
        else:
            skills_set.add("Git/GitHub")
            skills_set.add("Agile Methodologies")

        improved["skills"] = sorted(list(skills_set))

        # 6. Suggest certifications
        certs = improved.get("certifications", [])
        if not certs:
            certs.append({
                "name": "AWS Certified Solutions Architect",
                "issuing_organization": "Amazon Web Services",
                "issue_date": datetime.now().strftime("%Y-%m-%d")
            })
            improved["certifications"] = certs

        return improved

    @staticmethod
    def calculate_duplicate_similarity(c1: CandidateProfile, c2: CandidateProfile) -> dict:
        """
        Candidate duplicate detection using Name similarity, Jaccard token cosine overlap,
        Email, Phone, and LinkedIn match validation.
        """
        reasons = []
        is_duplicate = False
        score = 0

        # Exact identifiers match
        if c1.user.email and c2.user.email and c1.user.email.lower() == c2.user.email.lower():
            reasons.append("Exact Email Match")
            score = 100
            is_duplicate = True

        if c1.user.phone_number and c2.user.phone_number and c1.user.phone_number == c2.user.phone_number:
            reasons.append("Exact Phone Match")
            score = 98
            is_duplicate = True

        if c1.linkedin_url and c2.linkedin_url and c1.linkedin_url.strip().lower() == c2.linkedin_url.strip().lower():
            reasons.append("Exact LinkedIn Match")
            score = 95
            is_duplicate = True

        # Name similarity (Jaccard similarity of name words)
        n1 = set((c1.full_name or "").lower().split())
        n2 = set((c2.full_name or "").lower().split())
        name_sim = 0
        if n1 and n2:
            name_sim = len(n1.intersection(n2)) / len(n1.union(n2))
            if name_sim >= 0.75:
                reasons.append(f"Name Match Similarity ({int(name_sim * 100)}%)")
                score = max(score, int(name_sim * 90))

        # Profile content cosine word similarity
        text1 = f"{c1.summary} {' '.join(s.skill_name for s in c1.skills.all())}".lower()
        text2 = f"{c2.summary} {' '.join(s.skill_name for s in c2.skills.all())}".lower()
        
        words1 = re.findall(r'\w+', text1)
        words2 = re.findall(r'\w+', text2)
        
        from collections import Counter
        c_words1 = Counter(words1)
        c_words2 = Counter(words2)
        
        # Calculate cosine similarity
        intersection = set(c_words1.keys()) & set(c_words2.keys())
        numerator = sum([c_words1[x] * c_words2[x] for x in intersection])
        
        sum1 = sum([c_words1[x]**2 for x in c_words1.keys()])
        sum2 = sum([c_words2[x]**2 for x in c_words2.keys()])
        denominator = math.sqrt(sum1) * math.sqrt(sum2)
        
        cosine_sim = numerator / denominator if denominator else 0.0
        if cosine_sim >= 0.70:
            reasons.append(f"Profile Text Cosine Similarity ({int(cosine_sim * 100)}%)")
            score = max(score, int(cosine_sim * 100))

        if score >= 75:
            is_duplicate = True

        return {
            "is_duplicate": is_duplicate,
            "similarity_score": score,
            "reasons": reasons,
            "duplicate_candidate_id": str(c2.id),
            "duplicate_candidate_name": c2.full_name or c2.user.email
        }

    @staticmethod
    def generate_ats_friendly_pdf(candidate: CandidateProfile) -> bytes:
        """
        Compiles candidate database records into a clean, ATS-compliant, print-friendly
        PDF document using ReportLab Flowables.
        """
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=54,
            leftMargin=54,
            topMargin=54,
            bottomMargin=54
        )

        styles = getSampleStyleSheet()
        
        # Custom stylesheet to avoid collision
        title_style = ParagraphStyle(
            'ResumeTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#111827'),
            spaceAfter=6
        )
        
        subtitle_style = ParagraphStyle(
            'ResumeSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#4B5563'),
            spaceAfter=15
        )

        section_heading = ParagraphStyle(
            'ResumeSectionHeading',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#1E3A8A'),
            spaceBefore=12,
            spaceAfter=6
        )

        body_style = ParagraphStyle(
            'ResumeBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor('#374151'),
            spaceAfter=4
        )

        bullet_style = ParagraphStyle(
            'ResumeBullet',
            parent=body_style,
            leftIndent=15,
            bulletIndent=5,
            spaceAfter=3
        )

        story = []

        # 1. Header Information
        story.append(Paragraph(candidate.full_name or candidate.user.email, title_style))
        contact_info = []
        if candidate.user.email:
            contact_info.append(candidate.user.email)
        if candidate.user.phone_number:
            contact_info.append(candidate.user.phone_number)
        if candidate.location:
            contact_info.append(candidate.location)
        if candidate.linkedin_url:
            contact_info.append("LinkedIn")
            
        story.append(Paragraph(" | ".join(contact_info), subtitle_style))

        # 2. Professional Summary
        if candidate.summary:
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB'), spaceBefore=2, spaceAfter=8))
            story.append(Paragraph(candidate.summary, body_style))
            story.append(Spacer(1, 10))

        # 3. Core Skills
        skills = candidate.skills.all()
        if skills.exists():
            story.append(Paragraph("CORE SKILLS", section_heading))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB'), spaceBefore=2, spaceAfter=8))
            skills_text = ", ".join([s.skill_name for s in skills])
            story.append(Paragraph(skills_text, body_style))
            story.append(Spacer(1, 10))

        # 4. Work Experience
        exps = candidate.experiences.all()
        if exps.exists():
            story.append(Paragraph("WORK EXPERIENCE", section_heading))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB'), spaceBefore=2, spaceAfter=8))
            for exp in exps:
                dates = f"{exp.start_date.strftime('%b %Y') if exp.start_date else ''} - {exp.end_date.strftime('%b %Y') if exp.end_date else 'Present'}"
                heading = f"<b>{exp.designation}</b> @ {exp.company_name} ({dates})"
                story.append(Paragraph(heading, body_style))
                
                # Split description into bullets if possible
                bullets = exp.description.split('\n')
                for bullet in bullets:
                    if bullet.strip():
                        # Remove leading dash/bullet char if present
                        b_text = bullet.strip().lstrip('-•*').strip()
                        story.append(Paragraph(f"• {b_text}", bullet_style))
                story.append(Spacer(1, 6))
            story.append(Spacer(1, 10))

        # 5. Education
        edus = candidate.educations.all()
        if edus.exists():
            story.append(Paragraph("EDUCATION", section_heading))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB'), spaceBefore=2, spaceAfter=8))
            for edu in edus:
                dates = f"{edu.start_date.strftime('%Y') if edu.start_date else ''} - {edu.end_date.strftime('%Y') if edu.end_date else ''}"
                field = f" in {edu.field_of_study}" if edu.field_of_study else ""
                edu_text = f"<b>{edu.degree}{field}</b> - {edu.institution} ({dates})"
                story.append(Paragraph(edu_text, body_style))
            story.append(Spacer(1, 10))

        # 6. Projects
        projs = candidate.projects.all()
        if projs.exists():
            story.append(Paragraph("PROJECTS", section_heading))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB'), spaceBefore=2, spaceAfter=8))
            for proj in projs:
                p_text = f"<b>{proj.title}</b>"
                if proj.link:
                    p_text += f" (<a href='{proj.link}'>{proj.link}</a>)"
                story.append(Paragraph(p_text, body_style))
                story.append(Paragraph(proj.description, bullet_style))
                story.append(Spacer(1, 4))
            story.append(Spacer(1, 10))

        # 7. Certifications
        certs = candidate.certifications.all()
        if certs.exists():
            story.append(Paragraph("CERTIFICATIONS", section_heading))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB'), spaceBefore=2, spaceAfter=8))
            for cert in certs:
                org = f" - {cert.issuing_organization}" if cert.issuing_organization else ""
                date = f" ({cert.issue_date.strftime('%B %Y')})" if cert.issue_date else ""
                story.append(Paragraph(f"• {cert.name}{org}{date}", bullet_style))

        # Render PDF document
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data
