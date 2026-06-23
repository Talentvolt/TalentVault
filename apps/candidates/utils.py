import re
import zipfile
import io
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

def process_resume_file(file_obj, filename, overwrite=False):
    # Support images, screenshots, scanned PDFs, etc.
    ext = filename.split('.')[-1].lower()
    if ext not in ['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'tiff', 'bmp']:
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

    from services.resume_intelligence import ResumeIntelligenceService
    
    # 1. OCR Engine Execution
    try:
        logger.info(f"[PARSER OCR RUNNING] Running OCR pipeline for: {filename}")
        ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, filename)
        text = ocr_result["text"]
        logger.info(f"[PARSER OCR SUCCESS] Engine: {ocr_result['engine']}, Confidence: {ocr_result['confidence']}%")
    except Exception as e:
        logger.error(f"[PARSER OCR FAILURE] Failed during OCR pipeline on {filename}: {str(e)}", exc_info=True)
        return None, "OCR_FAILED"
    
    # 2. NLP Extraction
    try:
        logger.info(f"[PARSER NLP RUNNING] Extracting data from OCR text length: {len(text)}")
        parsed_data = ResumeIntelligenceService.parse_resume_nlp(text)
        info = parsed_data['personal_info']
        logger.info(f"[PARSER NLP SUCCESS] Parsed info for candidate: {info.get('name')}")
    except Exception as e:
        logger.error(f"[PARSER NLP FAILURE] Failed running NLP parser: {str(e)}", exc_info=True)
        return None, "NLP_FAILED"
    
    email = info.get('email', '')
    phone = info.get('phone', '')
    
    # Normalize placeholders
    if email == "candidate@example.com":
        email = ""
    if phone == "9876543210":
        phone = ""
        
    if not email:
        # Avoid using absolute hash without dynamic text to generate a unique but reproducible identifier
        email = f"unknown_{abs(hash(text or filename))}@example.com"

    logger.info(f"[PARSER CONTACTS] Extracted Email: {email}, Extracted Phone: {phone}")
    print(f"[PARSER CONTACTS] Extracted Email: {email}, Extracted Phone: {phone}")
        
    try:
        from django.db import transaction
        with transaction.atomic():
            # Check for duplicates:
            # Match on email (which is unique) OR match on phone number ONLY if we have a valid, non-empty phone number
            if phone:
                existing_user = User.objects.filter(Q(email=email) | Q(phone_number=phone)).first()
            else:
                existing_user = User.objects.filter(email=email).first()
            
            if existing_user and not overwrite:
                DuplicateResumeLog.objects.create(
                    email=email,
                    phone=phone,
                    filename=filename,
                    action_taken='SKIPPED'
                )
                logger.warning(f"[PARSER DUPLICATE] Candidate already exists (skipped): {email} / {phone}")
                print(f"[PARSER DUPLICATE] Candidate already exists (skipped): {email} / {phone}")
                return None, "DUPLICATE"
                
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
                
            profile, created_profile = CandidateProfile.objects.get_or_create(user=user)
            
            candidate_name = info.get('name', '')
            if not ResumeIntelligenceService.is_valid_name(candidate_name):
                candidate_name = ResumeIntelligenceService.extract_candidate_name(text)
                
            profile.full_name = candidate_name
            profile.summary = parsed_data.get('summary', '')
            profile.location = info.get('location') or "Unknown"
            profile.current_salary = parsed_data.get('current_ctc')
            profile.expected_salary = parsed_data.get('expected_ctc')
            profile.notice_period = parsed_data.get('notice_period', 30)
            profile.total_experience = info.get('total_experience', 0.0)
            
            profile.current_company = info.get('current_company')
            profile.current_designation = info.get('current_designation') or "Professional"

            # Save fields for Resume Intelligence
            profile.parsed_json = parsed_data
            profile.ocr_engine = ocr_result.get("engine", "None")
            profile.ocr_confidence = Decimal(str(ocr_result.get("confidence", 0.0)))
            profile.resume_type = ocr_result.get("resume_type", "UNKNOWN")
            
            # Store initial Version 1
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
            
            # Save the original file content
            try:
                profile.resume.save(filename, ContentFile(file_bytes), save=False)
                profile.original_file.save("original_" + filename, ContentFile(file_bytes), save=False)
                logger.info(f"[PARSER FILE SAVE SUCCESS] Physical files saved: {filename}")
                print(f"[PARSER FILE SAVE SUCCESS] Physical files saved: {filename}")
            except Exception as e:
                logger.error(f"[PARSER FILE SAVE ERROR] Error saving resume file to disk: {str(e)}", exc_info=True)
                print(f"[PARSER FILE SAVE ERROR] Error saving resume file to disk: {str(e)}")
            
            profile.save()
            logger.info(f"[PARSER DB PROFILE] CandidateProfile saved successfully for: {profile.full_name} (ID: {profile.id})")
            print(f"[PARSER DB PROFILE] CandidateProfile saved successfully for: {profile.full_name} (ID: {profile.id})")
            
            # Clear and update related data
            profile.skills.all().delete()
            for skill in parsed_data.get('skills', []):
                CandidateSkill.objects.get_or_create(profile=profile, skill_name=skill.title())
                
            profile.experiences.all().delete()
            for exp in parsed_data.get('experience', []):
                Experience.objects.create(
                    profile=profile,
                    company_name=exp.get('company', '')[:100],
                    designation=exp.get('designation', '')[:100],
                    description=exp.get('description', ''),
                    start_date=parse_date_robust(exp.get('start_date'), datetime.now().date()),
                    end_date=parse_date_robust(exp.get('end_date'), datetime.now().date())
                )
                
            profile.educations.all().delete()
            for edu in parsed_data.get('education', []):
                Education.objects.create(
                    profile=profile,
                    institution=edu.get('institution', '')[:100],
                    degree=edu.get('degree', '')[:100],
                    field_of_study=edu.get('field_of_study', '')[:100],
                    start_date=parse_date_robust(edu.get('start_date'), datetime.now().date()),
                    end_date=parse_date_robust(edu.get('end_date'), datetime.now().date())
                )
                
            profile.projects.all().delete()
            for proj in parsed_data.get('projects', []):
                Project.objects.create(
                    profile=profile,
                    title=proj.get('title', '')[:255],
                    description=proj.get('description', ''),
                    link=proj.get('link', '')
                )
                
            profile.certifications.all().delete()
            for cert in parsed_data.get('certifications', []):
                Certification.objects.create(
                    profile=profile,
                    name=cert.get('name', '')[:255],
                    issuing_organization=cert.get('issuing_organization', '')[:255],
                    issue_date=parse_date_robust(cert.get('issue_date'), datetime.now().date())
                )
                
            # Calculate and save ATS suitability score
            try:
                from services.candidate_matching_service import CandidateMatchingService
                CandidateMatchingService.update_ats_scores(candidate_id=profile.id)
            except Exception as e:
                logger.error(f"[PARSER ATS ERROR] Failed updating ATS suitability index score: {str(e)}", exc_info=True)
                print(f"[PARSER ATS ERROR] Failed updating ATS suitability index score: {str(e)}")
            
            logger.info(f"[PARSER COMPLETED] Candidate Profile created/updated successfully: {profile.id}")
            print(f"[PARSER COMPLETED] Candidate Profile created successfully: ID={profile.id}, Name={profile.full_name}")
            return profile, "SUCCESS"
            
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"[PARSER DATABASE SAVE FAILURE] Failed saving candidate database records for {filename}: {str(e)}\n{tb}", exc_info=True)
        print(f"[PARSER DATABASE SAVE FAILURE] Exception Traceback in process_resume_file:\n{tb}")
        return None, "SAVE_FAILED"

def handle_resume_upload(uploaded_file, overwrite=False):
    results = {'created': [], 'duplicates': 0, 'errors': 0}
    
    if uploaded_file.name.lower().endswith('.zip'):
        with zipfile.ZipFile(uploaded_file, 'r') as z:
            for filename in z.namelist():
                if filename.lower().endswith(('.pdf', '.docx', '.png', '.jpg', '.jpeg')):
                    with z.open(filename) as f:
                        file_obj = io.BytesIO(f.read()) 
                        profile, status = process_resume_file(file_obj, filename, overwrite)
                        if status == "SUCCESS":
                            results['created'].append(profile)
                        elif status == "DUPLICATE":
                            results['duplicates'] += 1
                        else:
                            results['errors'] += 1
    else:
        profile, status = process_resume_file(uploaded_file, uploaded_file.name, overwrite)
        if status == "SUCCESS":
            results['created'].append(profile)
        elif status == "DUPLICATE":
            results['duplicates'] += 1
        else:
            results['errors'] += 1
            
    return results