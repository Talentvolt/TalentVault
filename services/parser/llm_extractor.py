import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from django.db import transaction
from django.conf import settings
from pydantic import BaseModel, Field
from openai import OpenAI

from apps.candidates.models import CandidateProfile, CandidateSkill, Experience, Education, Project, Certification

logger = logging.getLogger(__name__)

# ======================================================================
# Pydantic Schemas for Structured Output with Source Metadata
# ======================================================================

class FieldString(BaseModel):
    value: Optional[str] = Field(description="The extracted string value exactly as it appears in the text, or null if missing.")
    source_text: Optional[str] = Field(description="The exact text snippet where this value was found, or null if missing.")
    page_number: int = Field(default=0, description="The 0-based page number where this field was found.")
    confidence: float = Field(default=1.0, description="Confidence score between 0.0 and 1.0 (or 0 and 100) for this field.")

class FieldListString(BaseModel):
    value: Optional[List[str]] = Field(description="The list of extracted string values exactly as they appear, or null if missing.")
    source_text: Optional[str] = Field(description="The exact text snippet where these values were found, or null if missing.")
    page_number: int = Field(default=0, description="The 0-based page number.")
    confidence: float = Field(default=1.0, description="Confidence score.")

class ExperienceItem(BaseModel):
    company: FieldString
    designation: FieldString
    location: FieldString
    employment_type: FieldString
    start_date: FieldString
    end_date: FieldString
    description: FieldString

class FieldExperience(BaseModel):
    value: Optional[List[ExperienceItem]] = Field(description="List of parsed experience objects.")
    source_text: Optional[str] = Field(description="The exact text snippet of the Work Experience section.")
    page_number: int = Field(default=0, description="The 0-based page number.")
    confidence: float = Field(default=1.0, description="Confidence score.")

class EducationItem(BaseModel):
    degree: FieldString
    branch: FieldString
    college: FieldString
    board: FieldString
    university: FieldString
    start_year: FieldString
    end_year: FieldString
    cgpa: FieldString
    percentage: FieldString
    grade: FieldString

class FieldEducation(BaseModel):
    value: Optional[List[EducationItem]] = Field(description="List of parsed education objects.")
    source_text: Optional[str] = Field(description="The exact text snippet of the Education section.")
    page_number: int = Field(default=0, description="The 0-based page number.")
    confidence: float = Field(default=1.0, description="Confidence score.")

class ProjectItem(BaseModel):
    title: FieldString
    description: FieldString
    technologies: FieldString
    duration: FieldString

class FieldProject(BaseModel):
    value: Optional[List[ProjectItem]] = Field(description="List of parsed project objects.")
    source_text: Optional[str] = Field(description="The exact text snippet of the Projects section.")
    page_number: int = Field(default=0, description="The 0-based page number.")
    confidence: float = Field(default=1.0, description="Confidence score.")

class CertificationItem(BaseModel):
    name: FieldString
    issuing_organization: FieldString
    issue_date: FieldString

class FieldCertification(BaseModel):
    value: Optional[List[CertificationItem]] = Field(description="List of parsed certifications.")
    source_text: Optional[str] = Field(description="The exact text snippet of the Certifications section.")
    page_number: int = Field(default=0, description="The 0-based page number.")
    confidence: float = Field(default=1.0, description="Confidence score.")

class ResumeSchema(BaseModel):
    candidate_name: FieldString
    email: FieldString
    phone: FieldString
    linkedin: FieldString
    github: FieldString
    portfolio: FieldString
    address: FieldString
    city: FieldString
    state: FieldString
    country: FieldString
    current_designation: FieldString
    current_company: FieldString
    professional_summary: FieldString
    work_experience: FieldExperience
    education: FieldEducation
    projects: FieldProject
    technical_skills: FieldListString
    soft_skills: FieldListString
    languages: FieldListString
    certifications: FieldCertification
    awards: FieldListString
    achievements: FieldListString
    training: FieldListString
    interests: FieldListString
    strengths: FieldListString
    references: FieldListString

# ======================================================================
# System Prompt
# ======================================================================

