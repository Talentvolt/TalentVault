import re
import os
import zipfile
import io
import hashlib
import pdfplumber
import docx
import logging
from decimal import Decimal
from datetime import datetime
from django.core.files.base import ContentFile
from django.db.models import Q
from apps.accounts.models import User
from apps.candidates.models import (
    CandidateProfile, CandidateSkill, DuplicateResumeLog, 
    Experience, Education, Project, Certification
)

logger = logging.getLogger(__name__)

CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')

# Pre-compiled regular expressions for candidate name/info validation
NAME_CLEAN_RE = re.compile(r'^\+?\d[\d\s-]{8,}$')
DIGITS_ONLY_RE = re.compile(r'[^\d+]')
DIGITS_DIGIT_RE = re.compile(r'^\+?\d+$')
EMAIL_RE = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
URL_RE = re.compile(r'(https?://\S+|www\.\S+)', re.I)
STRIP_NON_ALPHA_RE = re.compile(r'[^a-z\s]')

_GLOBAL_SPACY_NLP = None

import threading
_thread_local_timings = threading.local()

def get_spacy_nlp():
    global _GLOBAL_SPACY_NLP
    if _GLOBAL_SPACY_NLP is None:
        try:
            import spacy
            _GLOBAL_SPACY_NLP = spacy.load("en_core_web_sm")
        except Exception as e:
            logger.warning(f"Failed to load spaCy model: {e}")
            _GLOBAL_SPACY_NLP = False
    return _GLOBAL_SPACY_NLP

def clean_extracted_text(text: str) -> str:
    if not text:
        return ""
    # Strip null bytes and non-printable control characters, preserving normal whitespace
    return "".join(c for c in text if c.isprintable() or c in "\n\r\t").strip()


def sanitize_text(value, path="", print_on_nul=True):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    
    if "\x00" in value:
        if print_on_nul:
            msg = f"Found NUL byte in: {path or 'unknown'}"
            print(msg)
            logger.warning(msg)
            
    # remove \x00
    value = value.replace("\x00", "")
    # remove control characters except \n and \t
    value = CONTROL_CHARS_RE.sub("", value)
    # strip whitespace
    return value.strip()

def sanitize_recursive(data, path=""):
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            current_path = f"{path}.{k}" if path else k
            sanitized[k] = sanitize_recursive(v, current_path)
        return sanitized
    elif isinstance(data, list):
        sanitized = []
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"
            sanitized.append(sanitize_recursive(item, current_path))
        return sanitized
    elif isinstance(data, str):
        return sanitize_text(data, path)
    elif data is None:
        if path and any(k in path for k in ["current_ctc", "expected_ctc", "date_of_birth", "gender"]):
            return None
        return ""
    elif isinstance(data, (bool, int, float)):
        return data
    else:
        return sanitize_text(data, path)

def parse_date_robust(date_str, default=None):
    if not date_str or not isinstance(date_str, str):
        return default
    date_str = date_str.strip()
    # Try various formats
    formats = ["%Y-%m-%d", "%Y-%m", "%Y", "%d-%m-%Y", "%d/%m/%Y", "%m/%Y", "%m-%Y", "%b %Y", "%B %Y", "%b-%Y", "%B-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    # Try extracting 4 digit year
    year_match = re.search(r'\b(19\d\d|20\d\d)\b', date_str)
    if year_match:
        try:
            return datetime.strptime(year_match.group(1), "%Y").date()
        except ValueError:
            pass
    return default


def extract_text_from_pdf(file_obj):
    text = ""
    try:
        with pdfplumber.open(file_obj) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"PDF parsing error: {e}")
    return text

def extract_text_from_docx(file_obj):
    text = ""
    try:
        doc = docx.Document(file_obj)
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        print(f"DOCX parsing error: {e}")
    return text

def parse_resume_text(text):
    data = {
        'name': '',
        'email': '',
        'phone': '',
        'skills': [],
        'summary': '',
        'current_company': '',
        'designation': '',
        'current_ctc': None,
        'expected_ctc': None,
        'notice_period': 30,
        'location': '',
        'experience_years': 0.0,
        'work_history': [],
        'education_history': [],
        'projects': [],
        'certifications': []
    }
    
    # Clean text
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Extract Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        data['email'] = email_match.group(0)
        
    # Extract Phone
    phone_match = re.search(r'(\+\d{1,3}[- ]?)?\d{10}', text)
    if phone_match:
        data['phone'] = phone_match.group(0)
        
    # Extract Name (heuristic: first line)
    if lines:
        data['name'] = lines[0]
        
    # Skills extraction (expanded list)
    skill_keywords = [
        'python', 'java', 'django', 'react', 'javascript', 'node', 'mern', 'aws', 'docker', 'kubernetes', 'sql', 
        'pharma', 'nurse', 'sales', 'hr', 'php', 'laravel', 'flutter', 'android', 'ios', 'data science', 'ml', 'ai'
    ]
    text_lower = text.lower()
    for skill in skill_keywords:
        if re.search(r'\b' + re.escape(skill) + r'\b', text_lower):
            data['skills'].append(skill)

    # Heuristics for CTC
    ctc_match = re.search(r'(Current CTC|CTC|Salary)[: ]+([\d.]+)', text, re.I)
    if ctc_match:
        try:
            data['current_ctc'] = float(ctc_match.group(2)) * 100000 
        except: pass

    ectc_match = re.search(r'(Expected CTC|ECTC)[: ]+([\d.]+)', text, re.I)
    if ectc_match:
        try:
            data['expected_ctc'] = float(ectc_match.group(2)) * 100000
        except: pass

    # Notice Period
    np_match = re.search(r'(Notice Period|NP)[: ]+(\d+)', text, re.I)
    if np_match:
        try:
            data['notice_period'] = int(np_match.group(2))
        except: pass

    # Experience Years
    exp_match = re.search(r'(\d+)\+?\s*Years?', text, re.I)
    if exp_match:
        data['experience_years'] = float(exp_match.group(1))

    # Location (expanded)
    locations = ['Delhi', 'Mumbai', 'Bangalore', 'Hyderabad', 'Pune', 'Noida', 'Gurgaon', 'Patna', 'Lucknow', 'Begusarai', 'Samastipur']
    for loc in locations:
        if loc.lower() in text_lower:
            data['location'] = loc
            break
            
    # Very basic section detection for work, education, etc.
    # We'll just take the next few lines for now as a mock implementation of deeper parsing
    current_section = None
    for line in lines:
        l = line.lower()
        if 'experience' in l or 'work history' in l:
            current_section = 'WORK'
            continue
        if 'education' in l or 'academic' in l:
            current_section = 'EDU'
            continue
        if 'project' in l:
            current_section = 'PROJECT'
            continue
        if 'certification' in l:
            current_section = 'CERT'
            continue
            
        if current_section == 'WORK' and len(data['work_history']) < 3:
            data['work_history'].append(line)
        elif current_section == 'EDU' and len(data['education_history']) < 2:
            data['education_history'].append(line)
        elif current_section == 'PROJECT' and len(data['projects']) < 3:
            data['projects'].append(line)
        elif current_section == 'CERT' and len(data['certifications']) < 3:
            data['certifications'].append(line)

    data['summary'] = text[:500]
    return data

def _flatten_field(field_data):
    if isinstance(field_data, dict) and "value" in field_data:
        return field_data["value"]
    return field_data


