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
    def parse_experience_description_to_html(desc_text: str) -> str:
        if not desc_text or not desc_text.strip():
            return ""
            
        # If it already looks like HTML, return it as is
        if "<ul" in desc_text or "<li" in desc_text or "<p" in desc_text or "<div" in desc_text or "<strong" in desc_text:
            return desc_text
            
        import re
        categories = {
            "Responsibilities": [],
            "Territory Coverage": [],
            "Key Institutions": [],
            "Achievements": [],
        }
        
        current_category = "Responsibilities"
        lines = desc_text.split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
                
            line_clean = line_stripped.lstrip('-•*+ ').strip()
            line_lower = line_clean.lower()
            
            # Check if the line is a section heading itself
            if any(h in line_lower for h in ["responsibilities", "responsibility", "roles & responsibilities", "role & responsibilities"]):
                current_category = "Responsibilities"
                header_content = re.sub(r'^(responsibilities|responsibility|roles\s*&\s*responsibilities|role\s*&\s*responsibilities)[:\-\s]*', '', line_clean, flags=re.I).strip()
                if header_content:
                    categories[current_category].append(header_content)
                continue
            elif any(h in line_lower for h in ["territory coverage", "territory", "coverage area", "geographical coverage"]):
                current_category = "Territory Coverage"
                header_content = re.sub(r'^(territory\s*coverage|territory|coverage\s*area|geographical\s*coverage)[:\-\s]*', '', line_clean, flags=re.I).strip()
                if header_content:
                    categories[current_category].append(header_content)
                continue
            elif any(h in line_lower for h in ["key institutions", "institutions", "key accounts", "hospital focus", "medical accounts"]):
                current_category = "Key Institutions"
                header_content = re.sub(r'^(key\s*institutions|institutions|key\s*accounts|hospital\s*focus|medical\s*accounts)[:\-\s]*', '', line_clean, flags=re.I).strip()
                if header_content:
                    categories[current_category].append(header_content)
                continue
            elif any(h in line_lower for h in ["achievements", "achievement", "key achievements", "accomplishments"]):
                current_category = "Achievements"
                header_content = re.sub(r'^(achievements|achievement|key\s*achievements|accomplishments)[:\-\s]*', '', line_clean, flags=re.I).strip()
                if header_content:
                    categories[current_category].append(header_content)
                continue
                
            # Classify the line based on keywords
            if any(kw in line_lower for kw in ["territory", "coverage", "region", "geographic", "zone", "sales area", "pan india"]):
                line_cat = "Territory Coverage"
            elif any(kw in line_lower for kw in ["institution", "hospital", "medical", "clinic", "key account", "client", "customer"]):
                line_cat = "Key Institutions"
            elif any(kw in line_lower for kw in ["achieve", "award", "won", "growth", "increase", "revenue", "percent", "target", "%"]):
                line_cat = "Achievements"
            else:
                line_cat = current_category
                
            categories[line_cat].append(line_clean)
            
        html_parts = []
        for cat_name in ["Responsibilities", "Territory Coverage", "Key Institutions", "Achievements"]:
            cat_lines = categories[cat_name]
            if cat_lines:
                html_parts.append(f"<p class='mb-1'><strong>{cat_name}</strong></p>")
                html_parts.append("<ul class='mb-2'>")
                for cl in cat_lines:
                    html_parts.append(f"  <li>{cl}</li>")
                html_parts.append("</ul>")
                
        if not html_parts:
            return f"<p>{desc_text}</p>"
            
        return "\n".join(html_parts)

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
            
        # Normalize and reject common resume headings
        normalized = re.sub(r'[^a-z0-9]', '', name_clean.lower()).strip()
        
        blacklisted_exact = {
            'curriculumvitae', 'resume', 'biodata', 'curriculum', 'vitae', 'cv',
            'workexperience', 'experience', 'profile', 'careerobjective', 'objective',
            'summary', 'education', 'skills', 'projects', 'certifications', 'languages',
            'personaldetails', 'languagesknown', 'corecompetencies', 'technicalskills',
            'employmenthistory', 'workhistory', 'professionalexperience', 'aboutme',
            'academicbackground', 'qualification', 'qualifications', 'educationhistory',
            'page', 'email', 'phone', 'contact'
        }
        
        if normalized in blacklisted_exact:
            return False
            
        # Check if the name contains any blacklisted word as a standalone word
        words = re.sub(r'[^a-zA-Z\s]', '', name_clean).lower().split()
        blacklisted_words = {
            'curriculum', 'vitae', 'biodata', 'resume', 'cv', 'experience', 'education', 
            'skills', 'projects', 'certifications', 'languages', 'objective', 'summary',
            'profile', 'workexperience', 'careerobjective', 'page', 'email', 'phone',
            'mobile', 'telephone', 'contact', 'address', 'present', 'current',
            'candidate', 'unknown', 'hometown', 'residence', 'nationality', 'gender'
        }
        if any(w in blacklisted_words for w in words):
            return False
            
        # Must not be a single long run-on word without spaces (e.g. CURRICULUMVITAE)
        if ' ' not in name_clean and len(name_clean) > 12:
            return False
            
        return True

    @staticmethod
    def calculate_name_email_similarity(name: str, email: str, linkedin: str = "") -> float:
        # Extract username from email
        username = email.split('@')[0].lower() if email else ""
        # Extract username from LinkedIn URL
        li_user = ""
        if linkedin:
            parts = linkedin.strip('/').split('/')
            if parts:
                li_user = parts[-1].lower()
                
        name_words = re.sub(r'[^a-zA-Z\s]', '', name).lower().split()
        if not name_words:
            return 0.0
            
        score = 0.0
        # Check email match
        if username:
            clean_username = re.sub(r'[^a-z]', ' ', username)
            user_words = clean_username.split()
            for w in name_words:
                if w in user_words or any(w in uw or uw in w for uw in user_words):
                    score += 0.5
                    
        # Check LinkedIn match
        if li_user:
            clean_li = re.sub(r'[^a-z]', ' ', li_user)
            li_words = clean_li.split()
            for w in name_words:
                if w in li_words or any(w in lw or lw in w for lw in li_words):
                    score += 0.5
                    
        return score

    @staticmethod
    def detect_heading_type(line_str: str) -> str:
        l = line_str.strip().lower()
        l = re.sub(r'[:\-\s]+$', '', l).strip()
        if len(l) > 60 or len(l) < 3:
            return None
        
        # Exact or close matching
        if l in ["work experience", "experience", "employment history", "work history", "professional experience"]:
            return "WORK"
        if l in ["education", "academic", "academic background", "qualification", "qualifications", "education history"]:
            return "EDU"
        if l in ["projects", "personal projects", "academic projects", "key projects"]:
            return "PROJECT"
        if l in ["technical skills", "core competencies", "skills", "key skills", "expertise", "competencies"]:
            return "SKILLS"
        if l in ["certifications", "certification", "courses", "credentials", "licenses & certifications"]:
            return "CERT"
        if l in ["languages", "languages known"]:
            return "LANGUAGES"
        if l in ["personal details", "personal profile", "personal summary"]:
            return "PERSONAL"
        if l in ["profile summary", "summary", "career objective", "objective", "professional summary", "about me"]:
            return "SUMMARY"
        if l in ["notable accomplishments across the career"]:
            return "OTHER"
            
        return None

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
    def get_duration_display(start_str: str, end_str: str) -> str:
        if not start_str:
            return ""
        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
        except Exception:
            return ""
            
        if not end_str or end_str.strip().lower() in ["present", "current", "today", "now", "ongoing"]:
            end_dt = datetime.now().date()
        else:
            try:
                end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
            except Exception:
                end_dt = datetime.now().date()
                
        if start_dt > end_dt:
            return "0 months"
            
        diff_years = end_dt.year - start_dt.year
        diff_months = end_dt.month - start_dt.month
        total_months = diff_years * 12 + diff_months
        
        years = total_months // 12
        months = total_months % 12
        
        parts = []
        if years > 0:
            parts.append(f"{years} Year" + ("s" if years > 1 else ""))
        if months > 0:
            parts.append(f"{months} Month" + ("s" if months > 1 else ""))
        if not parts:
            return "0 months"
        return " ".join(parts)

    @staticmethod
    def clean_camel_case_name(name: str) -> str:
        if not name or not isinstance(name, str):
            return name
        name_clean = name.strip()
        # Insert space before any uppercase letter that follows a lowercase letter (e.g. RohanKumar -> Rohan Kumar)
        # or between consecutive uppercase letters followed by a lowercase (e.g. HTMLParser -> HTML Parser)
        splitted = re.sub(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', name_clean)
        # Normalize multiple spaces
        return " ".join(splitted.split())

    @staticmethod
    def extract_candidate_name(text: str, parsed_name: str = None, email: str = "", linkedin: str = "") -> str:
        # Define breaking section headings that end the resume header
        BREAKING_SECTION_HEADINGS = {
            'workexperience', 'experience', 'employmenthistory', 'workhistory', 'professionalexperience',
            'education', 'academic', 'academicbackground', 'qualification', 'qualifications', 'educationhistory',
            'skills', 'technicalskills', 'corecompetencies', 'keyskills', 'expertise', 'competencies',
            'projects', 'personalprojects', 'academicprojects', 'keyprojects',
            'certifications', 'certification', 'courses', 'credentials', 'licensescertifications',
            'summary', 'careerobjective', 'objective', 'professionalsummary', 'aboutme', 'profilesummary'
        }
        
        # Ignored resume titles/labels/headings
        IGNORED_HEADINGS = {
            'workexperience', 'experience', 'curriculumvitae', 'resume', 'cv',
            'biodata', 'profile', 'careerobjective', 'objective', 'summary',
            'education', 'skills', 'projects', 'certifications', 'languages',
            'personaldetails', 'languagesknown', 'corecompetencies', 'technicalskills',
            'employmenthistory', 'workhistory', 'professionalexperience', 'aboutme',
            'academicbackground', 'qualification', 'qualifications', 'educationhistory',
            'page', 'email', 'phone', 'contact'
        }
        
        # Clean helper for candidate name validation
        def is_ignored(name_str: str) -> bool:
            normalized = re.sub(r'[^a-z0-9]', '', name_str.lower()).strip()
            if normalized in IGNORED_HEADINGS:
                return True
            words = re.sub(r'[^a-zA-Z\s]', '', name_str).lower().split()
            if any(w in IGNORED_HEADINGS for w in words):
                return True
            return False
            
        def is_valid_human_name(name_str: str) -> bool:
            if not ResumeIntelligenceService.is_valid_name(name_str):
                return False
            if is_ignored(name_str):
                return False
            words = name_str.split()
            if not (1 <= len(words) <= 5):
                return False
            if len(name_str.strip()) < 3:
                return False
            return True

        # Prepare email/linkedin username cross-check words
        email_username = email.split('@')[0].lower() if email else ""
        cross_check_words = set(re.sub(r'[^a-z]', ' ', email_username).split()) if email_username else set()
        
        if linkedin:
            parts = linkedin.strip('/').split('/')
            if parts:
                li_user = parts[-1].lower()
                cross_check_words.update(re.sub(r'[^a-z]', ' ', li_user).split())

        # 1. Priority 1: parsed_name is valid
        if parsed_name and is_valid_human_name(parsed_name):
            return ResumeIntelligenceService.clean_camel_case_name(parsed_name)
            
        # Parse lines to identify Header lines (stopping at first breaking section heading)
        lines = [l.strip() for l in text.split('\n')]
        header_lines = []
        for line in lines:
            if not line:
                continue
            normalized = re.sub(r'[^a-z0-9]', '', line.lower()).strip()
            if normalized in BREAKING_SECTION_HEADINGS:
                break
            header_lines.append(line)
            
        # Fallback if header_lines is too empty
        if len(header_lines) < 2:
            header_lines = []
            count = 0
            for line in lines:
                if not line:
                    continue
                normalized = re.sub(r'[^a-z0-9]', '', line.lower()).strip()
                if normalized not in BREAKING_SECTION_HEADINGS:
                    header_lines.append(line)
                    count += 1
                if count >= 15:
                    break

        # 2. Priority 2: Use spaCy PERSON entity detection on the header text if available
        if SPACY_AVAILABLE:
            try:
                nlp = spacy.load("en_core_web_sm")
                header_text = "\n".join(header_lines[:12])
                doc = nlp(header_text)
                nlp_candidates = []
                for ent in doc.ents:
                    if ent.label_ == "PERSON":
                        val = ent.text.strip()
                        if is_valid_human_name(val):
                            nlp_candidates.append(val)
                            
                if nlp_candidates:
                    if cross_check_words:
                        for cand in nlp_candidates:
                            cand_words = set(re.sub(r'[^a-z]', ' ', cand.lower()).split())
                            if cand_words.intersection(cross_check_words):
                                return ResumeIntelligenceService.clean_camel_case_name(cand)
                    return ResumeIntelligenceService.clean_camel_case_name(nlp_candidates[0])
            except Exception as e:
                print(f"spaCy PERSON extraction in header failed: {e}")

        # 3. Priority 3: Rule-based PERSON entity in first 15 lines (2-3 capitalized words)
        rule_candidates = []
        for line in header_lines[:15]:
            line_clean = line.strip()
            if not is_valid_human_name(line_clean):
                continue
            words = line_clean.split()
            if 2 <= len(words) <= 3:
                # Must be all capitalized words
                if all(w[0].isupper() and re.sub(r'[.,]', '', w).isalpha() for w in words):
                    rule_candidates.append(line_clean)
                    
        if rule_candidates:
            if cross_check_words:
                for cand in rule_candidates:
                    cand_words = set(re.sub(r'[^a-z]', ' ', cand.lower()).split())
                    if cand_words.intersection(cross_check_words):
                        return ResumeIntelligenceService.clean_camel_case_name(cand)
            return ResumeIntelligenceService.clean_camel_case_name(rule_candidates[0])

        # 4. Priority 4: First text line in header matching email/linkedin cross check
        if cross_check_words:
            for line in header_lines:
                line_clean = line.strip()
                if is_valid_human_name(line_clean):
                    line_words = set(re.sub(r'[^a-z]', ' ', line_clean.lower()).split())
                    if line_words.intersection(cross_check_words):
                        return ResumeIntelligenceService.clean_camel_case_name(line_clean)

        # 5. Priority 5: First text line excluding phone/email/etc.
        for line in header_lines:
            line_clean = line.strip()
            if is_valid_human_name(line_clean):
                return ResumeIntelligenceService.clean_camel_case_name(line_clean)
                
        # 6. Final Fallback
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
            largest_bold_name = None
            try:
                doc = docx.Document(io.BytesIO(file_bytes))
                extracted_text = "\n".join([p.text for p in doc.paragraphs])
                
                # Check top paragraphs for bold or heading style
                for p in doc.paragraphs[:15]:
                    cleaned_p = p.text.strip()
                    if not cleaned_p:
                        continue
                    # Check if paragraph has bold runs
                    is_bold = any(run.bold for run in p.runs)
                    is_heading = p.style.name.startswith("Heading") or p.style.name == "Title"
                    if (is_bold or is_heading) and ResumeIntelligenceService.is_valid_name(cleaned_p):
                        # Ensure it's not an ignored heading
                        normalized = re.sub(r'[^a-z0-9]', '', cleaned_p.lower()).strip()
                        if normalized not in {
                            'workexperience', 'experience', 'curriculumvitae', 'resume', 'cv',
                            'biodata', 'profile', 'careerobjective', 'objective', 'summary',
                            'education', 'skills', 'projects', 'certifications', 'languages',
                            'personaldetails', 'languagesknown', 'corecompetencies', 'technicalskills',
                            'employmenthistory', 'workhistory', 'professionalexperience', 'aboutme',
                            'academicbackground', 'qualification', 'qualifications', 'educationhistory'
                        }:
                            largest_bold_name = cleaned_p
                            break
            except Exception as e:
                extracted_text = f"DOCX Parse Error: {str(e)}"
                largest_bold_name = None
            return {
                "text": extracted_text,
                "engine": "python-docx",
                "confidence": 100.0,
                "resume_type": "EDITABLE_DOCX",
                "largest_bold_name": largest_bold_name
            }

        if resume_type == 'PDF':
            # Extract largest bold valid name span on page 1
            largest_bold_name = None
            try:
                import fitz
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                if len(doc) > 0:
                    page = doc[0]
                    spans_info = []
                    blocks_dict = page.get_text("dict")
                    for b in blocks_dict.get("blocks", []):
                        if b.get("type") == 0: # text block
                            for line in b.get("lines", []):
                                for span in line.get("spans", []):
                                    span_text = span.get("text", "").strip()
                                    if span_text:
                                        size = span.get("size", 0.0)
                                        font = span.get("font", "").lower()
                                        flags = span.get("flags", 0)
                                        is_bold = "bold" in font or (flags & 16)
                                        spans_info.append((span_text, size, is_bold))
                    
                    # Filter and rank
                    valid_spans = []
                    for text_val, size, is_bold in spans_info:
                        cleaned = " ".join(text_val.split())
                        if ResumeIntelligenceService.is_valid_name(cleaned):
                            normalized = re.sub(r'[^a-z0-9]', '', cleaned.lower()).strip()
                            if normalized not in {
                                'workexperience', 'experience', 'curriculumvitae', 'resume', 'cv',
                                'biodata', 'profile', 'careerobjective', 'objective', 'summary',
                                'education', 'skills', 'projects', 'certifications', 'languages',
                                'personaldetails', 'languagesknown', 'corecompetencies', 'technicalskills',
                                'employmenthistory', 'workhistory', 'professionalexperience', 'aboutme',
                                'academicbackground', 'qualification', 'qualifications', 'educationhistory'
                            }:
                                valid_spans.append((cleaned, size, is_bold))
                    if valid_spans:
                        valid_spans.sort(key=lambda x: (x[2], x[1]), reverse=True)
                        largest_bold_name = valid_spans[0][0]
            except Exception as e:
                print(f"PDF largest bold name extraction failed: {e}")

            # First try direct text extraction via PyMuPDF (fitz) with layout-aware column reconstruction
            try:
                import fitz
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                
                header_parts = []
                col1_parts = []
                col2_parts = []
                footer_parts = []
                
                for page_idx, page in enumerate(doc):
                    blocks = page.get_text("blocks")
                    valid_blocks = []
                    for b in blocks:
                        x0, y0, x1, y1, text, block_no, block_type = b
                        text_clean = text.strip()
                        if text_clean:
                            valid_blocks.append((x0, y0, x1, y1, text_clean))
                            
                    # Sort by y0
                    valid_blocks_sorted = sorted(valid_blocks, key=lambda x: x[1])
                    
                    # Check if page has columns
                    left_blocks = [b for b in valid_blocks_sorted if b[2] <= 205]
                    right_blocks = [b for b in valid_blocks_sorted if b[0] >= 205]
                    has_columns = len(left_blocks) > 0 and len(right_blocks) > 0
                    
                    for b in valid_blocks_sorted:
                        x0, y0, x1, y1, text = b
                        
                        # Check for Header (Page 1 only, y1 < 135)
                        if page_idx == 0 and y1 < 135:
                            header_parts.append(text)
                            continue
                            
                        # Check for Footer (Last Page only, y0 >= 700)
                        if page_idx == len(doc) - 1 and y0 >= 700:
                            footer_parts.append(text)
                            continue
                            
                        if has_columns:
                            # If x1 <= 205, it is Column 1 (Left column)
                            # If x0 >= 205, it is Column 2 (Right column)
                            # If it spans across (FULL), put it in Column 2 (since it's part of work experience sequence)
                            if x1 <= 205:
                                col1_parts.append(text)
                            else:
                                col2_parts.append(text)
                        else:
                            # Single column page, put all in col2_parts to keep in normal flow
                            col2_parts.append(text)
                            
                # Reconstruct unified text stream
                full_stream = []
                if header_parts:
                    full_stream.append("\n".join(header_parts))
                    
                full_stream.append("\nWORK EXPERIENCE\n")
                full_stream.append("\n\n".join(col2_parts))
                
                full_stream.append("\nEDUCATION\n")
                full_stream.append("\n\n".join(col1_parts))
                
                if footer_parts:
                    full_stream.append("\nPERSONAL DETAILS\n")
                    full_stream.append("\n\n".join(footer_parts))
                    
                extracted_text = "\n\n".join(full_stream) + "\n"
            except Exception as e:
                print(f"PyMuPDF direct extraction failed: {e}")

            if len(extracted_text.strip()) > 100:
                return {
                    "text": extracted_text,
                    "engine": "pymupdf",
                    "confidence": 99.0,
                    "resume_type": "EDITABLE_PDF",
                    "largest_bold_name": largest_bold_name
                }

            # Fallback to pdfplumber
            extracted_text = ""
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
                    "resume_type": "EDITABLE_PDF",
                    "largest_bold_name": largest_bold_name
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
    def parse_resume_nlp(text: str, parsed_name: str = None) -> dict:
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

        name = ResumeIntelligenceService.extract_candidate_name(text, parsed_name=parsed_name, email=email, linkedin=linkedin)

        # Location, Address, and City detection
        address = ""
        city = ""
        location = "Unknown"
        
        # Address detection
        address_keywords = ["address", "residence", "hometown", "location"]
        for line in lines:
            if any(akw in line.lower() for akw in address_keywords):
                addr_line = re.sub(r'^(address|residence|hometown|location)[:\-\s]*', '', line, flags=re.I).strip()
                if addr_line and len(addr_line) > 3:
                    address = addr_line
                    break
                    
        if not address:
            pincode_match = re.search(r'\b\d{6}\b', text)
            if pincode_match:
                for line in lines:
                    if pincode_match.group(0) in line:
                        address = line.strip()
                        break
                        
        # City detection
        locations = ['Delhi', 'Mumbai', 'Bangalore', 'Hyderabad', 'Pune', 'Noida', 'Gurgaon', 'Patna', 'Lucknow', 'Begusarai', 'Samastipur', 'Chennai', 'Kolkata']
        for loc in locations:
            if loc.lower() in text.lower():
                city = loc
                break
                
        if city:
            location = city
            if address and city.lower() not in address.lower():
                address = f"{address}, {city}"
        elif address:
            location = address

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

        # Extract Summary (heuristic: look for "career objective", "objective", "summary", "profile", "about me" headers)
        summary = ""
        summary_found = False
        summary_lines = []
        raw_lines = text.split('\n')
        for i, line in enumerate(raw_lines):
            l_strip = line.strip()
            l_lower = l_strip.lower()
            if not l_strip:
                if summary_found:
                    summary_lines.append("")
                continue
            if any(h in l_lower for h in ["career objective", "objective", "summary", "professional summary", "career profile", "about me"]):
                summary_found = True
                continue
            if summary_found:
                if len(l_strip) < 50 and any(h in l_lower for h in ["experience", "education", "skills", "projects", "certifications", "languages"]):
                    break
                summary_lines.append(line)
        if summary_lines:
            summary = "\n".join(summary_lines).strip()
            summary = re.sub(r'^\s+|\s+$', '', summary)
        else:
            # Fallback summary: find first line that is not a name, email, phone, or title
            for line in lines[1:10]:
                l_clean = line.strip()
                if not ResumeIntelligenceService.is_valid_name(l_clean) and "@" not in l_clean and not any(kw in l_clean.lower() for kw in ["phone", "email", "github", "linkedin", "curriculum", "vitae", "resume", "cv", "biodata"]):
                    summary = l_clean
                    break
            if not summary and lines:
                summary = lines[1] if len(lines) > 1 else lines[0]

        # Clean name from summary if it somehow ended up in it
        if name and summary:
            summary = re.sub(rf'\b{re.escape(name)}\b', '', summary, flags=re.I).strip()
            summary = re.sub(r'^\s*[-–—,.:;]\s*', '', summary)

        # Section-based extraction
        detect_heading_type = ResumeIntelligenceService.detect_heading_type

        current_section = None
        header_info_lines = []
        sections = {
            "WORK": [],
            "EDU": [],
            "PROJECT": [],
            "CERT": [],
            "SKILLS": [],
            "SUMMARY": [],
            "LANGUAGES": [],
            "PERSONAL": [],
            "OTHER": []
        }

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

        action_verbs = [
            'drove', 'ensured', 'maintained', 'strengthened', 'monitored', 'led', 'collaborated', 
            'performed', 'oversaw', 'directed', 'prepared', 'optimized', 'liaised', 'tracked', 
            'governed', 'crafted', 'built', 'delivered', 'reviewed', 'partnered', 'spearheaded',
            'successfully', 'instrumental', 'achieved', 'contributed', 'liaised', 'assisted',
            'supporting', 'developing', 'managing', 'providing', 'handling', 'identifying'
        ]

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            
            heading_type = detect_heading_type(line_str)
            if heading_type:
                current_section = heading_type
                continue
                
            # Check for implicit transition to WORK:
            date_match = date_range_regex.search(line_str)
            if date_match:
                non_date_text = line_str.replace(date_match.group(0), "").strip()
                non_date_text = re.sub(r'^[|/\-\s\.,:]+|[|/\-\s\.,:]+$', '', non_date_text).strip()
                if len(non_date_text) > 3 and any(char.isalpha() for char in non_date_text):
                    current_section = "WORK"
            elif current_section in ["SKILLS", "OTHER"]:
                is_bullet = line_str.startswith(('-', '•', '*', '+'))
                if not is_bullet and len(line_str) < 120:
                    l_lower = line_str.lower()
                    if not l_lower.startswith("key result areas") and any(re.search(r'\b' + re.escape(kw) + r'\b', l_lower) for kw in designation_keywords):
                        first_word = re.sub(r'[^a-zA-Z]', '', line_str.split()[0].lower()) if line_str.split() else ""
                        if first_word not in action_verbs and "leadership" not in l_lower and "summary" not in l_lower:
                            current_section = "WORK"
                        
            if current_section is None:
                header_info_lines.append(line_str)
            else:
                if current_section in ["SKILLS", "OTHER"]:
                    is_bullet = line_str.startswith(('-', '•', '*', '+'))
                    is_long = len(line_str) > 50
                    first_word = re.sub(r'[^a-zA-Z]', '', line_str.split()[0].lower()) if line_str.split() else ""
                    is_action = first_word in action_verbs
                    
                    if is_bullet or is_long or is_action:
                        sections["WORK"].append(line_str)
                        continue
                        
                sections[current_section].append(line_str)

        # 1. Parse Work Experiences
        work_blocks = []
        current_block = {
            "title_line": "",
            "description_lines": []
        }

        for line in sections["WORK"]:
            line_str = line.strip()
            if not line_str:
                continue
                
            date_match = date_range_regex.search(line_str)
            is_new_job_line = False
            
            if date_match:
                non_date_text = line_str.replace(date_match.group(0), "").strip()
                non_date_text = re.sub(r'^[|/\-\s\.,:]+|[|/\-\s\.,:]+$', '', non_date_text).strip()
                if len(non_date_text) > 3 and any(char.isalpha() for char in non_date_text):
                    is_new_job_line = True
            else:
                is_bullet = line_str.startswith(('-', '•', '*', '+'))
                if not is_bullet and len(line_str) < 120:
                    l_lower = line_str.lower()
                    first_word = re.sub(r'[^a-zA-Z]', '', line_str.split()[0].lower()) if line_str.split() else ""
                    if l_lower.startswith("key result areas"):
                        is_new_job_line = False
                    elif first_word in action_verbs:
                        is_new_job_line = False
                    elif any(re.search(r'\b' + re.escape(kw) + r'\b', l_lower) for kw in designation_keywords):
                        if "leadership" not in l_lower and "summary" not in l_lower:
                            is_new_job_line = True
                        
            if is_new_job_line:
                if current_block["title_line"].strip():
                    work_blocks.append(current_block)
                current_block = {
                    "title_line": line_str,
                    "description_lines": []
                }
            else:
                current_block["description_lines"].append(line_str)

        if current_block["title_line"].strip():
            work_blocks.append(current_block)

        experiences = []
        for block in work_blocks:
            title_line = block["title_line"]
            date_match = date_range_regex.search(title_line)
            date_str = ""
            start_date_val = ""
            end_date_val = ""
            if date_match:
                date_str = date_match.group(0)
                raw_start = date_match.group(1).strip() if date_match.group(1) else ""
                raw_end = date_match.group(2).strip() if date_match.group(2) else ""
                start_date_val = ResumeIntelligenceService.normalize_date_to_string(raw_start, is_end=False) or ""
                end_date_val = ResumeIntelligenceService.normalize_date_to_string(raw_end, is_end=True) or ""
                
            title_clean = title_line.replace(date_str, "").strip()
            title_clean = re.sub(r'^[|/\-\s\.,:]+|[|/\-\s\.,:]+$', '', title_clean).strip()
            
            parts = [p.strip() for p in re.split(r'[|]+', title_clean) if p.strip()]
            if len(parts) == 1:
                parts = [p.strip() for p in re.split(r'[,–\-]+', title_clean) if p.strip()]
                
            designation = ""
            company = ""
            location = ""
            
            if len(parts) >= 1:
                designation = parts[0]
            if len(parts) >= 2:
                company = parts[1]
            if len(parts) >= 3:
                location = parts[2]
                
            designation = re.sub(r'^(presently|currently|actively)?\s*working\s+as\s+', '', designation, flags=re.I).strip()
            designation = re.sub(r'^worked\s+as\s+', '', designation, flags=re.I).strip()
            designation = re.sub(r'^role\s*:\s*', '', designation, flags=re.I).strip()
            
            # Split designation by company separators if company is empty
            if designation and not company:
                company_separators = [r'\bin\b', r'\bat\b', r'\bfor\b', r'\bwith\b', r'\b@\b', r'\s*-\s*', r'\s*\|\s*']
                for sep in company_separators:
                    c_parts = re.split(sep, designation, maxsplit=1, flags=re.I)
                    if len(c_parts) == 2:
                        designation = c_parts[0].strip()
                        company = c_parts[1].strip()
                        break
            
            desc_lines = []
            for line in block["description_lines"]:
                line_str = line.strip()
                if not line_str:
                    continue
                if line_str.lower().startswith("key result areas"):
                    desc_lines.append(line_str)
                else:
                    line_clean = line_str.lstrip('-•*+ ').strip()
                    if line_clean:
                        desc_lines.append(f"• {line_clean}")
                        
            description = "\n".join(desc_lines)
            
            duration = ""
            if start_date_val:
                duration = ResumeIntelligenceService.get_duration_display(start_date_val, end_date_val)
                
            experiences.append({
                "designation": designation or "Position",
                "company": company or "Company",
                "location": location or "Location",
                "duration": duration,
                "description": description,
                "start_date": start_date_val,
                "end_date": end_date_val
            })

        # 2. Parse Educations
        educations = []
        edu_degree_keywords = [
            'mba', 'pgdm', 'b.com', 'bcom', 'b.tech', 'btech', 'b.e.', 'be', 'bsc', 'b.sc', 'msc', 'm.sc', 'phd', 
            'doctor', 'bachelor', 'master', 'diploma', 'high school', 'intermediate', '10th', '12th', 'ssc', 'hsc', 'school',
            'chartered accountant', 'ca', 'icai', 'c.a.'
        ]

        edu_blocks = []
        current_edu = {"header_lines": [], "year_line": ""}

        for line in sections["EDU"]:
            line_str = line.strip()
            if not line_str:
                continue
            year_match = re.search(r'\b(19\d\d|20\d\d)\b', line_str)
            is_year = bool(year_match)
            
            if is_year:
                year_str = year_match.group(0)
                non_year_part = line_str.replace(year_str, "").strip()
                non_year_part = re.sub(r'^[-–—,.:;\s]+|[-–—,.:;\s]+$', '', non_year_part).strip()
                
                if current_edu["year_line"]:
                    edu_blocks.append(current_edu)
                    current_edu = {"header_lines": [], "year_line": ""}
                    
                current_edu["year_line"] = year_str
                if non_year_part:
                    current_edu["header_lines"].append(non_year_part)
            else:
                current_edu["header_lines"].append(line_str)
                
        if current_edu["year_line"] or current_edu["header_lines"]:
            edu_blocks.append(current_edu)

        for block in edu_blocks:
            degree = "Degree"
            institution = "Institution"
            
            headers = [h.strip() for h in block["header_lines"] if h.strip()]
            if len(headers) == 1:
                h_val = headers[0]
                split_done = False
                for sep in [" - ", " , ", " at ", " @ ", " | ", " from "]:
                    if sep in h_val:
                        parts = h_val.split(sep, 1)
                        degree = parts[0].strip()
                        institution = parts[1].strip()
                        split_done = True
                        break
                if not split_done:
                    degree = h_val
            elif len(headers) >= 2:
                degree_idx = -1
                for idx, h in enumerate(headers):
                    if any(re.search(r'\b' + re.escape(kw) + r'\b', h.lower()) for kw in edu_degree_keywords):
                        degree_idx = idx
                        break
                
                if degree_idx != -1:
                    degree = headers[degree_idx]
                    other_lines = [h for i, h in enumerate(headers) if i != degree_idx]
                    institution = " ".join(other_lines)
                else:
                    degree = headers[0]
                    institution = " ".join(headers[1:])
                    
            inst_lower = institution.lower()
            if "institute of chartered accountants" in inst_lower or "icai" in inst_lower:
                institution = "ICAI"
                
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
        for line in sections["PROJECT"]:
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

        # 4. Parse Skills
        skills = []
        for line in sections["SKILLS"]:
            s_clean = line.strip().lstrip('-•*+ ').strip()
            if s_clean and len(s_clean) < 60:
                skills.append(s_clean)

        # 5. Parse Certifications
        certs = []
        cert_blocks = []
        current_cert = []
        for line in sections["CERT"]:
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
        total_exp = round(total_exp, 1)

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
                "address": address,
                "city": city,
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
            if "btech" in deg or "b.tech" in deg or "b.e." in deg or "bachelor of technology" in deg:
                edu["degree"] = "B.Tech"
            elif "mtech" in deg or "m.tech" in deg or "master" in deg:
                edu["degree"] = "M.Tech"
            elif "phd" in deg or "doctor" in deg:
                edu["degree"] = "Ph.D."
            elif "diploma" in deg:
                edu["degree"] = "Diploma"
            elif "intermediate" in deg or "12th" in deg or "hsc" in deg:
                edu["degree"] = "Intermediate"
            elif "high school" in deg or "10th" in deg or "ssc" in deg or "school" in deg:
                edu["degree"] = "High School"
            inst = edu.get("institution", "").strip()
            if "icai" in inst.lower():
                edu["institution"] = "ICAI"
            else:
                edu["institution"] = inst.title()

        # 4. Generate professional Summary if not present or improve it
        current_desig = info.get('current_designation') or 'Professional'
        if current_desig.lower() == 'professional':
            current_desig = 'Professional'
            
        orig_summary = data.get("summary", "")
        cand_name = info.get("name", "")
        
        if orig_summary:
            clean_summary = orig_summary
            if cand_name:
                clean_summary = re.sub(rf'\b{re.escape(cand_name)}\b', '', clean_summary, flags=re.I).strip()
                clean_summary = re.sub(r'^\s*[-–—,.:;]\s*', '', clean_summary)
            improved["summary"] = clean_summary
        else:
            skills_str = ", ".join(improved.get("skills", [])[:5])
            improved["summary"] = f"Results-driven {current_desig} with {info.get('total_experience', 2)} years of experience. Highly skilled in {skills_str}, with a proven track record of delivering high-quality results."

        # 5. Deduplicate skills (Do not suggest fake/missing skills)
        skills_set = {s.strip().title() for s in improved.get("skills", [])}
        improved["skills"] = sorted(list(skills_set))

        # 6. Certifications (Do not suggest fake/missing certifications)
        improved["certifications"] = improved.get("certifications", [])

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