SYSTEM_PROMPT = """
You are a strict resume parsing assistant.
Your job is to extract fields from the provided resume text.

CRITICAL RULES:
1. DO NOT invent or hallucinate any data.
2. DO NOT normalize or clean values. If the resume has "B.Tech", do not change to "Bachelor of Technology".
3. DO NOT expand abbreviations.
4. DO NOT change dates or invent "Present". If the resume says "2009", extract "2009", not "2009-2009" or "Present".
5. For every extracted field, you must return:
   - "value": the exact string value as it appears in the resume.
   - "source_text": the exact verbatim sentence or line from the resume containing the value.
   - "page_number": the page index (0-based) where it was found.
   - "confidence": your confidence score for the extraction (between 0.0 and 100.0).
6. If any field is missing or not mentioned, set "value" and "source_text" to null. DO NOT guess.
7. Descriptions of experience and projects must preserve bullets, line breaks, exact wording, and paragraph spacing.
"""

# ======================================================================
# LLMExtractor Service
# ======================================================================

class LLMExtractor:
    """
    LLMExtractor uses OpenAI Responses API (Structured Outputs) to extract
    structured fields from resume text and validates them against the original text blocks.
    """

    def __init__(self):
        self.api_key = getattr(settings, "OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY"))
        self.model = getattr(settings, "OPENAI_MODEL_NAME", "gpt-4.1-mini")

    def extract_resume(self, text: str) -> dict:
        """
        Calls OpenAI structured outputs API to parse the resume text into ResumeSchema.
        """
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
            
        client = OpenAI(api_key=self.api_key)
        
        completion = client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            response_format=ResumeSchema
        )
        
        parsed_response = completion.choices[0].message.parsed
        extracted_dict = parsed_response.model_dump()
        
        # Validate against original text
        validated_dict = self.validate_document(extracted_dict, text)
        return validated_dict

    # ======================================================================
    # Validation Engine
    # ======================================================================

    def validate_document(self, extracted_data: dict, original_text: str) -> dict:
        """
        Validates every extracted value against the original text of the document.
        If any value is not found inside the original text, it is set to None.
        Calculates field-level, section-level and overall confidences.
        """
        # Lowercase and strip whitespace for matching
        doc_text_clean = " ".join(original_text.split())
        
        # Recursively validate and sanitize data
        sanitized_data = self._validate_and_sanitize(extracted_data, doc_text_clean)
        
        # Calculate confidences
        final_data = self.calculate_confidences(sanitized_data)
        return final_data

    def _validate_and_sanitize(self, data: Any, doc_text_clean: str) -> Any:
        if isinstance(data, dict):
            if "value" in data and "source_text" in data:
                val = data.get("value")
                if val is not None:
                    if isinstance(val, list):
                        valid_list = []
                        for item in val:
                            if isinstance(item, str):
                                if self._text_exists_in_doc(item, doc_text_clean):
                                    valid_list.append(item)
                                else:
                                    logger.warning(f"Rejected hallucinated list item: '{item}'")
                            else:
                                validated_item = self._validate_and_sanitize(item, doc_text_clean)
                                valid_list.append(validated_item)
                        data["value"] = valid_list
                    elif isinstance(val, str):
                        if not self._text_exists_in_doc(val, doc_text_clean):
                            logger.warning(f"Rejected hallucinated value: '{val}'")
                            data["value"] = None
                            data["source_text"] = None
                            data["confidence"] = 0.0
                    elif isinstance(val, (int, float)):
                        if not self._text_exists_in_doc(str(val), doc_text_clean):
                            logger.warning(f"Rejected hallucinated numeric value: '{val}'")
                            data["value"] = None
                            data["source_text"] = None
                            data["confidence"] = 0.0
                return data
            else:
                return {k: self._validate_and_sanitize(v, doc_text_clean) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._validate_and_sanitize(item, doc_text_clean) for item in data]
        return data

    def _text_exists_in_doc(self, value: str, doc_text_clean: str) -> bool:
        if not value:
            return True
        val_clean = " ".join(str(value).split()).lower()
        val_clean_alphanumeric = re.sub(r'[^a-zA-Z0-9]', '', val_clean)
        if not val_clean_alphanumeric:
            return True
        doc_clean_alphanumeric = re.sub(r'[^a-zA-Z0-9]', '', doc_text_clean).lower()
        return val_clean_alphanumeric in doc_clean_alphanumeric

    # ======================================================================
    # Confidence Calculations
    # ======================================================================

    def calculate_confidences(self, data: dict) -> dict:
        confidences = {}
        
        # 1. Personal Info
        personal_fields = [
            "candidate_name", "email", "phone", "linkedin", "github", "portfolio",
            "address", "city", "state", "country", "current_designation", "current_company"
        ]
        p_confs = [data[f]["confidence"] for f in personal_fields if f in data and "confidence" in data[f]]
        confidences["personal_info"] = sum(p_confs) / len(p_confs) if p_confs else 100.0
        
        # 2. Work Experience
        exp_confs = []
        work_exp = data.get("work_experience", {})
        if work_exp and isinstance(work_exp.get("value"), list):
            for item in work_exp["value"]:
                for v in item.values():
                    if isinstance(v, dict) and "confidence" in v:
                        exp_confs.append(v["confidence"])
        confidences["work_experience"] = sum(exp_confs) / len(exp_confs) if exp_confs else work_exp.get("confidence", 100.0)
        
        # 3. Education
        edu_confs = []
        education = data.get("education", {})
        if education and isinstance(education.get("value"), list):
            for item in education["value"]:
                for v in item.values():
                    if isinstance(v, dict) and "confidence" in v:
                        edu_confs.append(v["confidence"])
        confidences["education"] = sum(edu_confs) / len(edu_confs) if edu_confs else education.get("confidence", 100.0)
        
        # 4. Projects
        proj_confs = []
        projects = data.get("projects", {})
        if projects and isinstance(projects.get("value"), list):
            for item in projects["value"]:
                for v in item.values():
                    if isinstance(v, dict) and "confidence" in v:
                        proj_confs.append(v["confidence"])
        confidences["projects"] = sum(proj_confs) / len(proj_confs) if proj_confs else projects.get("confidence", 100.0)
        
        # 5. Skills
        skill_fields = ["technical_skills", "soft_skills"]
        s_confs = [data[f]["confidence"] for f in skill_fields if f in data and "confidence" in data[f]]
        confidences["skills"] = sum(s_confs) / len(s_confs) if s_confs else 100.0
        
        # 6. Certifications
        cert_confs = []
        certs = data.get("certifications", {})
        if certs and isinstance(certs.get("value"), list):
            for item in certs["value"]:
                for v in item.values():
                    if isinstance(v, dict) and "confidence" in v:
                        cert_confs.append(v["confidence"])
        confidences["certifications"] = sum(cert_confs) / len(cert_confs) if cert_confs else certs.get("confidence", 100.0)

        # 7. Other sections
        other_fields = ["professional_summary", "languages", "awards", "achievements", "training", "interests", "strengths", "references"]
        o_confs = [data[f]["confidence"] for f in other_fields if f in data and "confidence" in data[f]]
        confidences["other"] = sum(o_confs) / len(o_confs) if o_confs else 100.0

        # Calculate overall
        overall = sum(confidences.values()) / len(confidences) if confidences else 100.0
        
        data["section_confidence"] = confidences
        data["overall_confidence"] = overall
        return data