def parse_education_date_to_date_obj(date_val):
    if not date_val:
        return None
    date_str = str(date_val).strip()
    if not date_str:
        return None
        
    import re
    from datetime import datetime
    
    # 1. Try common full/partial date formats via datetime.strptime
    formats = [
        "%Y-%m-%d", "%Y-%m", "%m/%Y", "%m-%Y", 
        "%b %Y", "%B %Y", "%b-%Y", "%B-%Y", "%Y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # 2. Extract year (4 digits) and search for month name/number
    year_match = re.search(r'\b(19\d\d|20\d\d)\b', date_str)
    if not year_match:
        return None
    year = int(year_match.group(1))
    
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    date_str_lower = date_str.lower()
    found_month = None
    for m_name, m_num in months.items():
        if m_name in date_str_lower:
            if not found_month or len(m_name) > len(found_month[0]):
                found_month = (m_name, m_num)
                
    if found_month:
        try:
            return datetime(year, found_month[1], 1).date()
        except Exception:
            pass
            
    m1 = re.search(r'\b(0[1-9]|1[0-2]|[1-9])\s*[\-/]\s*(19\d\d|20\d\d)\b', date_str)
    if m1:
        try:
            return datetime(int(m1.group(2)), int(m1.group(1)), 1).date()
        except Exception:
            pass
            
    m2 = re.search(r'\b(19\d\d|20\d\d)\s*[\-/]\s*(0[1-9]|1[0-2]|[1-9])\b', date_str)
    if m2:
        try:
            return datetime(int(m2.group(1)), int(m2.group(2)), 1).date()
        except Exception:
            pass

    try:
        return datetime(year, 1, 1).date()
    except Exception:
        return None


def parse_education_date_to_string(date_val) -> str:
    date_obj = parse_education_date_to_date_obj(date_val)
    if date_obj:
        return date_obj.strftime("%Y-%m-%d")
    return ""


def normalize_skills(skills_list):
    if not skills_list:
        return []
    normalized = []
    seen = set()
    normalization_map = {
        'python': 'Python',
        'django': 'Django',
        'react': 'React',
        'javascript': 'JavaScript',
        'node': 'Node.js',
        'node.js': 'Node.js',
        'aws': 'AWS',
        'docker': 'Docker',
        'kubernetes': 'Kubernetes',
        'sql': 'SQL',
        'mysql': 'MySQL',
        'postgresql': 'PostgreSQL',
        'mongodb': 'MongoDB',
        'html': 'HTML',
        'css': 'CSS',
        'git': 'Git',
        'java': 'Java',
        'php': 'PHP',
        'typescript': 'TypeScript',
        'c++': 'C++',
        'c#': 'C#',
        'ruby': 'Ruby',
        'rails': 'Ruby on Rails',
        'flutter': 'Flutter',
        'android': 'Android',
        'ios': 'iOS'
    }
    for s in skills_list:
        if not s or not isinstance(s, str):
            continue
        s_clean = s.strip()
        if not s_clean:
            continue
        s_lower = s_clean.lower()
        normalized_name = normalization_map.get(s_lower, s_clean.title())
        if normalized_name.lower() not in seen:
            normalized.append(normalized_name)
            seen.add(normalized_name.lower())
    return normalized


def parse_experience_years(text_val):
    if not text_val:
        return 0.0
    text_val = str(text_val).lower().strip()
    years = 0.0
    months = 0.0
    
    years_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:yr|year|yrs|years)', text_val)
    if years_match:
        years = float(years_match.group(1))
        
    months_match = re.search(r'(\d+)\s*(?:month|months|mth|mths)', text_val)
    if months_match:
        months = float(months_match.group(1))
        
    if years > 0 or months > 0:
        return round(years + (months / 12.0), 2)
        
    digit_match = re.search(r'^(\d+(?:\.\d+)?)$', text_val)
    if digit_match:
        return round(float(digit_match.group(1)), 2)
        
    return 0.0


def convert_llm_data_to_standard_format(llm_data):
    f = _flatten_field
    
    # 1. Experiences
    experiences = []
    work_exp = llm_data.get("work_experience", {})
    if work_exp and isinstance(work_exp.get("value"), list):
        for item in work_exp["value"]:
            s_date = f(item.get("start_date"))
            e_date = f(item.get("end_date"))
            experiences.append({
                "designation": (f(item.get("designation")) or "")[:100],
                "company": (f(item.get("company")) or "")[:100],
                "location": (f(item.get("location")) or "")[:100],
                "duration": "",
                "description": f(item.get("description")) or "",
                "start_date": s_date or "",
                "end_date": e_date or ""
            })
            
    # Calculate duration and years of experience
    from services.resume_intelligence import ResumeIntelligenceService
    total_exp = 0.0
    for exp in experiences:
        s_date_str = ResumeIntelligenceService.normalize_date_to_string(exp["start_date"], is_end=False)
        e_date_str = ResumeIntelligenceService.normalize_date_to_string(exp["end_date"], is_end=True)
        if s_date_str:
            exp["start_date"] = s_date_str
            exp["end_date"] = e_date_str or "Present"
            exp["duration"] = ResumeIntelligenceService.get_duration_display(s_date_str, e_date_str)
            total_exp += ResumeIntelligenceService.calculate_experience_years_from_dates(s_date_str, e_date_str)
    total_exp = round(total_exp, 1)

    # 2. Educations
    educations = []
    education = llm_data.get("education", {})
    if education and isinstance(education.get("value"), list):
        for item in education["value"]:
            s_year = f(item.get("start_year"))
            e_year = f(item.get("end_year"))
            
            # If only one completion year exists, store it as end_date
            if s_year and not e_year:
                e_year = s_year
                s_year = ""
                
            educations.append({
                "degree": (f(item.get("degree")) or "")[:100],
                "institution": (f(item.get("college")) or f(item.get("university")) or "")[:100],
                "field_of_study": (f(item.get("branch")) or "General")[:100],
                "score": (f(item.get("cgpa")) or f(item.get("percentage")) or "N/A")[:20],
                "start_date": parse_education_date_to_string(s_year),
                "end_date": parse_education_date_to_string(e_year)
            })

    # 3. Skills (normalized and merged)
    tech_skills = f(llm_data.get("technical_skills")) or []
    soft_skills = f(llm_data.get("soft_skills")) or []
    skills = normalize_skills(tech_skills + soft_skills)

    # 4. Projects
    projects = []
    projects_data = llm_data.get("projects", {})
    if projects_data and isinstance(projects_data.get("value"), list):
        for item in projects_data["value"]:
            projects.append({
                "title": (f(item.get("title")) or "")[:255],
                "description": f(item.get("description")) or "",
                "link": (f(item.get("link")) or "")[:255]
            })

    # 5. Certifications
    certifications = []
    cert_data = llm_data.get("certifications", {})
    if cert_data and isinstance(cert_data.get("value"), list):
        for item in cert_data["value"]:
            certifications.append({
                "name": (f(item.get("name")) or "")[:255],
                "issuing_organization": (f(item.get("issuing_organization")) or "")[:255],
                "issue_date": f(item.get("issue_date")) or ""
            })

    # 6. Personal Info
    raw_phone = f(llm_data.get("phone")) or ""
    phone_digits = re.sub(r'\D', '', raw_phone)
    phone_clean = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits
    if not phone_clean:
        phone_match = re.search(r'(?:\+?\d{1,3}[- ]?)?(?:\d[- ]?){9}\d', raw_phone)
        if phone_match:
            phone_clean = re.sub(r'\D', '', phone_match.group(0))[-10:]

    raw_email = f(llm_data.get("email")) or ""
    email_clean = raw_email.strip()[:254]

    raw_name = f(llm_data.get("full_name")) or f(llm_data.get("name")) or f(llm_data.get("candidate_name")) or "Unknown Candidate"
    name_clean = raw_name.strip()[:255]

    raw_linkedin = f(llm_data.get("linkedin")) or ""
    linkedin_clean = raw_linkedin.strip()[:200]

    raw_portfolio = f(llm_data.get("portfolio")) or ""
    portfolio_clean = raw_portfolio.strip()[:200]

    # Clean and parse CTCs, Notice Period, DOB, Gender
    def clean_ctc(val):
        if not val:
            return None
        val_str = str(val).lower()
        matches = re.findall(r'[\d\.]+', val_str)
        if not matches:
            return None
        num = float(matches[0])
        if 'lpa' in val_str or 'lakh' in val_str or num < 100.0:
            return num * 100000
        return num

    def clean_notice_period(val):
        if not val:
            return 30
        val_str = str(val).lower()
        matches = re.findall(r'\d+', val_str)
        if not matches:
            return 30
        return int(matches[0])

    current_ctc_val = clean_ctc(f(llm_data.get("current_ctc")))
    expected_ctc_val = clean_ctc(f(llm_data.get("expected_ctc")))
    notice_period_val = clean_notice_period(f(llm_data.get("notice_period")))
    dob_val = f(llm_data.get("date_of_birth")) or f(llm_data.get("dob"))
    gender_val = f(llm_data.get("gender"))

    personal_info = {
        "name": name_clean,
        "email": email_clean,
        "phone": phone_clean,
        "location": (f(llm_data.get("address")) or f(llm_data.get("city")) or "Unknown")[:255],
        "address": (f(llm_data.get("address")) or "")[:255],
        "city": (f(llm_data.get("city")) or "")[:255],
        "linkedin_url": linkedin_clean,
        "portfolio_url": portfolio_clean,
        "current_company": (experiences[0]["company"] if experiences else "")[:255],
        "current_designation": (experiences[0]["designation"] if experiences else "Professional")[:255],
        "total_experience": total_exp,
        "current_ctc": current_ctc_val,
        "expected_ctc": expected_ctc_val,
        "notice_period": notice_period_val,
        "date_of_birth": dob_val,
        "gender": gender_val
    }

    return {
        "personal_info": personal_info,
        "summary": f(llm_data.get("professional_summary")) or "",
        "skills": skills,
        "education": educations,
        "experience": experiences,
        "projects": projects,
        "certifications": certifications,
        "achievements": f(llm_data.get("achievements")) or [],
        "languages": f(llm_data.get("languages")) or [],
        "current_ctc": current_ctc_val,
        "expected_ctc": expected_ctc_val,
        "notice_period": notice_period_val,
        "date_of_birth": dob_val,
        "gender": gender_val,
        "metadata": {
            "parsed_by": "OpenAIResumeParser",
            "parsed_at": datetime.now().isoformat()
        }
    }

