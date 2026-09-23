import os
import re
import io
import time
import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ParseoraException(Exception):
    """Base exception for Parseora integration errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, request_id: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


class ParseoraAuthError(ParseoraException):
    """Raised when authentication with Parseora fails."""
    pass


class ParseoraUnavailableError(ParseoraException):
    """Raised when Parseora API is unreachable or unavailable."""
    pass


class ParseoraTimeoutError(ParseoraException):
    """Raised when Parseora API times out."""
    pass


class ParseoraService:
    """
    Clean integration service for Parseora Document Intelligence Platform.
    Communicates with Parseora REST API for resume/CV parsing and extracts
    structured entities mapped directly to TalentVault Candidate models.
    """

    @classmethod
    def get_api_url(cls) -> str:
        url = getattr(settings, 'PARSEORA_API_URL', None) or os.environ.get('PARSEORA_API_URL') or "http://127.0.0.1:8001"
        return url.rstrip('/')

    @classmethod
    def get_api_key(cls) -> Optional[str]:
        return getattr(settings, 'PARSEORA_API_KEY', None) or os.environ.get('PARSEORA_API_KEY')

    @classmethod
    def get_timeout(cls) -> float:
        return float(getattr(settings, 'PARSEORA_TIMEOUT', None) or os.environ.get('PARSEORA_TIMEOUT', 45.0))

    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.get_api_key())

    @classmethod
    def parse_resume(
        cls,
        file_bytes: bytes,
        filename: str,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Sends uploaded CV file as multipart/form-data to POST {PARSEORA_API_URL}/api/v1/parse.
        
        Headers:
            X-API-Key: {PARSEORA_API_KEY}
            
        Form Data:
            document_type=resume
            target_language=en
            extract_tables=true
            extract_images=false
            extract_evidence=true
            ocr_mode=auto
            async_job=false
            
        Returns:
            Structured JSON dictionary returned from Parseora.
        """
        api_url = cls.get_api_url()
        api_key = cls.get_api_key()
        endpoint = f"{api_url}/api/v1/parse"
        req_timeout = timeout or cls.get_timeout()

        if not api_key:
            logger.error("[PARSEORA] PARSEORA_API_KEY is not configured.")
            raise ParseoraAuthError("Parseora API Key is not configured.")

        # Determine MIME type safely
        ext = filename.split('.')[-1].lower() if '.' in filename else 'pdf'
        mime_map = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'doc': 'application/msword',
            'rtf': 'application/rtf',
            'txt': 'text/plain',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'webp': 'image/webp',
            'tiff': 'image/tiff'
        }
        content_type = mime_map.get(ext, 'application/octet-stream')

        files = {
            'file': (filename, io.BytesIO(file_bytes), content_type)
        }

        data = {
            'document_type': 'resume',
            'target_language': 'en',
            'extract_tables': 'true',
            'extract_images': 'true',
            'extract_evidence': 'true',
            'ocr_mode': 'auto',
            'async_job': 'false'
        }

        headers = {
            'X-API-Key': api_key
        }

        logger.info(f"[PARSEORA REQUEST] Sending resume parsing request to {endpoint} for file: {filename} ({len(file_bytes)} bytes)")
        t0 = time.time()

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                files=files,
                data=data,
                timeout=req_timeout
            )
        except requests.exceptions.Timeout as e:
            elapsed = time.time() - t0
            logger.error(f"[PARSEORA TIMEOUT] Request timed out after {elapsed:.2f}s for file {filename}")
            raise ParseoraTimeoutError(f"Parseora request timed out after {elapsed:.2f}s.") from e
        except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
            elapsed = time.time() - t0
            logger.error(f"[PARSEORA CONNECTION ERROR] Failed to reach Parseora at {endpoint} after {elapsed:.2f}s: {type(e).__name__}")
            raise ParseoraUnavailableError(f"Parseora service is unavailable at {api_url}.") from e

        elapsed = time.time() - t0
        status_code = response.status_code

        # Attempt to parse JSON response safely
        try:
            res_json = response.json()
        except Exception:
            res_json = {}

        request_id = res_json.get('request_id') or response.headers.get('X-Request-Id')

        logger.info(f"[PARSEORA RESPONSE] Status: {status_code} | Request ID: {request_id} | Elapsed: {elapsed:.2f}s | File: {filename}")

        if status_code in (401, 403):
            err_msg = res_json.get('message') or "Invalid, revoked, or expired Parseora API Key."
            logger.error(f"[PARSEORA AUTH ERROR] Status: {status_code} | Request ID: {request_id} | Message: {err_msg}")
            raise ParseoraAuthError(err_msg, status_code=status_code, request_id=request_id)

        if status_code != 200:
            err_msg = res_json.get('message') or res_json.get('error') or f"Parseora returned HTTP {status_code}"
            logger.error(f"[PARSEORA API ERROR] Status: {status_code} | Request ID: {request_id} | Message: {err_msg}")
            raise ParseoraException(err_msg, status_code=status_code, request_id=request_id)

        return res_json

    @staticmethod
    def _extract_scalar(field: Any, default: Any = None) -> Any:
        """Helper to extract scalar string or numeric value from Parseora nested entity field."""
        if field is None:
            return default
        if isinstance(field, dict):
            for k in ['value', 'normalized_value', 'original_value', 'evidence']:
                if field.get(k) is not None:
                    return field[k]
            return default
        return field

    # Section headings / contact markers that must never be stored as a
    # structured record (education degree, etc.).
    _NON_RECORD_TEXT_RE = re.compile(
        r'@|https?://|www\.|linkedin|github|'
        r'\b(?:gmail|yahoo|outlook|hotmail)\b|'
        r'\b(?:summary|objective|profile|experience|education|skills|certifications?|'
        r'languages?|interests?|hobbies|personal\s+details?|declaration|references?|'
        r'achievements?|projects?)\b',
        re.IGNORECASE,
    )

    @classmethod
    def _is_contact_or_heading(cls, text: str) -> bool:
        """True when a value is contact/header text or a section heading rather
        than a genuine structured record field."""
        if not text:
            return False
        s = str(text).strip()
        if not s:
            return False
        if cls._NON_RECORD_TEXT_RE.search(s):
            return True
        if '|' in s:
            return True
        if re.search(r'\+?\d[\d\s\-()]{7,}', s):
            return True
        # A long prose sentence is not a degree/institution.
        if len(s.split()) > 8 and s.rstrip().endswith('.'):
            return True
        return False

    # Labels that must never be accepted as a candidate name.
    _NON_NAME_LABELS = {
        'district', 'taluk', 'taluka', 'tehsil', 'village', 'post', 'po', 'pin',
        'pincode', 'zip', 'street', 'road', 'lane', 'block', 'sector', 'state',
        'country', 'city', 'town', 'area', 'locality', 'landmark', 'house', 'flat',
        'apartment', 'building', 'floor', 'near', 'opposite', 'address', 'contact',
        'email', 'phone', 'mobile', 'dob', 'birth', 'birthday', 'marital', 'married',
        'single', 'father', 'mother', 'spouse', 'religion', 'caste', 'category',
        'signature', 'declaration', 'reference', 'references', 'summary', 'objective',
        'profile', 'experience', 'education', 'skills', 'certifications',
        'achievements', 'projects', 'languages', 'interests', 'hobbies',
        'curriculum', 'vitae', 'resume', 'cv', 'unknown', 'candidate', 'none', 'null',
    }

    @classmethod
    def _is_plausible_person_name(cls, name: Any) -> bool:
        """Generic guard: reject address/section labels and non-name fragments."""
        if not name or not isinstance(name, str):
            return False
        clean = " ".join(name.strip().split())
        if not clean:
            return False
        if '@' in clean or 'http' in clean.lower():
            return False
        if clean.replace(' ', '').replace('-', '').isdigit():
            return False
        alpha_tokens = [
            re.sub(r'[^A-Za-z]', '', tok)
            for tok in re.split(r'\s+', clean)
        ]
        alpha_tokens = [tok for tok in alpha_tokens if len(tok) >= 2]
        if not alpha_tokens:
            return False
        if all(tok.lower() in cls._NON_NAME_LABELS for tok in alpha_tokens):
            return False
        return True

    @classmethod
    def _is_valid_skill(cls, skill: str) -> bool:
        """Rejects responsibility sentences / bullet-merged blobs masquerading as skills."""
        if not skill:
            return False
        s = str(skill).strip().strip('•●○■◆▪-*\u2022\uf0b7\uf0d8\uf0a7')
        if not s or len(s) < 2:
            return False
        if '@' in s or 'http' in s.lower():
            return False
        if '•' in s:
            return False
        words = s.split()
        if len(words) > 6:
            return False
        if s.rstrip().endswith('.'):
            return False
        if re.search(r'\b(?:responsible|managed|handled|developed|ensured|maintained|'
                     r'coordinated|assisted|worked|achieved|delivered)\b', s, re.IGNORECASE):
            return False
        return True

    @classmethod
    def map_response_to_talentvault(cls, res_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps Parseora structured JSON response directly into TalentVault's standard
        parsed_data candidate schema and model fields.
        """
        cand = res_json.get('candidate') or res_json.get('data', {}).get('candidate') or {}

        # 1. Experiences
        experiences: List[Dict[str, Any]] = []
        raw_exp = (
            res_json.get('experience') or 
            res_json.get('work_experience') or 
            res_json.get('data', {}).get('experience') or 
            res_json.get('data', {}).get('work_experience') or 
            []
        )
        if isinstance(raw_exp, list):
            for item in raw_exp:
                if not isinstance(item, dict):
                    continue
                desig = cls._extract_scalar(item.get('job_title')) or cls._extract_scalar(item.get('designation')) or cls._extract_scalar(item.get('normalized_job_title')) or ''
                comp = cls._extract_scalar(item.get('company_name')) or cls._extract_scalar(item.get('company')) or ''
                loc = cls._extract_scalar(item.get('location')) or ''
                s_date = cls._extract_scalar(item.get('start_date')) or ''
                e_date = cls._extract_scalar(item.get('end_date')) or ''
                is_curr = bool(item.get('is_current'))
                dur = cls._extract_scalar(item.get('duration_formatted')) or cls._extract_scalar(item.get('duration')) or ''

                desc = item.get('description') or ''
                resps = item.get('responsibilities') or []
                if isinstance(resps, list) and resps:
                    bullet_desc = '\n'.join([f"• {r.strip()}" for r in resps if isinstance(r, str) and r.strip()])
                    desc = bullet_desc if not desc else f"{desc}\n{bullet_desc}"

                experiences.append({
                    'designation': str(desig)[:100],
                    'company': str(comp)[:100],
                    'location': str(loc)[:100],
                    'duration': str(dur),
                    'description': str(desc),
                    'start_date': str(s_date) if s_date else '',
                    'end_date': str(e_date) if e_date else '',
                    'is_current': is_curr
                })

        # Calculate experience years and durations using TalentVault intelligence
        from services.resume_intelligence import ResumeIntelligenceService
        total_exp = 0.0
        for exp in experiences:
            s_date_str = ResumeIntelligenceService.normalize_date_to_string(exp['start_date'], is_end=False)
            e_date_str = ResumeIntelligenceService.normalize_date_to_string(exp['end_date'], is_end=True)
            if s_date_str:
                exp['start_date'] = s_date_str
                exp['end_date'] = e_date_str or "Present"
                exp['duration'] = ResumeIntelligenceService.get_duration_display(s_date_str, e_date_str)
                total_exp += ResumeIntelligenceService.calculate_experience_years_from_dates(s_date_str, e_date_str)
        total_exp = round(total_exp, 1)

        # Fallback to Parseora total_experience_years if calculated is 0
        api_total_exp = cls._extract_scalar(cand.get('total_experience_years'))
        if total_exp == 0.0 and api_total_exp is not None:
            try:
                total_exp = round(float(api_total_exp), 1)
            except (ValueError, TypeError):
                pass

        api_rel_exp = cls._extract_scalar(cand.get('relevant_experience_years'))
        relevant_exp = total_exp
        if api_rel_exp is not None:
            try:
                relevant_exp = round(float(api_rel_exp), 1)
            except (ValueError, TypeError):
                relevant_exp = total_exp

        # 2. Educations
        educations: List[Dict[str, Any]] = []
        raw_edu = (
            res_json.get('education') or 
            res_json.get('data', {}).get('education') or 
            []
        )
        if isinstance(raw_edu, list):
            for item in raw_edu:
                if not isinstance(item, dict):
                    continue
                deg = cls._extract_scalar(item.get('degree')) or cls._extract_scalar(item.get('raw_degree')) or ''
                inst = cls._extract_scalar(item.get('college')) or cls._extract_scalar(item.get('university')) or cls._extract_scalar(item.get('institution')) or ''
                fos = cls._extract_scalar(item.get('field_of_study')) or cls._extract_scalar(item.get('branch')) or 'General'
                score = str(cls._extract_scalar(item.get('cgpa')) or cls._extract_scalar(item.get('percentage')) or cls._extract_scalar(item.get('score')) or cls._extract_scalar(item.get('grade')) or '')
                s_year = str(cls._extract_scalar(item.get('start_year')) or cls._extract_scalar(item.get('start_date')) or '')
                e_year = str(cls._extract_scalar(item.get('end_year')) or cls._extract_scalar(item.get('passing_year')) or cls._extract_scalar(item.get('end_date')) or '')

                if s_year and not e_year:
                    e_year = s_year
                    s_year = ""

                # Never let contact/header text or a section heading become an
                # education record (e.g. a stray email/phone line).
                if cls._is_contact_or_heading(deg) and cls._is_contact_or_heading(inst):
                    continue
                if cls._is_contact_or_heading(deg) and not str(inst).strip():
                    continue

                educations.append({
                    'degree': str(deg)[:100],
                    'institution': str(inst)[:100],
                    'field_of_study': str(fos)[:100],
                    'score': str(score)[:20],
                    'start_date': s_year,
                    'end_date': e_year
                })

        # 3. Skills (Normalized and Deduplicated)
        from apps.candidates.utils import normalize_skills
        skills_raw = res_json.get('skills') or res_json.get('data', {}).get('skills') or {}
        all_skills_list: List[str] = []
        if isinstance(skills_raw, dict):
            for key in ['technical_skills', 'soft_skills', 'domain_skills', 'frameworks', 'databases', 'cloud_skills', 'tools', 'libraries']:
                items = skills_raw.get(key) or []
                if isinstance(items, list):
                    all_skills_list.extend([str(s).strip() for s in items if s])
            if 'all_skills' in skills_raw and isinstance(skills_raw['all_skills'], list):
                for sk in skills_raw['all_skills']:
                    if isinstance(sk, dict) and 'name' in sk:
                        all_skills_list.append(str(sk['name']).strip())
                    elif isinstance(sk, str):
                        all_skills_list.append(sk.strip())
        elif isinstance(skills_raw, list):
            for sk in skills_raw:
                if isinstance(sk, dict) and 'name' in sk:
                    all_skills_list.append(str(sk['name']).strip())
                elif isinstance(sk, str):
                    all_skills_list.append(sk.strip())

        # Never turn a responsibility sentence / bullet blob into a skill.
        all_skills_list = [s for s in all_skills_list if cls._is_valid_skill(s)]

        normalized_skills = normalize_skills(all_skills_list)

        # 4. Projects
        projects: List[Dict[str, Any]] = []
        raw_proj = (
            res_json.get('projects') or 
            res_json.get('data', {}).get('projects') or 
            []
        )
        if isinstance(raw_proj, list):
            for item in raw_proj:
                if not isinstance(item, dict):
                    continue
                projects.append({
                    'title': str(cls._extract_scalar(item.get('title')) or '')[:255],
                    'description': str(cls._extract_scalar(item.get('description')) or ''),
                    'link': str(cls._extract_scalar(item.get('link')) or cls._extract_scalar(item.get('url')) or '')[:255]
                })

        # 5. Certifications
        certifications: List[Dict[str, Any]] = []
        raw_cert = (
            res_json.get('certifications') or 
            res_json.get('data', {}).get('certifications') or 
            []
        )
        if isinstance(raw_cert, list):
            for item in raw_cert:
                if not isinstance(item, dict):
                    continue
                certifications.append({
                    'name': str(cls._extract_scalar(item.get('name')) or cls._extract_scalar(item.get('title')) or '')[:255],
                    'issuing_organization': str(cls._extract_scalar(item.get('issuing_organization')) or cls._extract_scalar(item.get('organization')) or cls._extract_scalar(item.get('issuer')) or '')[:255],
                    'issue_date': str(cls._extract_scalar(item.get('issue_date')) or cls._extract_scalar(item.get('date')) or '')
                })

        # 6. Personal Info & Contacts
        raw_phone = str(cls._extract_scalar(cand.get('phone')) or cls._extract_scalar(cand.get('alternate_phone')) or '')
        phone_digits = re.sub(r'\D', '', raw_phone)
        phone_clean = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits

        raw_email = str(cls._extract_scalar(cand.get('email')) or '')
        email_clean = raw_email.strip()[:254]

        raw_name = str(cls._extract_scalar(cand.get('name')) or '').strip()
        # Never invent a candidate name and never accept an address/section
        # label. If Parseora has no usable name, leave it empty so the
        # downstream validated fallbacks can run (and may legitimately end up
        # null). Placeholder labels are treated as missing.
        if not cls._is_plausible_person_name(raw_name):
            raw_name = ""
        name_clean = raw_name[:255] if raw_name else ""

        linkedin_clean = str(cls._extract_scalar(cand.get('linkedin')) or '').strip()[:200]
        portfolio_clean = str(cls._extract_scalar(cand.get('portfolio')) or cls._extract_scalar(cand.get('website')) or '').strip()[:200]
        github_clean = str(cls._extract_scalar(cand.get('github')) or '').strip()[:200]

        loc = str(
            cls._extract_scalar(cand.get('current_location')) or 
            cls._extract_scalar(cand.get('location')) or 
            cls._extract_scalar(cand.get('city')) or 
            cls._extract_scalar(cand.get('address')) or 
            'Unknown'
        ).strip()[:255]
        pref_loc = str(cls._extract_scalar(cand.get('preferred_location')) or '').strip()[:255]

        curr_comp = str(
            cls._extract_scalar(cand.get('current_company')) or 
            (experiences[0]['company'] if experiences else '')
        ).strip()[:255]
        curr_desig = str(
            cls._extract_scalar(cand.get('current_designation')) or 
            (experiences[0]['designation'] if experiences else 'Professional')
        ).strip()[:255]

        # Clean CTCs
        def clean_ctc(val):
            if not val:
                return None
            val_str = str(val).lower()
            matches = re.findall(r'[\d\.]+', val_str)
            if not matches:
                return None
            try:
                num = float(matches[0])
                if 'lpa' in val_str or 'lakh' in val_str or num < 100.0:
                    return num * 100000
                return num
            except Exception:
                return None

        def clean_notice_period(val):
            if not val:
                return 30
            val_str = str(val).lower()
            matches = re.findall(r'\d+', val_str)
            if not matches:
                return 30
            try:
                return int(matches[0])
            except Exception:
                return 30

        current_ctc_val = clean_ctc(cls._extract_scalar(cand.get('current_ctc')))
        expected_ctc_val = clean_ctc(cls._extract_scalar(cand.get('expected_ctc')))
        notice_period_val = clean_notice_period(cls._extract_scalar(cand.get('notice_period')))
        dob_val = cls._extract_scalar(cand.get('date_of_birth'))
        gender_val = cls._extract_scalar(cand.get('gender'))

        summary = str(
            cls._extract_scalar(cand.get('summary')) or 
            cls._extract_scalar(cand.get('objective')) or 
            cls._extract_scalar(res_json.get('summary')) or 
            ''
        ).strip()

        highest_qual = educations[0]['degree'] if educations else ''
        college_uni = educations[0]['institution'] if educations else ''

        personal_info = {
            'name': name_clean,
            'email': email_clean,
            'phone': phone_clean,
            'location': loc,
            'address': str(cls._extract_scalar(cand.get('address')) or '')[:255],
            'city': str(cls._extract_scalar(cand.get('city')) or '')[:255],
            'state': str(cls._extract_scalar(cand.get('state')) or '')[:255],
            'country': str(cls._extract_scalar(cand.get('country')) or '')[:255],
            'preferred_location': pref_loc,
            'linkedin_url': linkedin_clean,
            'portfolio_url': portfolio_clean,
            'github_url': github_clean,
            'current_company': curr_comp,
            'current_designation': curr_desig,
            'total_experience': total_exp,
            'relevant_experience': relevant_exp,
            'highest_qualification': highest_qual,
            'college_university': college_uni,
            'notice_period': notice_period_val,
            'date_of_birth': dob_val,
            'gender': gender_val,
            'current_ctc': current_ctc_val,
            'expected_ctc': expected_ctc_val,
        }

        # 7. Extract Profile Photo (genuine candidate portrait only).
        # Raw bytes are kept OUT of the JSON payload; only a metadata reference
        # travels with parsed_data.
        photo_bytes: Optional[bytes] = None
        photo_ext: str = 'jpg'
        photo_info: Dict[str, Any] = {'available': False}
        photo_data = (
            cand.get('photo') or
            cand.get('profile_photo') or
            res_json.get('photo') or
            res_json.get('data', {}).get('photo') or
            res_json.get('data', {}).get('candidate', {}).get('photo') or
            {}
        )

        # Accept either a structured object, a base64 data string or a URL.
        if isinstance(photo_data, str) and photo_data.strip():
            candidate_str = photo_data.strip()
            if candidate_str.lower().startswith(('http://', 'https://')):
                photo_data = {'available': True, 'url': candidate_str}
            else:
                photo_data = {'available': True, 'base64': candidate_str}

        if isinstance(photo_data, dict):
            asset_type = str(
                photo_data.get('type') or photo_data.get('kind') or photo_data.get('category') or ''
            ).strip().lower()
            rejected_asset_types = {
                'logo', 'icon', 'avatar', 'signature', 'qr', 'qrcode', 'qr_code',
                'graphic', 'decoration', 'decorative', 'banner', 'watermark', 'stamp',
            }
            declared_available = bool(photo_data.get('available', True))
            reference_url = photo_data.get('url') or photo_data.get('storage_url')
            reference_path = (
                photo_data.get('storage_path') or photo_data.get('path') or photo_data.get('key')
            )
            is_genuine = declared_available and asset_type not in rejected_asset_types

            if is_genuine:
                b64_str = photo_data.get('base64') or photo_data.get('data') or ''
                if isinstance(b64_str, (bytes, bytearray, memoryview)):
                    photo_bytes = bytes(b64_str)
                elif isinstance(b64_str, str) and b64_str:
                    try:
                        import base64
                        b64_data = b64_str
                        if ',' in b64_str:
                            header, b64_data = b64_str.split(',', 1)
                            header_lower = header.lower()
                            if 'png' in header_lower:
                                photo_ext = 'png'
                            elif 'webp' in header_lower:
                                photo_ext = 'webp'
                            elif 'jpeg' in header_lower or 'jpg' in header_lower:
                                photo_ext = 'jpg'
                        photo_bytes = base64.b64decode(b64_data)
                    except Exception as e:
                        logger.warning(f"[PARSEORA] Failed to decode photo base64: {e}")
                        photo_bytes = None

            has_reference = bool(reference_url or reference_path)
            photo_info = {
                'available': bool(is_genuine and (photo_bytes or has_reference)),
                'source': photo_data.get('source') or 'parseora',
                'page': photo_data.get('page'),
                'bounding_box': photo_data.get('bounding_box') or photo_data.get('bbox'),
                'confidence': photo_data.get('confidence'),
                'url': reference_url,
                'storage_path': reference_path,
                'asset_type': asset_type or 'portrait',
            }

        personal_info['has_photo'] = bool(photo_info.get('available'))
        if photo_info.get('url'):
            personal_info['photo_url'] = photo_info['url']
        if photo_info.get('storage_path'):
            personal_info['photo_reference'] = photo_info['storage_path']

        # Format achievements and languages
        achievements_raw = res_json.get('achievements') or res_json.get('awards') or []
        achievements = [str(a).strip() for a in achievements_raw if a] if isinstance(achievements_raw, list) else []

        languages_raw = res_json.get('languages') or []
        languages = [str(l).strip() for l in languages_raw if l] if isinstance(languages_raw, list) else []

        request_id = res_json.get('request_id', '')

        return {
            'personal_info': personal_info,
            'summary': summary,
            'skills': normalized_skills,
            'education': educations,
            'experience': experiences,
            'projects': projects,
            'certifications': certifications,
            'achievements': achievements,
            'languages': languages,
            'current_ctc': current_ctc_val,
            'expected_ctc': expected_ctc_val,
            'notice_period': notice_period_val,
            'date_of_birth': dob_val,
            'gender': gender_val,
            'photo_bytes': photo_bytes,
            'photo_ext': photo_ext,
            'photo_info': photo_info,
            'metadata': {
                'parsed_by': 'Parseora',
                'request_id': request_id,
                'parsed_at': datetime.now().isoformat()
            }
        }