# ======================================================================
# DB Saving Transaction
# ======================================================================

def _flatten(field_data: Any) -> Any:
    if isinstance(field_data, dict) and "value" in field_data:
        return field_data["value"]
    return field_data

def parse_date_robust(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    cleaned = date_str.strip().lower()
    if cleaned in ("present", "current", "till date"):
        return datetime.now().date()
        
    formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%b %Y", "%B %Y", "%m/%Y", "%Y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except Exception:
            continue
    return None


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


@transaction.atomic
def save_llm_parsed_data_to_db(profile: CandidateProfile, validated_data: dict) -> CandidateProfile:
    """
    Saves the validated structured data back into PostgreSQL:
    Updates CandidateProfile summary and parsed_json fields, and updates relation tables.
    """
    # 1. Store full metadata-rich structured JSON
    profile.parsed_json = validated_data
    
    # 2. Extract flat values to sync candidate profile fields
    profile.full_name = _flatten(validated_data.get("candidate_name")) or profile.full_name
    profile.summary = _flatten(validated_data.get("professional_summary")) or ""
    
    # Contact & location
    email = _flatten(validated_data.get("email"))
    phone = _flatten(validated_data.get("phone"))
    location = _flatten(validated_data.get("address")) or _flatten(validated_data.get("city")) or "Unknown"
    
    profile.location = location[:100]
    profile.linkedin_url = _flatten(validated_data.get("linkedin"))
    profile.portfolio_url = _flatten(validated_data.get("portfolio"))
    
    profile.current_company = (_flatten(validated_data.get("current_company")) or "")[:255]
    profile.current_designation = (_flatten(validated_data.get("current_designation")) or "")[:255]
    
    profile.save()
    
    # 3. Sync Skills
    profile.skills.all().delete()
    tech_skills = _flatten(validated_data.get("technical_skills")) or []
    soft_skills = _flatten(validated_data.get("soft_skills")) or []
    for sk in (tech_skills + soft_skills):
        if sk:
            CandidateSkill.objects.get_or_create(profile=profile, skill_name=sk.strip().title()[:100])

    # 4. Sync Experiences
    profile.experiences.all().delete()
    work_exp = validated_data.get("work_experience", {})
    if work_exp and isinstance(work_exp.get("value"), list):
        for item in work_exp["value"]:
            comp = _flatten(item.get("company")) or "Unknown"
            desig = _flatten(item.get("designation")) or "Role"
            desc = _flatten(item.get("description")) or ""
            loc = _flatten(item.get("location")) or ""
            
            s_date = parse_date_robust(_flatten(item.get("start_date")))
            e_date = parse_date_robust(_flatten(item.get("end_date")))
            
            # Note: Django model Experience description should preserve HTML formatting exactly
            from services.resume_intelligence import ResumeIntelligenceService
            desc_html = ResumeIntelligenceService.parse_experience_description_to_html(desc)
            
            Experience.objects.create(
                profile=profile,
                company_name=comp[:255],
                designation=desig[:255],
                description=desc_html,
                start_date=s_date,
                end_date=e_date
            )

    # 5. Sync Education
    profile.educations.all().delete()
    education = validated_data.get("education", {})
    if education and isinstance(education.get("value"), list):
        for item in education["value"]:
            deg = _flatten(item.get("degree")) or "Degree"
            inst = _flatten(item.get("college")) or _flatten(item.get("university")) or "Institution"
            field = _flatten(item.get("branch")) or "General"
            cgpa = _flatten(item.get("cgpa")) or _flatten(item.get("percentage")) or ""
            
            s_year = _flatten(item.get("start_year"))
            e_year = _flatten(item.get("end_year"))
            
            # If only one completion year exists, store it as end_date
            if s_year and not e_year:
                e_year = s_year
                s_year = ""
                
            s_date = parse_education_date_to_date_obj(s_year)
            e_date = parse_education_date_to_date_obj(e_year)
            
            Education.objects.create(
                profile=profile,
                institution=inst[:255],
                degree=deg[:255],
                field_of_study=field[:255],
                percentage_or_cgpa=cgpa[:20],
                start_date=s_date,
                end_date=e_date
            )

    # 6. Sync Projects
    profile.projects.all().delete()
    projects = validated_data.get("projects", {})
    if projects and isinstance(projects.get("value"), list):
        for item in projects["value"]:
            title = _flatten(item.get("title")) or "Project"
            desc = _flatten(item.get("description")) or ""
            
            from services.resume_intelligence import ResumeIntelligenceService
            desc_html = ResumeIntelligenceService.parse_experience_description_to_html(desc)
            
            Project.objects.create(
                profile=profile,
                title=title[:255],
                description=desc_html
            )

    # 7. Sync Certifications
    profile.certifications.all().delete()
    certifications = validated_data.get("certifications", {})
    if certifications and isinstance(certifications.get("value"), list):
        for item in certifications["value"]:
            name = _flatten(item.get("name")) or "Certification"
            org = _flatten(item.get("issuing_organization")) or "Accredited Body"
            i_date = parse_date_robust(_flatten(item.get("issue_date")))
            
            from services.resume_intelligence import ResumeIntelligenceService
            name_html = ResumeIntelligenceService.parse_experience_description_to_html(name)
            
            Certification.objects.create(
                profile=profile,
                name=name_html[:255],
                issuing_organization=org[:255],
                issue_date=i_date
            )

    return profile