from typing import List, Optional
from pydantic import BaseModel, Field

class FastExperienceItem(BaseModel):
    company: Optional[str] = Field(None, description="Company name")
    designation: Optional[str] = Field(None, description="Job designation / title")
    location: Optional[str] = Field(None, description="Work location")
    employment_type: Optional[str] = Field(None, description="Full-time, part-time, etc.")
    start_date: Optional[str] = Field(None, description="Start date of employment")
    end_date: Optional[str] = Field(None, description="End date or Present")
    description: Optional[str] = Field(None, description="Key duties and accomplishments")

class FastExperience(BaseModel):
    value: List[FastExperienceItem] = Field(default_factory=list)

class FastEducationItem(BaseModel):
    degree: Optional[str] = Field(None, description="Name of degree")
    branch: Optional[str] = Field(None, description="Branch of study")
    college: Optional[str] = Field(None, description="College name")
    board: Optional[str] = Field(None, description="Board name")
    university: Optional[str] = Field(None, description="University name")
    start_year: Optional[str] = Field(None, description="Start year")
    end_year: Optional[str] = Field(None, description="End year")
    cgpa: Optional[str] = Field(None, description="CGPA")
    percentage: Optional[str] = Field(None, description="Percentage")
    grade: Optional[str] = Field(None, description="Grade")

class FastEducation(BaseModel):
    value: List[FastEducationItem] = Field(default_factory=list)

class FastProjectItem(BaseModel):
    title: Optional[str] = Field(None, description="Project title")
    description: Optional[str] = Field(None, description="Project description")
    technologies: Optional[str] = Field(None, description="Technologies used")
    duration: Optional[str] = Field(None, description="Duration")

class FastProject(BaseModel):
    value: List[FastProjectItem] = Field(default_factory=list)

class FastCertificationItem(BaseModel):
    name: Optional[str] = Field(None, description="Certification name")
    issuing_organization: Optional[str] = Field(None, description="Issuing organization")
    issue_date: Optional[str] = Field(None, description="Issue date")

class FastCertification(BaseModel):
    value: List[FastCertificationItem] = Field(default_factory=list)

class FastResumeSchema(BaseModel):
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    current_designation: Optional[str] = None
    current_company: Optional[str] = None
    professional_summary: Optional[str] = None
    work_experience: FastExperience = Field(default_factory=FastExperience)
    education: FastEducation = Field(default_factory=FastEducation)
    projects: FastProject = Field(default_factory=FastProject)
    technical_skills: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    certifications: FastCertification = Field(default_factory=FastCertification)
    awards: List[str] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    training: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    expected_ctc: Optional[str] = Field(None, description="Expected CTC / salary")
    current_ctc: Optional[str] = Field(None, description="Current CTC / salary")
    notice_period: Optional[str] = Field(None, description="Notice period in days or months")
    date_of_birth: Optional[str] = Field(None, description="Date of birth")
    gender: Optional[str] = Field(None, description="Gender")

class OpenAIResumeParser:
    @staticmethod
    def parse(text: str) -> dict:
        import os
        import time
        from openai import OpenAI
        from django.conf import settings
        
        api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API Key is not configured.")
        
        model_name = getattr(settings, "OPENAI_MODEL_NAME", "gpt-4.1-mini")
        client = OpenAI(api_key=api_key)
        
        system_content = (
            "You are a professional resume parsing assistant.\n"
            "Your critical objective is to extract 100% of the resume content without any summarization, omission, or simplification.\n"
            "- Extract EVERY work experience, education item, project, skill, and certification listed, preserving their original order exactly.\n"
            "- For work experience and projects descriptions (responsibilities): Do NOT merge separate bullet points, sentences, or responsibilities into one long paragraph.\n"
            "- Do NOT summarize or condense responsibilities. Convert each responsibility or action item into its own separate line starting with a bullet point character '• '.\n"
            "- If the resume already has bullets, keep them as separate lines. Each bullet item must be preserved with its exact wording.\n"
            "- Never combine multiple distinct bullet points or achievements into a single sentence or line."
        )
        
        t0 = time.time()
        completion = client.beta.chat.completions.parse(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": system_content
                },
                {"role": "user", "content": text}
            ],
            response_format=FastResumeSchema
        )
        openai_duration = time.time() - t0
        logger.info(f"[TIMING] OpenAI API call took: {openai_duration:.4f}s")
        print(f"[TIMING] OpenAI API call took: {openai_duration:.4f}s")
        
        t_val = time.time()
        llm_raw_data = completion.choices[0].message.parsed.model_dump()
        result = convert_llm_data_to_standard_format(llm_raw_data)
        validation_duration = time.time() - t_val
        logger.info(f"[TIMING] JSON validation & conversion took: {validation_duration:.4f}s")
        print(f"[TIMING] JSON validation & conversion took: {validation_duration:.4f}s")
        
        if hasattr(_thread_local_timings, "timings"):
            _thread_local_timings.timings["openai"] = openai_duration
            _thread_local_timings.timings["validation"] = validation_duration
            
        return result

def copy_storage_file(source_field, target_path):
    """
    Copies a file within the same storage backend (local filesystem or S3)
    to avoid re-uploading the same bytes over the network.
    """
    import os
    import shutil
    import logging
    logger = logging.getLogger(__name__)
    
    storage = source_field.storage
    source_name = source_field.name
    
    # 1. Try S3 server-side copy if S3Storage is used
    if hasattr(storage, 'bucket_name') and hasattr(storage, 'connection'):
        try:
            s3_client = storage.connection.meta.client
            bucket_name = storage.bucket_name
            copy_source = {'Bucket': bucket_name, 'Key': source_name}
            s3_client.copy(copy_source, bucket_name, target_path)
            logger.info(f"[S3 COPY SUCCESS] Copied {source_name} to {target_path} server-side.")
            print(f"[S3 COPY SUCCESS] Copied {source_name} to {target_path} server-side.")
            return True
        except Exception as e:
            logger.error(f"[S3 COPY ERROR] Failed S3 copy from {source_name} to {target_path}: {e}")
            print(f"[S3 COPY ERROR] Failed S3 copy from {source_name} to {target_path}: {e}")

    # 2. Try local filesystem copy
    try:
        source_path = storage.path(source_name)
        target_abs_path = storage.path(target_path)
        os.makedirs(os.path.dirname(target_abs_path), exist_ok=True)
        shutil.copy2(source_path, target_abs_path)
        logger.info(f"[LOCAL COPY SUCCESS] Copied {source_path} to {target_abs_path} locally.")
        print(f"[LOCAL COPY SUCCESS] Copied {source_path} to {target_abs_path} locally.")
        return True
    except Exception as e:
        logger.error(f"[LOCAL COPY ERROR] Failed local copy from {source_name} to {target_path}: {e}")
        print(f"[LOCAL COPY ERROR] Failed local copy from {source_name} to {target_path}: {e}")

    return False

