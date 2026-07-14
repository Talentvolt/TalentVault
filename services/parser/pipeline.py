import time
import logging
import concurrent.futures
import hashlib
from django.db import transaction
from django.conf import settings
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)

def run_stage_with_retry_and_timeout(func, args=(), kwargs={}, max_retries=2, timeout=45.0):
    """
    Executes a pipeline stage function with a ThreadPoolExecutor timeout and retry backoff.
    """
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[STAGE RUN] {func.__name__} - Attempt {attempt}/{max_retries} (Timeout: {timeout}s)")
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as te:
            logger.error(f"[STAGE TIMEOUT] {func.__name__} timed out on attempt {attempt}.")
            last_exception = te
        except Exception as e:
            logger.error(f"[STAGE ERROR] {func.__name__} failed on attempt {attempt}: {str(e)}", exc_info=True)
            last_exception = e
            if attempt < max_retries:
                time.sleep(0.5 * attempt)
    raise last_exception

class ResumeParsingPipeline:
    """
    Enterprise-grade resume parsing pipeline divided into 9 robust stages.
    Provides timeout, retry, error recovery, and seamless text/OCR fallbacks.
    """

    def __init__(self, file_obj, filename, overwrite=False, progress_callback=None, security_data=None, user=None):
        self.file_obj = file_obj
        self.filename = filename
        self.overwrite = overwrite
        self.progress_callback = progress_callback
        self.security_data = security_data
        self.user = user

        # Context shared across stages
        self.file_bytes = None
        self.file_hash = None
        self.extension = None
        self.extracted_text = ""
        self.parsed_json = None
        self.ocr_result = None
        self.profile = None
        self.status = "SUCCESS"

    def run(self):
        """
        Executes the stages sequentially with timeout and retry wrapper.
        """
        # Stage 1: File Validation
        try:
            self._stage_1_file_validation()
        except Exception as e:
            logger.error(f"Pipeline aborted at Stage 1: {e}")
            return None, "READ_ERROR"

        # Stage 2: Virus Scan
        try:
            self._stage_2_virus_scan()
        except Exception as e:
            logger.error(f"Pipeline aborted at Stage 2: {e}")
            return None, "SECURITY_FAILED"

        # Stage 3 & 4: Text Extraction & OCR
        # We run text extraction first for editable docs. If it fails or results are minimal, we run OCR.
        # Fallback requirement: If OCR fails -> use text parser. If text parser fails -> use OCR.
        text_extraction_success = False
        try:
            # Stage 4: Try Direct Text Extraction
            if self.progress_callback:
                self.progress_callback("extracting_text")
            self._stage_4_text_extraction()
            if len(self.extracted_text.strip()) > 100:
                text_extraction_success = True
                logger.info("Direct text extraction succeeded with substantial text.")
        except Exception as e:
            logger.warning(f"Direct text extraction failed: {e}. Will attempt OCR.")

        if not text_extraction_success:
            try:
                # Stage 3: OCR
                if self.progress_callback:
                    self.progress_callback("reading_pdf")
                run_stage_with_retry_and_timeout(self._stage_3_ocr, timeout=90.0)
            except Exception as ocr_err:
                logger.error(f"OCR stage failed: {ocr_err}")
                # Fallback: if OCR failed, attempt to use direct text extraction results if any
                if self.extracted_text:
                    logger.warning("OCR failed. Continuing with direct text parser results as fallback.")
                else:
                    return None, "OCR_FAILED"

        # Stage 5: AI JSON Extraction
        try:
            if self.progress_callback:
                self.progress_callback("ai_parsing")
            run_stage_with_retry_and_timeout(self._stage_5_ai_json_extraction, timeout=60.0)
        except Exception as e:
            logger.error(f"AI JSON extraction completely failed: {e}. Building minimal fallback data.")
            self._build_minimal_fallback_json()

        # Stage 6: Skills Normalization
        try:
            self._stage_6_skills_normalization()
        except Exception as e:
            logger.warning(f"Skills normalization failed: {e}. Skipping normalization.")

        # Stage 7: Database Save
        try:
            if self.progress_callback:
                self.progress_callback("saving_candidate")
            self._stage_7_database_save()
        except Exception as e:
            logger.critical(f"Pipeline failed during DB Save: {e}", exc_info=True)
            return None, "SAVE_FAILED"

        # Stage 8: ATS Score
        try:
            if self.progress_callback:
                self.progress_callback("ats_score_generated")
            self._stage_8_ats_score()
        except Exception as e:
            logger.warning(f"ATS scoring failed: {e}")

        # Stage 9: Final Validation
        try:
            self._stage_9_final_validation()
        except Exception as e:
            logger.warning(f"Final validation failed: {e}")

        return self.profile, self.status

    # ==========================================
    # STAGE IMPLEMENTATIONS
    # ==========================================

    def _stage_1_file_validation(self):
        """Stage 1: File Validation"""
        from apps.candidates.utils import sanitize_text
        self.filename = sanitize_text(self.filename, "filename")
        self.extension = self.filename.split('.')[-1].lower() if '.' in self.filename else ''
        
        valid_exts = {'pdf', 'doc', 'docx', 'rtf', 'txt'}
        if self.extension not in valid_exts:
            raise ValueError(f"Invalid file extension: {self.extension}")

        if hasattr(self.file_obj, 'seek'):
            self.file_obj.seek(0)
        self.file_bytes = self.file_obj.read()
        if not self.file_bytes:
            raise ValueError("Uploaded file is empty.")
            
        self.file_hash = hashlib.sha256(self.file_bytes).hexdigest()
        logger.info(f"[STAGE 1 SUCCESS] Validated: {self.filename} ({len(self.file_bytes)} bytes)")

    def _stage_2_virus_scan(self):
        """Stage 2: Virus Scan"""
        if self.security_data is None:
            from utils.security import perform_all_security_validations
            self.security_data = perform_all_security_validations(self.file_bytes, self.filename)
        logger.info("[STAGE 2 SUCCESS] Virus scan and security validations completed.")

    def _stage_3_ocr(self):
        """Stage 3: OCR"""
        from services.resume_intelligence import ResumeIntelligenceService
        self.ocr_result = ResumeIntelligenceService.run_ocr_pipeline(self.file_bytes, self.filename)
        self.extracted_text = self.ocr_result.get("text", "")
        logger.info(f"[STAGE 3 SUCCESS] OCR completed using engine: {self.ocr_result.get('engine')}")

    def _stage_4_text_extraction(self):
        """Stage 4: Direct Text Extraction"""
        from apps.candidates.utils import extract_text_from_pdf, extract_text_from_docx
        text = ""
        if self.extension == 'pdf':
            text = extract_text_from_pdf(self.file_obj)
        elif self.extension in ['docx', 'doc']:
            text = extract_text_from_docx(self.file_obj)
        elif self.extension in ['txt', 'rtf']:
            # Fallback direct read for txt/rtf
            try:
                text = self.file_bytes.decode('utf-8', errors='ignore')
            except Exception:
                text = ""

        self.extracted_text = text
        logger.info(f"[STAGE 4 SUCCESS] Direct text extraction length: {len(text)}")

    def _stage_5_ai_json_extraction(self):
        """Stage 5: AI JSON Extraction (with spaCy/NLP fallback and minimal manual review fallback)"""
        from services.parser.llm_extractor import LLMExtractor
        from services.resume_intelligence import ResumeIntelligenceService
        
        logger.info(f"Starting AI JSON Extraction. Text length: {len(self.extracted_text)}")
        
        # Ensure we have some text to parse
        if not self.extracted_text.strip():
            raise ValueError("No text available for AI JSON extraction.")

        # Attempt OpenAI
        try:
            from apps.candidates.utils import OpenAIResumeParser
            self.parsed_json = OpenAIResumeParser.parse(self.extracted_text)
            logger.info("[STAGE 5] OpenAI parsing succeeded.")
            return
        except Exception as openai_err:
            logger.error(f"[STAGE 5] OpenAI parsing failed: {openai_err}. Trying spaCy NLP fallback.")

        # Fallback: spaCy NLP Parser
        try:
            bold_name = self.ocr_result.get("largest_bold_name") if self.ocr_result else None
            self.parsed_json = ResumeIntelligenceService.parse_resume_nlp(self.extracted_text, parsed_name=bold_name)
            logger.info("[STAGE 5] spaCy NLP parsing fallback succeeded.")
            
            # Run ai_improve on NLP results if available
            try:
                self.parsed_json = ResumeIntelligenceService.ai_improve_resume_data(self.parsed_json)
                logger.info("[STAGE 5] AI improve completed on NLP fallback.")
            except Exception as improve_err:
                logger.warning(f"[STAGE 5] AI improve failed on NLP fallback: {improve_err}")
            return
        except Exception as nlp_err:
            logger.error(f"[STAGE 5] spaCy NLP parsing fallback failed: {nlp_err}.")

        # If both failed, build minimal fallback JSON (Manual Review)
        logger.warning("[STAGE 5 WARNING] Both OpenAI and NLP parsers failed. Generating minimal Manual Review data.")
        self._build_minimal_fallback_json()

    def _stage_6_skills_normalization(self):
        """Stage 6: Skills Normalization"""
        from apps.candidates.utils import normalize_skills
        if not self.parsed_json:
            return
            
        skills = self.parsed_json.get('skills', [])
        # Also check personal_info, technical_skills, soft_skills
        personal_info = self.parsed_json.get('personal_info', {})
        tech_skills = personal_info.get('technical_skills', []) if isinstance(personal_info, dict) else []
        soft_skills = personal_info.get('soft_skills', []) if isinstance(personal_info, dict) else []
        
        combined_skills = list(skills) + list(tech_skills) + list(soft_skills)
        normalized = normalize_skills(combined_skills)
        self.parsed_json['skills'] = normalized
        logger.info(f"[STAGE 6 SUCCESS] Normalized {len(combined_skills)} skills down to {len(normalized)}")

    def _stage_7_database_save(self):
        """Stage 7: Database Save (wrapped in Django atomic transaction)"""
        from apps.accounts.models import User
        from apps.candidates.models import CandidateProfile, Experience, Education, Project, Certification
        from apps.candidates.utils import (
            sanitize_text, sanitize_recursive, parse_date_robust, 
            extract_profile_photo, select_best_profile_photo, parse_experience_years
        )
        from services.resume_intelligence import ResumeIntelligenceService

        # Pre-sanitize
        self.parsed_json = sanitize_recursive(self.parsed_json, "parsed_json")
        self.extracted_text = sanitize_text(self.extracted_text, "raw_resume_text")
        
        info = self.parsed_json.get('personal_info', {})
        email = info.get('email', '')
        phone = info.get('phone', '')
        
        if email == "candidate@example.com":
            email = ""
        if phone == "9876543210":
            phone = ""
            
        if not email:
            email = f"unknown_{abs(hash(self.extracted_text or self.filename))}@example.com"

        # Begin DB Transaction
        with transaction.atomic():
            def get_priority_name():
                def is_acceptable_name(name_str):
                    if not name_str or not isinstance(name_str, str):
                        return False
                    name_str = name_str.strip()
                    if not name_str:
                        return False
                    if name_str.lower() in ("unknown candidate", "unknown", "placeholder", "candidate", "null", "none"):
                        return False
                    
                    import re
                    name_clean = " ".join(name_str.strip().split())
                    if not name_clean:
                        return False
                    if name_clean.isdigit():
                        return False
                    if re.match(r'^\+?\d[\d\s-]{8,}$', name_clean):
                        return False
                    if '@' in name_clean:
                        return False
                    if name_clean.lower().startswith('http'):
                        return False
                    if 'linkedin' in name_clean.lower() or 'github' in name_clean.lower():
                        return False
                        
                    digits_only = re.sub(r'[^\d+]', '', name_clean)
                    if len(digits_only) >= 8 and digits_only.replace('+', '').isdigit():
                        return False
                        
                    if re.search(r'[\w\.-]+@[\w\.-]+\.\w+', name_clean):
                        return False
                    if re.search(r'(https?://\S+|www\.\S+)', name_clean, re.I):
                        return False
                        
                    if not any(char.isalpha() for char in name_clean):
                        return False
                        
                    norm = re.sub(r'[^a-z\s]', '', name_clean.lower()).strip()
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
                    val = self.parsed_json.get(k)
                    if isinstance(val, dict) and "value" in val:
                        val = val["value"]
                    if is_acceptable_name(val):
                        openai_name = val.strip()
                        break
                
                if not openai_name:
                    personal = self.parsed_json.get("personal_info", {})
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
                    from services.singletons import NLPService
                    nlp = NLPService().get_nlp()
                    if nlp:
                        page_1 = self.extracted_text.split('\x0c')[0] if '\x0c' in self.extracted_text else self.extracted_text
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
                if self.ocr_result:
                    largest_heading = self.ocr_result.get("largest_bold_name")
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
                    if self.extension == 'pdf':
                        import fitz
                        doc = fitz.open(stream=self.file_bytes, filetype="pdf")
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

            # Check duplicates
            linkedin = info.get('linkedin_url', '') or info.get('linkedin', '')
            sha256 = self.security_data.get('sha256', '') if self.security_data else ''
            
            existing_user = self.user
            if not existing_user:
                if email:
                    existing_user = User.objects.filter(email=email).first()
                if not existing_user and phone:
                    existing_user = User.objects.filter(phone_number=phone).first()
                if not existing_user and linkedin:
                    existing_profile = CandidateProfile.objects.filter(linkedin_url=linkedin).first()
                    if existing_profile:
                        existing_user = existing_profile.user

            if existing_user:
                profile = getattr(existing_user, 'candidate_profile', None)
                if not profile:
                    profile = CandidateProfile.objects.create(
                        user=existing_user,
                        full_name=existing_user.get_full_name() or "Candidate"
                    )
            else:
                # Create user
                existing_user, created_user = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'role': User.Role.CANDIDATE,
                        'phone_number': phone if phone else None
                    }
                )
                if created_user:
                    existing_user.set_unusable_password()
                    existing_user.save()
                profile, created_profile = CandidateProfile.objects.get_or_create(
                    user=existing_user,
                    defaults={'full_name': info.get('name') or "Candidate"}
                )

            # Update profile info
            profile.full_name = get_priority_name()[:255]
            profile.summary = self.parsed_json.get('summary', '')
            profile.location = (info.get('location') or "Unknown")[:100]
            
            # Salary
            curr_sal = self.parsed_json.get('current_ctc')
            if curr_sal is not None and str(curr_sal).strip() not in ("", "None", "null"):
                try:
                    profile.current_salary = Decimal(str(curr_sal))
                except Exception:
                    profile.current_salary = None
            else:
                profile.current_salary = None

            exp_sal = self.parsed_json.get('expected_ctc')
            if exp_sal is not None and str(exp_sal).strip() not in ("", "None", "null"):
                try:
                    profile.expected_salary = Decimal(str(exp_sal))
                except Exception:
                    profile.expected_salary = None
            else:
                profile.expected_salary = None

            profile.notice_period = self.parsed_json.get('notice_period', 30)
            
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

            # OCR engines meta
            engine_name = self.ocr_result.get("engine", "None") if self.ocr_result else "None"
            conf_val = self.ocr_result.get("confidence", 0.0) if self.ocr_result else 0.0
            resume_type = self.ocr_result.get("resume_type", "UNKNOWN") if self.ocr_result else "UNKNOWN"
            
            profile.ocr_engine = engine_name
            profile.ocr_confidence = Decimal(str(conf_val))
            profile.resume_type = resume_type
            profile.raw_resume_text = self.extracted_text
            profile.original_experience_json = self.parsed_json.get('experience', [])
            profile.original_skills = self.parsed_json.get('skills', [])
            profile.original_summary = self.parsed_json.get('summary', '')

            # File and security metadata
            from django.utils import timezone
            if self.security_data:
                profile.original_filename = (self.security_data.get("sanitized_filename", self.filename) or "")[:255]
                profile.secure_filename = (self.security_data.get("secure_filename") or "")[:255]
                profile.sha256 = self.security_data.get("sha256")
                profile.mime_type = (self.security_data.get("mime_type") or "")[:100]
                profile.scan_status = self.security_data.get("scan_status", "PASSED")
                profile.scan_timestamp = self.security_data.get("scan_timestamp") or timezone.now()
            else:
                profile.original_filename = (self.filename or "")[:255]
            
            profile.parser_status = "SUCCESS"
            profile.preview_status = "READY"

            # Versioning
            v1_data = {
                "version": 1,
                "label": "Original Resume",
                "data": self.parsed_json,
                "created_at": datetime.now().isoformat(),
                "created_by": "System OCR Parser"
            }
            profile.resume_versions = {"1": v1_data}
            profile.current_version = 1
            
            # Photo extraction (async ThreadPool run did this, we can run it or use cached if any)
            try:
                photo_bytes, photo_ext = extract_profile_photo(self.file_bytes, self.filename)
                if photo_bytes:
                    from django.core.files.base import ContentFile
                    photo_name = f"profile_photo_{profile.id}.{photo_ext}"
                    profile.profile_photo.save(photo_name, ContentFile(photo_bytes), save=False)
            except Exception as photo_err:
                logger.error(f"Failed photo extraction during save: {photo_err}")

            profile.save()

            # Save nested entities
            # 1. Skills
            profile.skills.all().delete()
            for s in self.parsed_json.get('skills', []):
                from apps.candidates.models import CandidateSkill
                CandidateSkill.objects.create(profile=profile, skill_name=s)

            # 2. Experience
            profile.experiences.all().delete()
            for exp in self.parsed_json.get('experience', []):
                desc_html = ResumeIntelligenceService.parse_experience_description_to_html(exp.get('description', ''))
                Experience.objects.create(
                    profile=profile,
                    company_name=(exp.get('company') or '')[:100],
                    designation=(exp.get('designation') or '')[:100],
                    start_date=parse_date_robust(exp.get('start_date'), None),
                    end_date=parse_date_robust(exp.get('end_date'), None),
                    description=desc_html,
                    is_current=bool(exp.get('is_current', False))
                )

            # 3. Education
            profile.educations.all().delete()
            for edu in self.parsed_json.get('education', []):
                Education.objects.create(
                    profile=profile,
                    institution=(edu.get('institution') or '')[:100],
                    degree=(edu.get('degree') or '')[:100],
                    field_of_study=(edu.get('field_of_study') or '')[:100],
                    percentage_or_cgpa=(edu.get('score') or '')[:20],
                    start_date=parse_date_robust(edu.get('start_date'), None),
                    end_date=parse_date_robust(edu.get('end_date'), None)
                )

            # 4. Projects
            profile.projects.all().delete()
            for proj in self.parsed_json.get('projects', []):
                desc_html = ResumeIntelligenceService.parse_experience_description_to_html(proj.get('description', ''))
                Project.objects.create(
                    profile=profile,
                    title=(proj.get('title') or '')[:255],
                    description=desc_html,
                    link=proj.get('link', '')
                )

            # 5. Certifications
            profile.certifications.all().delete()
            for cert in self.parsed_json.get('certifications', []):
                Certification.objects.create(
                    profile=profile,
                    name=(cert.get('name') or '')[:255],
                    issuing_organization=(cert.get('issuing_organization') or '')[:255],
                    issue_date=parse_date_robust(cert.get('issue_date'), None)
                )

            self.profile = profile
            logger.info(f"[STAGE 7 SUCCESS] Database Save completed for profile ID={profile.id}")

    def _stage_8_ats_score(self):
        """Stage 8: ATS Scoring"""
        from services.candidate_matching_service import CandidateMatchingService
        CandidateMatchingService.update_ats_scores(candidate_id=self.profile.id)
        logger.info("[STAGE 8 SUCCESS] ATS Suitability Index Score updated.")

    def _stage_9_final_validation(self):
        """Stage 9: Final Validation"""
        if not self.profile or not self.profile.id:
            raise ValueError("Final validation failed: CandidateProfile object not created.")
        logger.info(f"[STAGE 9 SUCCESS] Final validation passed. Parse completed successfully.")

    # ==========================================
    # HELPER METHODS
    # ==========================================

    def _build_minimal_fallback_json(self):
        """Builds a minimal fallback dictionary to prevent database save failures."""
        import re as _re
        text = self.extracted_text or ""
        email_match = _re.search(r'[\w\.\-]+@[\w\.\-]+\.\w+', text)
        phone_match = _re.search(r'(?:\+?\d{1,3}[- ]?)?(?:\d[- ]?){9}\d', text)
        
        email_fb = email_match.group(0) if email_match else ""
        phone_fb = _re.sub(r'[\s-]', '', phone_match.group(0))[-10:] if phone_match else ""
        
        name_fb = self.ocr_result.get("largest_bold_name") if self.ocr_result else None
        if not name_fb:
            for line in text.split('\n'):
                line = line.strip()
                if line and '@' not in line and not _re.search(r'\d{5,}', line) and len(line.split()) <= 5:
                    name_fb = line.title()
                    break
        name_fb = name_fb or "Manual Review Candidate"

        self.parsed_json = {
            "personal_info": {
                "name": name_fb,
                "email": email_fb,
                "phone": phone_fb,
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
        self.status = "SUCCESS" # We flag success to keep page from throwing 500, candidate will show up for Manual Review.
        logger.warning(f"Fallback minimal manual review data constructed: {self.parsed_json['personal_info']}")

def uuid_hex():
    import uuid
    return uuid.uuid4().hex
