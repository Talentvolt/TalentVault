import re
import zipfile
import io
import hashlib
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
    import pdfplumber
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
    import docx
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
        import time
        from services.parser.llm_extractor import LLMExtractor
        from apps.candidates.utils import convert_llm_data_to_standard_format
        
        t0 = time.time()
        extractor = LLMExtractor()
        raw_parsed = extractor.extract_resume(text)
        logger.info(f"[TIMING] LLMExtractor run took: {time.time() - t0:.4f}s")
        print(f"[TIMING] LLMExtractor run took: {time.time() - t0:.4f}s")
        
        t_val = time.time()
        result = convert_llm_data_to_standard_format(raw_parsed)
        logger.info(f"[TIMING] JSON validation & conversion took: {time.time() - t_val:.4f}s")
        print(f"[TIMING] JSON validation & conversion took: {time.time() - t_val:.4f}s")
        return result

def process_resume_file(file_obj, filename, overwrite=False, progress_callback=None, security_data=None, user=None):
    from services.parser.pipeline import ResumeParsingPipeline
    pipeline = ResumeParsingPipeline(
        file_obj=file_obj,
        filename=filename,
        overwrite=overwrite,
        progress_callback=progress_callback,
        security_data=security_data,
        user=user
    )
    return pipeline.run()

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