def process_resume_file(file_obj, filename, overwrite=False, progress_callback=None, security_data=None, user=None):
    import time
    t_process_start = time.time()
    
    filename = sanitize_text(filename, "filename")
    
    # Support only PDF, DOC, DOCX, RTF, TXT
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    if ext not in ['pdf', 'doc', 'docx', 'rtf', 'txt']:
        logger.error(f"[PARSER ERROR] Invalid format uploaded: {filename}")
        return None, "INVALID_FORMAT"
        
    try:
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        file_bytes = file_obj.read()
        logger.info(f"[PARSER START] Uploaded resume: {filename}, size: {len(file_bytes)} bytes")
    except Exception as e:
        logger.error(f"[PARSER READ ERROR] Error reading file bytes for {filename}: {str(e)}", exc_info=True)
        return None, "READ_ERROR"

    # Enforce security validation if not already done
    if security_data is None:
        from utils.security import perform_all_security_validations
        try:
            security_data = perform_all_security_validations(file_bytes, filename)
        except Exception as e:
            logger.error(f"[PARSER SECURITY REJECT] File {filename} failed security check: {str(e)}")
            return None, "SECURITY_FAILED"

    from services.resume_intelligence import ResumeIntelligenceService
    
    sha256 = security_data.get('sha256') if security_data else hashlib.sha256(file_bytes).hexdigest()
    existing_profile = CandidateProfile.objects.filter(sha256=sha256).first()
    
    cached_duplicate = False
    t_ocr = 0.0
    t_openai = 0.0
    t_validation = 0.0
    
    if existing_profile and existing_profile.raw_resume_text and not overwrite:
        logger.info(f"[PARSER DEDUPLICATION] Reusing cached OCR & LLM parse for exact duplicate file: {filename}")
        print(f"[PARSER DEDUPLICATION] Reusing cached OCR & LLM parse for exact duplicate file: {filename}")
        text = existing_profile.raw_resume_text
        parsed_data = existing_profile.parsed_json
        ocr_result = {
            "text": text,
            "engine": existing_profile.ocr_engine,
            "confidence": float(existing_profile.ocr_confidence),
            "resume_type": existing_profile.resume_type,
            "largest_bold_name": existing_profile.full_name
        }
        cached_duplicate = True
    
    if not cached_duplicate:
        # 1. OCR Engine Execution / Text Extraction
        t_ocr_start = time.time()
        try:
            logger.info(f"[PARSER OCR RUNNING] Running OCR pipeline for: {filename}")
            if progress_callback:
                progress_callback("reading_pdf")
                progress_callback("extracting_text")
            ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, filename)
            text = ocr_result["text"]
            logger.info(f"[PARSER OCR SUCCESS] Engine: {ocr_result['engine']}, Confidence: {ocr_result['confidence']}%")
        except Exception as e:
            logger.error(f"[PARSER OCR FAILURE] Failed during OCR pipeline on {filename}: {str(e)}", exc_info=True)
            return None, "OCR_FAILED"
        t_ocr = time.time() - t_ocr_start
        logger.info(f"[TIMING] Text Extraction/OCR Pipeline took: {t_ocr:.4f}s")
        print(f"[TIMING] Text Extraction/OCR Pipeline took: {t_ocr:.4f}s")
        
        # 2. Run OpenAI parser and profile photo extraction in parallel!
        t_parallel_start = time.time()
        import concurrent.futures
        
        parsed_data = None
        photo_bytes = None
        photo_ext = None
        openai_duration = 0.0
        validation_duration = 0.0
        
        def run_openai_parser():
            nonlocal openai_duration, validation_duration
            try:
                logger.info(f"[PARSER LLM RUNNING] Attempting OpenAI parsing for: {filename}")
                if progress_callback:
                    progress_callback("ai_parsing")
                clean_text = clean_extracted_text(text)
                _thread_local_timings.timings = {"openai": 0.0, "validation": 0.0}
                res = OpenAIResumeParser.parse(clean_text)
                openai_duration = _thread_local_timings.timings.get("openai", 0.0)
                validation_duration = _thread_local_timings.timings.get("validation", 0.0)
                return res
            except Exception as e:
                logger.error(f"[PARSER LLM FAILURE] OpenAI parsing failed, falling back to NLP parser: {str(e)}", exc_info=True)
                return None

        def run_photo_extraction():
            try:
                return extract_profile_photo(file_bytes, filename)
            except Exception as e:
                logger.error(f"[PARSER PHOTO FAILURE] Photo extraction failed: {str(e)}", exc_info=True)
                return None, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_openai = executor.submit(run_openai_parser)
            future_photo = executor.submit(run_photo_extraction)
            
            parsed_data = future_openai.result()
            photo_bytes, photo_ext = future_photo.result()
            
        t_parallel = time.time() - t_parallel_start
        logger.info(f"[TIMING] Parallel OpenAI parsing & Photo extraction took: {t_parallel:.4f}s")
        print(f"[TIMING] Parallel OpenAI parsing & Photo extraction took: {t_parallel:.4f}s")
        
        t_openai = openai_duration
        t_validation = validation_duration

        if parsed_data is None:
            try:
                logger.info(f"[PARSER NLP RUNNING] Extracting data from OCR text length: {len(text)}")
                t_val_start = time.time()
                parsed_data = ResumeIntelligenceService.parse_resume_nlp(text, parsed_name=ocr_result.get("largest_bold_name"))
                t_validation += time.time() - t_val_start
                logger.info("[PARSER NLP SUCCESS] parse_resume_nlp completed")
            except Exception as e:
                logger.error(f"[PARSER NLP FAILURE] parse_resume_nlp raised an exception: {str(e)}", exc_info=True)

        # ai_improve step (only if NLP succeeded; still guarded individually)
        if parsed_data is not None:
            try:
                t_improve_start = time.time()
                parsed_data = ResumeIntelligenceService.ai_improve_resume_data(parsed_data)
                info = parsed_data['personal_info']
                t_validation += time.time() - t_improve_start
                logger.info(f"[TIMING] AI improve took: {time.time() - t_improve_start:.4f}s")
            except Exception as e:
                logger.error(f"[PARSER AI_IMPROVE FAILURE] ai_improve_resume_data raised: {str(e)}", exc_info=True)
                info = parsed_data.get('personal_info', {})
    else:
        # If it was duplicate, we still need to run photo extraction
        try:
            photo_bytes, photo_ext = extract_profile_photo(file_bytes, filename)
        except Exception as e:
            logger.error(f"[PARSER PHOTO FAILURE] Photo extraction failed: {str(e)}", exc_info=True)
            photo_bytes, photo_ext = None, None

    # Fallback: build a minimal parsed_data from raw OCR text so upload still succeeds
    if parsed_data is None:
        logger.warning("[PARSER FALLBACK] Building minimal parsed_data from raw OCR text")
        import re as _re
        _email_m = _re.search(r'[\w\.\-]+@[\w\.\-]+\.\w+', text)
        _phone_m = _re.search(r'(?:\+?\d{1,3}[- ]?)?(?:\d[- ]?){9}\d', text)
        _email_fb = _email_m.group(0) if _email_m else ""
        _phone_fb = _re.sub(r'[\s-]', '', _phone_m.group(0))[-10:] if _phone_m else ""
        _name_fb = ocr_result.get("largest_bold_name") or ""
        if not _name_fb:
            for _ln in text.split('\n'):
                _ln = _ln.strip()
                if _ln and '@' not in _ln and not _re.search(r'\d{5,}', _ln) and len(_ln.split()) <= 5:
                    _name_fb = _ln.title()
                    break
        parsed_data = {
            "personal_info": {
                "name": _name_fb,
                "email": _email_fb,
                "phone": _phone_fb,
                "location": "",
                "linkedin_url": "",
                "portfolio_url": "",
                "current_company": "",
                "current_designation": "",
                "total_experience": 0,
            },
            "summary": "",
            "experience": [],
            "education": [],
            "skills": [],
            "projects": [],
            "certifications": [],
            "achievements": [],
            "languages": [],
            "metadata": {"parsed_at": "", "word_count": len(text.split()), "fallback": True},
        }
        info = parsed_data['personal_info']
        logger.warning(f"[PARSER FALLBACK] Minimal data built for name={_name_fb!r} email={_email_fb!r}")
    
    parsed_data = sanitize_recursive(parsed_data, "parsed_data")
    text = sanitize_text(text, "raw_resume_text")
    info = parsed_data.get('personal_info', {})
    
    email = info.get('email', '')
    phone = info.get('phone', '')
    
    # Normalize placeholders
    if email == "candidate@example.com":
        email = ""
    if phone == "9876543210":
        phone = ""
        
    if not email:
        email = f"unknown_{abs(hash(text or filename))}@example.com"

    logger.info(f"[PARSER CONTACTS] Extracted Email: {email}, Extracted Phone: {phone}")
    print(f"[PARSER CONTACTS] Extracted Email: {email}, Extracted Phone: {phone}")
        
    try:
        from django.db import transaction
        t_db_start = time.time()
        with transaction.atomic():
            if progress_callback:
                progress_callback("saving_candidate")
            # Check for duplicates (Exact: email, phone, LinkedIn URL, or sha256 hash)
            t_user_start = time.time()
            linkedin = info.get('linkedin_url', '') or info.get('linkedin', '')
            sha256 = security_data.get('sha256', '') if security_data else ''
            
            existing_user = user
            if not existing_user:
                if email:
                    existing_user = User.objects.filter(email=email).first()
                if not existing_user and phone:
                    existing_user = User.objects.filter(phone_number=phone).first()
                if not existing_user and linkedin:
                    existing_profile = CandidateProfile.objects.filter(linkedin_url=linkedin).first()
                    if existing_profile:
                        existing_user = existing_profile.user
                if not existing_user and sha256:
                    existing_profile = CandidateProfile.objects.filter(sha256=sha256).first()
                    if existing_profile:
                        existing_user = existing_profile.user
            
            if existing_user and not overwrite and user is None:
                DuplicateResumeLog.objects.create(
                    email=email,
                    phone=phone,
                    filename=filename,
                    action_taken='SKIPPED'
                )
                existing_profile = getattr(existing_user, 'candidate_profile', None)
                return existing_profile, "DUPLICATE"
                
            if existing_user and overwrite:
                user = existing_user
                if phone: 
                    user.phone_number = phone
                user.save()
                DuplicateResumeLog.objects.create(
                    email=email,
                    phone=phone,
                    filename=filename,
                    action_taken='UPDATED'
                )
                logger.info(f"[PARSER DUPLICATE] Candidate already exists (overwriting): {email}")
                print(f"[PARSER DUPLICATE] Candidate already exists (overwriting): {email}")
            else:
                user, created_user = User.objects.get_or_create(
                    email=email,
                    defaults={'role': User.Role.CANDIDATE, 'phone_number': phone if phone else None}
                )
                if created_user:
                    user.set_unusable_password()
                    user.save()
                logger.info(f"[PARSER DB USER] User record {'created' if created_user else 'retrieved'}: {user.email}")
                print(f"[PARSER DB USER] User record {'created' if created_user else 'retrieved'}: {user.email}")
            t_user = time.time() - t_user_start
            logger.info(f"[TIMING] User DB lookup/create took: {t_user:.4f}s")
                
            t_profile_start = time.time()
            profile, created_profile = CandidateProfile.objects.get_or_create(user=user)
            
            def get_priority_name():
                def is_acceptable_name(name_str):
                    if not name_str or not isinstance(name_str, str):
                        return False
                    name_str = name_str.strip()
                    if not name_str:
                        return False
                    if name_str.lower() in ("unknown candidate", "unknown", "placeholder", "candidate", "null", "none"):
                        return False
                    
                    name_clean = " ".join(name_str.strip().split())
                    if not name_clean:
                        return False
                    if name_clean.isdigit():
                        return False
                    if NAME_CLEAN_RE.match(name_clean):
                        return False
                    if '@' in name_clean:
                        return False
                    if name_clean.lower().startswith('http'):
                        return False
                    if 'linkedin' in name_clean.lower() or 'github' in name_clean.lower():
                        return False
                        
                    digits_only = DIGITS_ONLY_RE.sub('', name_clean)
                    if len(digits_only) >= 8 and DIGITS_DIGIT_RE.match(digits_only.replace('+', '')):
                        return False
                        
                    if EMAIL_RE.search(name_clean):
                        return False
                    if URL_RE.search(name_clean):
                        return False
                        
                    if not any(char.isalpha() for char in name_clean):
                        return False
                        
                    norm = STRIP_NON_ALPHA_RE.sub('', name_clean.lower()).strip()
                    norm = " ".join(norm.split())
                    
                    SECTION_TITLES = {
                        "objective", "summary", "professional summary", "profile", "education",
                        "experience", "work experience", "projects", "technical skills", "skills",
                        "certifications", "achievements", "awards", "languages", "personal details",
                        "interests", "hobbies", "extracurricular activities", "volunteer work",
                        "declaration", "references", "career objective", "academic qualification"
                    }
                    if norm in SECTION_TITLES:
                        return False
                        
                    common_headings = {
                        'curriculum vitae', 'curriculum', 'vitae', 'resume', 'cv', 'biodata', 'page', 'email', 'phone', 'contact', 'mobile'
                    }
                    if norm in common_headings:
                        return False
                        
                    words = name_clean.lower().split()
                    blacklisted_words = {
                        'manager', 'developer', 'executive', 'engineer', 'lead', 'associate', 'specialist', 'director', 
                        'analyst', 'consultant', 'officer', 'administrator', 'coordinator', 'technician', 'representative', 
                        'intern', 'programmer', 'architect', 'head', 'founder', 'co-founder', 'ceo', 'cto', 'supervisor',
                        'leader', 'operator', 'agent', 'strategist', 'advisor', 'expert', 'auditor', 'salesperson',
                        'ltd', 'limited', 'pvt', 'private', 'llp', 'llc', 'inc', 'company', 'corporation', 'technologies',
                        'solutions', 'industries', 'group', 'corp', 'hospital', 'university', 'college', 'institute',
                        'school', 'bank', 'unknown', 'hometown', 'residence', 'nationality', 'gender', 'about', 'hr',
                        'recruiter', 'team', 'page', 'phone', 'email', 'address', 'contact', 'mobile', 'cv', 'resume',
                        'biodata', 'curriculum', 'vitae'
                    }
                    if any(w in blacklisted_words for w in words):
                        return False
                        
                    if ' ' not in name_clean and len(name_clean) > 12:
                        return False
                        
                    if not (1 <= len(words) <= 5):
                        return False
                        
                    return True

                # 1. OpenAI Name
                openai_name = None
                for k in ["full_name", "name", "candidate_name"]:
                    val = parsed_data.get(k)
                    if isinstance(val, dict) and "value" in val:
                        val = val["value"]
                    if is_acceptable_name(val):
                        openai_name = val.strip()
                        break
                
                if not openai_name:
                    personal = parsed_data.get("personal_info", {})
                    if isinstance(personal, dict):
                        for k in ["full_name", "name", "candidate_name"]:
                            val = personal.get(k)
                            if isinstance(val, dict) and "value" in val:
                                val = val["value"]
                            if is_acceptable_name(val):
                                openai_name = val.strip()
                                break
                
                logger.info(f"[NAME] OpenAI Name: {openai_name or 'None'}")
                print(f"[NAME] OpenAI Name: {openai_name or 'None'}")
                if openai_name:
                    return openai_name

                # 2. spaCy / NER Name
                spacy_name = None
                try:
                    nlp = get_spacy_nlp()
                    if nlp:
                        page_1 = text.split('\x0c')[0] if '\x0c' in text else text
                        lines = [line.strip() for line in page_1.split('\n') if line.strip()]
                        search_text = "\n".join(lines[:15])
                        doc = nlp(search_text)
                        for ent in doc.ents:
                            if ent.label_ == "PERSON":
                                ent_text = " ".join(ent.text.strip().split())
                                if is_acceptable_name(ent_text):
                                    spacy_name = ent_text.title()
                                    break
                except Exception as e:
                    logger.warning(f"spaCy PERSON extraction failed: {e}")
                
                logger.info(f"[NAME] spaCy Name: {spacy_name or 'None'}")
                print(f"[NAME] spaCy Name: {spacy_name or 'None'}")
                if spacy_name:
                    return spacy_name

                # 3. Resume Heading Name
                heading_name = None
                largest_heading = ocr_result.get("largest_bold_name")
                if is_acceptable_name(largest_heading):
                    heading_name = largest_heading.strip().title()
                
                logger.info(f"[NAME] Resume Heading: {heading_name or 'None'}")
                print(f"[NAME] Resume Heading: {heading_name or 'None'}")
                if heading_name:
                    return heading_name

                # 4. Largest Font OCR Name
                largest_font_name = None
                try:
                    # Collect lines from page 1 data if available
                    import fitz
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    if len(doc) > 0:
                        first_page = doc[0]
                        blocks_dict = first_page.get_text("dict")
                        spans_info = []
                        for b in blocks_dict.get("blocks", []):
                            if b.get("type") == 0:  # text block
                                for line in b.get("lines", []):
                                    spans = line.get("spans", [])
                                    if spans:
                                        line_text = "".join([s.get("text", "") for s in spans]).strip()
                                        line_text = " ".join(line_text.split())
                                        if line_text and is_acceptable_name(line_text):
                                            max_size = max(s.get("size", 0.0) for s in spans)
                                            spans_info.append((line_text, max_size))
                        if spans_info:
                            spans_info.sort(key=lambda x: x[1], reverse=True)
                            largest_font_name = spans_info[0][0].strip().title()
                except Exception as e:
                    logger.warning(f"Largest font OCR extraction failed: {e}")
                
                logger.info(f"[NAME] Largest Font OCR Name: {largest_font_name or 'None'}")
                print(f"[NAME] Largest Font OCR Name: {largest_font_name or 'None'}")
                if largest_font_name:
                    return largest_font_name

                # 5. Email Fallback
                email_name = None
                if email and '@' in email:
                    username = email.split('@')[0]
                    if username:
                        import re
                        username_no_digits = re.sub(r'\d+', '', username)
                        
                        lowered = username_no_digits.lower()
                        prefix_removed = username_no_digits
                        for pfx in ['mr', 'ms', 'dr', 'hr']:
                            if lowered.startswith(pfx):
                                rem = username_no_digits[len(pfx):]
                                if rem and rem[0] in '._-':
                                    prefix_removed = rem[1:]
                                    break
                                elif pfx == 'hr' and len(rem) >= 3:
                                    prefix_removed = rem
                                    break
                                elif pfx in ('mr', 'ms', 'dr') and len(rem) >= 4:
                                    prefix_removed = rem
                                    break
                                    
                        lowered_prefix_removed = prefix_removed.lower()
                        if lowered_prefix_removed not in ("unknown", "candidate", "admin", "recruit", "hr", "jobs", "careers", "info", "support", "contact", "office", "staff", "hello", "team", "sales", "marketing", "work", "example") and not lowered_prefix_removed.startswith("unknown_"):
                            parts = re.split(r'[\._\-]', prefix_removed)
                            segmented_parts = []
                            segments = {
                                "raj", "kumar", "azeez", "basha", "sunny", "singh", "sharma", "verma", "gupta", "bose", "das", "roy", "sen", "amit", "rahul", "priya", "neha", "pooja"
                            }
                            for p in parts:
                                p_lower = p.lower()
                                split_done = False
                                for i in range(3, len(p_lower) - 2):
                                    part1 = p_lower[:i]
                                    part2 = p_lower[i:]
                                    if part1 in segments or part2 in segments:
                                        segmented_parts.append(part1)
                                        segmented_parts.append(part2)
                                        split_done = True
                                        break
                                if not split_done:
                                    segmented_parts.append(p)
                                    
                            email_name_raw = " ".join(segmented_parts).strip().title()
                            if is_acceptable_name(email_name_raw):
                                email_name = email_name_raw

                logger.info(f"[NAME] Email Fallback: {email_name or 'None'}")
                print(f"[NAME] Email Fallback: {email_name or 'None'}")
                if email_name:
                    return email_name

                return "Unknown Candidate"

            candidate_name = get_priority_name()[:255]
            profile.full_name = candidate_name
            if isinstance(info, dict):
                info['name'] = candidate_name
            profile.summary = parsed_data.get('summary', '')
            profile.location = (info.get('location') or "Unknown")[:100]
            # Parse salary safely
            curr_sal = parsed_data.get('current_ctc')
            if curr_sal is not None and str(curr_sal).strip() not in ("", "None", "null"):
                try:
                    profile.current_salary = Decimal(str(curr_sal))
                except Exception:
                    profile.current_salary = None
            else:
                profile.current_salary = None

            exp_sal = parsed_data.get('expected_ctc')
            if exp_sal is not None and str(exp_sal).strip() not in ("", "None", "null"):
                try:
                    profile.expected_salary = Decimal(str(exp_sal))
                except Exception:
                    profile.expected_salary = None
            else:
                profile.expected_salary = None

            profile.notice_period = parsed_data.get('notice_period', 30)
            
            total_exp_val = info.get('total_experience', 0.0)
            if total_exp_val is not None and str(total_exp_val).strip() not in ("", "None", "null"):
                try:
                    profile.total_experience = Decimal(str(total_exp_val))
                except Exception:
                    profile.total_experience = Decimal("0.0")
            else:
                profile.total_experience = Decimal("0.0")
            
            profile.current_company = (info.get('current_company') or "")[:255]
            profile.current_designation = (info.get('current_designation') or "Professional")[:255]
            profile.linkedin_url = (info.get('linkedin_url') or "")[:200] or None
            profile.portfolio_url = (info.get('portfolio_url') or "")[:200] or None

            profile.parsed_json = parsed_data
            profile.ocr_engine = ocr_result.get("engine", "None")
            profile.ocr_confidence = Decimal(str(ocr_result.get("confidence", 0.0)))
            profile.resume_type = ocr_result.get("resume_type", "UNKNOWN")
            
            profile.raw_resume_text = text
            profile.original_experience_json = parsed_data.get('experience', [])
            profile.original_skills = parsed_data.get('skills', [])
            profile.original_summary = parsed_data.get('summary', '')
            
            v1_data = {
                "version": 1,
                "label": "Original Resume",
                "data": parsed_data,
                "created_at": datetime.now().isoformat(),
                "created_by": "System OCR Parser"
            }
            profile.resume_versions = {"1": v1_data}
            profile.current_version = 1
            profile.audit_logs = [{
                "action": "Parsed original resume using " + ocr_result.get("engine", "None"),
                "timestamp": datetime.now().isoformat(),
                "user": "System"
            }]
            
            if security_data:
                profile.original_filename = (security_data.get("sanitized_filename", filename) or "")[:255]
                profile.secure_filename = (security_data.get("secure_filename") or "")[:255]
                profile.sha256 = security_data.get("sha256")
                profile.mime_type = (security_data.get("mime_type") or "")[:100]
                profile.scan_status = security_data.get("scan_status", "PASSED")
                profile.scan_timestamp = security_data.get("scan_timestamp")
                profile.parser_status = "SUCCESS"
                profile.preview_status = "READY"
            else:
                profile.original_filename = (filename or "")[:255]
                profile.secure_filename = (filename or "")[:255]
                profile.parser_status = "SUCCESS"
                profile.preview_status = "READY"

            try:
                save_filename = security_data.get("secure_filename") if (security_data and security_data.get("secure_filename")) else filename
                profile.resume.save(save_filename, ContentFile(file_bytes), save=False)
                
                # Copy file inside storage instead of duplicate upload
                target_key = "resumes/original/original_" + os.path.basename(profile.resume.name)
                if copy_storage_file(profile.resume, target_key):
                    profile.original_file.name = target_key
                else:
                    profile.original_file.save("original_" + save_filename, ContentFile(file_bytes), save=False)
                    
                logger.info(f"[PARSER FILE SAVE SUCCESS] Physical files saved: {save_filename}")
                print(f"[PARSER FILE SAVE SUCCESS] Physical files saved: {save_filename}")
                
                if photo_bytes is None:
                    logger.info("[PHOTO] No valid candidate portrait found.")
                    print("[PHOTO] No valid candidate portrait found.")
                    profile.profile_photo = None
                else:
                    profile.profile_photo.save(f"photo_{profile.id}.{photo_ext}", ContentFile(photo_bytes), save=False)
                    logger.info(f"[PARSER PHOTO SAVE SUCCESS] Extracted and saved profile photo for {profile.full_name}")
                    print(f"[PARSER PHOTO SAVE SUCCESS] Extracted and saved profile photo for {profile.full_name}")
            except Exception as e:
                logger.error(f"[PARSER FILE SAVE ERROR] Error saving resume file to disk: {str(e)}", exc_info=True)
                print(f"[PARSER FILE SAVE ERROR] Error saving resume file to disk: {str(e)}")
            
            profile.save()
            t_profile = time.time() - t_profile_start
            logger.info(f"[TIMING] Profile DB save took: {t_profile:.4f}s")
            print(f"[TIMING] Profile DB save took: {t_profile:.4f}s")
            
            # Skills save
            t_skills_start = time.time()
            profile.skills.all().delete()
            for skill in parsed_data.get('skills', []):
                CandidateSkill.objects.get_or_create(profile=profile, skill_name=skill.strip().title()[:100])
            t_skills = time.time() - t_skills_start
            logger.info(f"[TIMING] Skills DB save took: {t_skills:.4f}s")
            print(f"[TIMING] Skills DB save took: {t_skills:.4f}s")
                
            # Experience save
            t_exp_start = time.time()
            profile.experiences.all().delete()
            for exp in parsed_data.get('experience', []):
                description_html = ResumeIntelligenceService.parse_experience_description_to_html(exp.get('description', ''))
                Experience.objects.create(
                    profile=profile,
                    company_name=(exp.get('company') or '')[:100],
                    designation=(exp.get('designation') or '')[:100],
                    description=description_html,
                    start_date=parse_date_robust(exp.get('start_date'), None),
                    end_date=parse_date_robust(exp.get('end_date'), None)
                )
            t_exp = time.time() - t_exp_start
            logger.info(f"[TIMING] Experience DB save took: {t_exp:.4f}s")
            print(f"[TIMING] Experience DB save took: {t_exp:.4f}s")
                
            # Education save
            t_edu_start = time.time()
            profile.educations.all().delete()
            for edu in parsed_data.get('education', []):
                Education.objects.create(
                    profile=profile,
                    institution=(edu.get('institution') or '')[:100],
                    degree=(edu.get('degree') or '')[:100],
                    field_of_study=(edu.get('field_of_study') or '')[:100],
                    percentage_or_cgpa=(edu.get('score') or '')[:20],
                    start_date=parse_date_robust(edu.get('start_date'), None),
                    end_date=parse_date_robust(edu.get('end_date'), None)
                )
            t_edu = time.time() - t_edu_start
            logger.info(f"[TIMING] Education DB save took: {t_edu:.4f}s")
            print(f"[TIMING] Education DB save took: {t_edu:.4f}s")
                
            # Projects save
            t_proj_start = time.time()
            profile.projects.all().delete()
            for proj in parsed_data.get('projects', []):
                Project.objects.create(
                    profile=profile,
                    title=(proj.get('title') or '')[:255],
                    description=ResumeIntelligenceService.parse_experience_description_to_html(proj.get('description', '')),
                    link=proj.get('link', '')
                )
            t_proj = time.time() - t_proj_start
            logger.info(f"[TIMING] Projects DB save took: {t_proj:.4f}s")
            print(f"[TIMING] Projects DB save took: {t_proj:.4f}s")
                
            # Certifications save
            t_cert_start = time.time()
            profile.certifications.all().delete()
            for cert in parsed_data.get('certifications', []):
                Certification.objects.create(
                    profile=profile,
                    name=(cert.get('name') or '')[:255],
                    issuing_organization=(cert.get('issuing_organization') or '')[:255],
                    issue_date=parse_date_robust(cert.get('issue_date'), None)
                )
            t_cert = time.time() - t_cert_start
            logger.info(f"[TIMING] Certifications DB save took: {t_cert:.4f}s")
            print(f"[TIMING] Certifications DB save took: {t_cert:.4f}s")
                
            # Calculate and save ATS suitability score
            t_ats_start = time.time()
            try:
                from services.candidate_matching_service import CandidateMatchingService
                CandidateMatchingService.update_ats_scores(candidate_id=profile.id)
                if progress_callback:
                    progress_callback("ats_score_generated")
            except Exception as e:
                logger.error(f"[PARSER ATS ERROR] Failed updating ATS suitability index score: {str(e)}", exc_info=True)
                print(f"[PARSER ATS ERROR] Failed updating ATS suitability index score: {str(e)}")
            t_ats = time.time() - t_ats_start
            logger.info(f"[TIMING] ATS suitability scoring took: {t_ats:.4f}s")
            print(f"[TIMING] ATS suitability scoring took: {t_ats:.4f}s")
            
            # Dynamic PDF generation: Skipped entirely during upload parsing!
            logger.info("[TIMING] ReportLab PDF generation skipped during parsing upload.")
            print("[TIMING] ReportLab PDF generation skipped during parsing upload.")

            t_db = time.time() - t_db_start
            logger.info(f"[TIMING] Total Database Transaction took: {t_db:.4f}s")
            print(f"[TIMING] Total Database Transaction took: {t_db:.4f}s")

            logger.info(f"[PARSER COMPLETED] Candidate Profile created/updated successfully: {profile.id}")
            print(f"[PARSER COMPLETED] Candidate Profile created successfully: ID={profile.id}, Name={profile.full_name}")
            
            t_total = time.time() - t_process_start
            logger.info(f"[TIMING] process_resume_file TOTAL duration: {t_total:.4f}s")
            
            # Print exact timing stages as requested
            print(f"OCR: {t_ocr:.2f}s")
            print(f"OpenAI: {t_openai:.2f}s")
            print(f"Validation: {t_validation:.2f}s")
            print(f"Database: {t_db:.2f}s")
            print(f"Total: {t_total:.2f}s")
            
            if progress_callback:
                progress_callback("completed", profile)
                
            return profile, "SUCCESS"
            
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"[PARSER DATABASE SAVE FAILURE] Failed saving candidate database records for {filename}: {str(e)}\n{tb}", exc_info=True)
        print(f"[PARSER DATABASE SAVE FAILURE] Exception Traceback in process_resume_file:\n{tb}")
        return None, "SAVE_FAILED"

def handle_resume_upload(uploaded_file, overwrite=False, progress_callback=None, user=None):
    from utils.security import perform_all_security_validations, log_upload_attempt, SecurityValidationError
    
    results = {'created': [], 'duplicates': 0, 'duplicate_profiles': [], 'errors': 0, 'error_reasons': []}
    
    try:
        if hasattr(uploaded_file, 'seek'):
            uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
    except Exception as e:
        log_upload_attempt(uploaded_file.name, None, user, "ERROR", "ERROR", f"Read error: {str(e)}")
        raise ValueError("Error reading file bytes.")

    sha256 = hashlib.sha256(file_bytes).hexdigest()

    try:
        # Perform all security validations
        security_data = perform_all_security_validations(file_bytes, uploaded_file.name)
        # Log successful upload scan
        log_upload_attempt(uploaded_file.name, sha256, user, "CLEAN", "CLEAN")
    except SecurityValidationError as e:
        # Log rejected attempt
        log_upload_attempt(uploaded_file.name, sha256, user, "INFECTED" if "Virus" in str(e) else "CLEAN", "INFECTED" if "Malware" in str(e) else "CLEAN", str(e))
        raise ValueError(str(e))
    except Exception as e:
        log_upload_attempt(uploaded_file.name, sha256, user, "ERROR", "ERROR", str(e))
        raise ValueError(str(e))

    ext = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else ''

    reason_map = {
        "INVALID_FORMAT": "Invalid file format. Supported: PDF, DOC, DOCX, RTF, TXT.",
        "READ_ERROR": "Error reading file bytes.",
        "OCR_FAILED": "OCR engine extraction failed.",
        "NLP_FAILED": "NLP parsing/extraction failed.",
        "SAVE_FAILED": "Database save failed.",
        "SECURITY_FAILED": "Security validation failed."
    }

    if ext == 'zip':
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as z:
                for filename in z.namelist():
                    # Directories or nested zip files are not processed directly
                    if filename.endswith('/') or filename.lower().endswith('.zip'):
                        continue
                    
                    sub_ext = filename.split('.')[-1].lower() if '.' in filename else ''
                    if sub_ext not in ['pdf', 'doc', 'docx', 'rtf', 'txt']:
                        continue
                        
                    with z.open(filename) as f:
                        sub_bytes = f.read()
                        sub_sha = hashlib.sha256(sub_bytes).hexdigest()
                        
                        from utils.security import sanitize_filename, generate_secure_filename, get_mime_type
                        sub_security_data = {
                            "sanitized_filename": sanitize_filename(filename),
                            "secure_filename": generate_secure_filename(filename),
                            "sha256": sub_sha,
                            "mime_type": get_mime_type(sub_bytes, filename, sub_ext),
                            "scan_status": "PASSED",
                            "scan_timestamp": timezone.now()
                        }
                        
                        file_obj = io.BytesIO(sub_bytes)
                        profile, status = process_resume_file(
                            file_obj, filename, overwrite, progress_callback, security_data=sub_security_data, user=user
                        )
                        
                        if status == "SUCCESS":
                            results['created'].append(profile)
                        elif status == "DUPLICATE":
                            results['duplicates'] += 1
                            if profile:
                                results['duplicate_profiles'].append(profile)
                        else:
                            results['errors'] += 1
                            err_reason = reason_map.get(status, f"Unknown parsing error ({status})")
                            results['error_reasons'].append(f"{filename}: {err_reason}")
        except Exception as e:
            raise ValueError(f"ZIP processing error: {str(e)}")
    else:
        file_obj = io.BytesIO(file_bytes)
        profile, status = process_resume_file(
            file_obj, uploaded_file.name, overwrite, progress_callback, security_data=security_data, user=user
        )
        if status == "SUCCESS":
            results['created'].append(profile)
        elif status == "DUPLICATE":
            results['duplicates'] += 1
            if profile:
                results['duplicate_profiles'].append(profile)
        else:
            results['errors'] += 1
            err_reason = reason_map.get(status, f"Unknown parsing error ({status})")
            results['error_reasons'].append(err_reason)
            
    return results

def select_best_profile_photo(images_list):
    """
    Refactored profile photo selector.
    Returns: (photo_bytes, ext) if a valid candidate portrait is found, else (None, None).
    """
    if not images_list:
        logger.info("[PHOTO] No valid candidate portrait found.")
        return None, None

    import cv2
    import numpy as np
    import os
    import re

    # Load Haar cascades
    face_cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
    profile_cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_profileface.xml')
    face_cascade = cv2.CascadeClassifier(face_cascade_path)
    profile_cascade = cv2.CascadeClassifier(profile_cascade_path)
    use_face_detection = not (face_cascade.empty() or profile_cascade.empty())

    valid_candidates = []

    for idx, (img_bytes, ext) in enumerate(images_list, 1):
        try:
            logger.info(f"[PHOTO] Image #{idx}")
            
            # Decode image
            np_arr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if img is None:
                logger.info("Width: 0\nHeight: 0\nFaces: 0\nOCR Text Ratio: 0.0\nDecision: Rejected (could not decode)")
                continue

            height, width = img.shape[:2]
            logger.info(f"Width: {width}")
            logger.info(f"Height: {height}")
            
            # Rule 1: Reject immediately if width < 120 or height < 120
            if width < 120 or height < 120:
                logger.info("Faces: 0\nOCR Text Ratio: 0.0\nDecision: rejected (too small)")
                continue

            # Aspect Ratio
            aspect_ratio = width / height
            
            # Rule 2: Reject landscape screenshots/wide banners/very tall narrow slices
            if aspect_ratio < 0.5 or aspect_ratio > 1.25:
                logger.info("Faces: 0\nOCR Text Ratio: 0.0\nDecision: rejected (invalid aspect ratio)")
                continue

            # Convert to gray
            if len(img.shape) == 2:
                gray = img
            else:
                if img.shape[2] == 4:
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    gray = cv2.cvtColor(img_rgb, cv2.COLOR_BGR2GRAY)
                else:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Rule 3: Mostly white document check
            white_pixels = np.sum(gray > 240)
            white_ratio = white_pixels / gray.size
            if white_ratio > 0.85:
                logger.info("Faces: 0\nOCR Text Ratio: 0.0\nDecision: rejected (mostly white document)")
                continue

            # Detect faces
            num_faces = 0
            faces = []
            if use_face_detection:
                frontal_faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
                profile_faces = profile_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
                
                faces = list(frontal_faces)
                for pf in profile_faces:
                    px, py, pw, ph = pf
                    overlap = False
                    for ff in frontal_faces:
                        fx, fy, fw, fh = ff
                        if abs((px + pw/2) - (fx + fw/2)) < fw/2 and abs((py + ph/2) - (fy + fh/2)) < fh/2:
                            overlap = True
                            break
                    if not overlap:
                        faces.append(pf)
                num_faces = len(faces)

            logger.info(f"Faces: {num_faces}")

            # Rule 4: Reject if no face detected
            if num_faces == 0:
                logger.info("OCR Text Ratio: 0.0\nDecision: rejected (no face)")
                continue

            # Rule 5: Reject if more than one face detected
            if num_faces > 1:
                logger.info("OCR Text Ratio: 0.0\nDecision: rejected (multiple faces)")
                continue

            # Get the single face details
            fx, fy, fw, fh = faces[0]
            face_area = fw * fh
            img_area = width * height
            face_area_pct = (face_area / img_area) * 100

            # Rule 6: Face area occupies less than 22% or more than 80% of image
            if face_area_pct < 22 or face_area_pct > 80:
                logger.info(f"OCR Text Ratio: 0.0\nDecision: rejected (face occupies {face_area_pct:.1f}% of image, outside 22-80%)")
                continue

            # Rule 7: Face centered check
            face_x_center = fx + fw/2
            face_y_center = fy + fh/2
            img_x_center = width / 2
            img_y_center = height / 2
            x_offset = abs(face_x_center - img_x_center) / width
            y_offset = abs(face_y_center - img_y_center) / height
            if x_offset > 0.25 or y_offset > 0.35:
                logger.info("OCR Text Ratio: 0.0\nDecision: rejected (face not centered)")
                continue

            # Rule 8: Detect text regions to compute OCR text density / text area
            # Sobel horizontal gradients
            grad = cv2.Sobel(gray, cv2.CV_8U, 1, 0, ksize=3)
            _, thresh = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
            dilated = cv2.dilate(thresh, kernel, iterations=1)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            text_area = 0
            for ctr in contours:
                cx, cy, cw, ch = cv2.boundingRect(ctr)
                if cw > 10 and 5 < ch < 50:
                    text_area += cw * ch

            ocr_text_ratio = text_area / img_area
            logger.info(f"OCR Text Ratio: {ocr_text_ratio:.2f}")

            # Rule 9: Reject if text area > face area
            if text_area > face_area:
                logger.info("Decision: rejected (text area > face area)")
                continue

            # Rule 10: Reject if OCR text density occupies significant portion (> 30% of total image)
            if ocr_text_ratio > 0.3:
                logger.info("Decision: rejected (mostly text)")
                continue

            # Rule 11: Table detection
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
            detect_horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
            cnts_h = cv2.findContours(detect_horizontal, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
            detect_vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
            cnts_v = cv2.findContours(detect_vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
            if len(cnts_h) > 5 and len(cnts_v) > 5:
                logger.info("Decision: rejected (table detected)")
                continue

            # Rule 12: OCR text content check for Resume/CV headings
            text_content = ""
            try:
                import pytesseract
                from PIL import Image
                pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                text_content = pytesseract.image_to_string(pil_img).lower()
            except Exception:
                pass

            if any(term in text_content for term in ("curriculum", "vitae", "resume", "cv", "education", "experience")):
                logger.info("Decision: rejected (curriculum vitae header)")
                continue

            # If all checks pass, it is a valid candidate portrait!
            logger.info("Decision: accepted (candidate portrait)")
            valid_candidates.append({
                'img_bytes': img_bytes,
                'ext': ext,
                'resolution': img_area,
                'face_area': face_area
            })

        except Exception as e:
            logger.error(f"Decision: rejected (exception occurred: {e})")
            continue

    if valid_candidates:
        # Prefer the one with the largest face area, then resolution
        valid_candidates.sort(key=lambda x: (x['face_area'], x['resolution']), reverse=True)
        best = valid_candidates[0]
        return best['img_bytes'], best['ext']

    logger.info("[PHOTO] No valid candidate portrait found.")
    return None, None


def extract_profile_photo(file_bytes, filename):
    ext = filename.split('.')[-1].lower()
    images_list = []
    if ext == 'pdf':
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)
                for img_info in image_list:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue
                    img_data = base_image.get("image")
                    if img_data:
                        images_list.append((img_data, base_image.get("ext", "png")))
        except Exception as e:
            logger.error(f"Error extracting photo from PDF: {e}")
    elif ext in ['docx', 'doc']:
        try:
            import zipfile
            import io
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                media_files = [f for f in z.namelist() if f.startswith('word/media/')]
                media_files.sort()
                for f_name in media_files:
                    img_data = z.read(f_name)
                    ext = f_name.split('.')[-1].lower()
                    images_list.append((img_data, ext))
        except Exception as e:
            logger.error(f"Error extracting photo from DOCX: {e}")

    return select_best_profile_photo(images_list)