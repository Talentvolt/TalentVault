from typing import Dict, List, Any
from decimal import Decimal
import re
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile

# --- Smart Job Recommendation / Intent-Based Ranking constants ---

# Deterministic related-role groups so titles like "Python Developer",
# "Django Developer" and "Backend Engineer" are understood as related.
ROLE_GROUPS = [
    {'python', 'django', 'flask', 'fastapi', 'backend', 'server', 'api', 'postgresql', 'mysql'},
    {'frontend', 'react', 'angular', 'vue', 'javascript', 'node', 'ui', 'web'},
    {'data', 'scientist', 'machine', 'learning', 'ml', 'ai', 'analyst', 'analytics', 'deep', 'nlp'},
    {'java', 'spring', 'microservice', 'backend', 'kotlin', 'hibernate'},
    {'mobile', 'android', 'ios', 'flutter', 'swift', 'reactnative', 'react', 'native'},
    {'devops', 'aws', 'cloud', 'kubernetes', 'docker', 'infra', 'sre', 'azure', 'gcp', 'jenkins'},
    {'sales', 'business', 'bde', 'marketing', 'bdm', 'account', 'field'},
    {'hr', 'recruit', 'talent', 'people', 'hrbp', 'hiring'},
    {'design', 'ux', 'ui', 'graphic', 'product', 'visual'},
    {'qa', 'testing', 'test', 'automation', 'selenium', 'quality'},
    {'support', 'customer', 'service', 'bpo', 'voice', 'chat', 'helpdesk'},
    {'finance', 'account', 'accountant', 'accounts', 'tax', 'audit', 'cma', 'ca'},
]

# Words that do not help distinguish job roles.
GENERIC_TITLE_WORDS = {
    'developer', 'engineer', 'senior', 'junior', 'lead', 'manager', 'associate',
    'specialist', 'executive', 'consultant', 'analyst', 'professional', 'staff',
    'technical', 'software', 'principal', 'trainee', 'intern', 'head', 'director',
    'vp', 'cto', 'ceo', 'full', 'stack', 'sr', 'jr', 'ii', 'iii', 'i',
}

SKILL_ALIASES = {
    'js': 'javascript', 'nodejs': 'node', 'node.js': 'node', 'reactjs': 'react',
    'postgres': 'postgresql', 'k8s': 'kubernetes', 'golang': 'go', 'ml': 'machine learning',
    'ai': 'artificial intelligence', 'c++': 'cpp', 'c#': 'csharp', '.net': 'dotnet',
    'html5': 'html', 'css3': 'css', 'typescript': 'ts',
}


class CandidateMatchingService:
    """
    Service to calculate the match score between a Job and a Candidate.
    
    Weights:
    - Skills: 70%
    - Experience: 20%
    - Location: 5%
    - Notice Period: 5%
    """

    @staticmethod
    def calculate_match_score(job: Job, candidate: CandidateProfile) -> Dict[str, Any]:
        skill_score = CandidateMatchingService._calculate_skill_score(job, candidate)
        experience_score = CandidateMatchingService._calculate_experience_score(job, candidate)
        location_score = CandidateMatchingService._calculate_location_score(job, candidate)
        notice_score = CandidateMatchingService._calculate_notice_score(job, candidate)

        # Requirement: Candidate experience must be >= required experience
        if candidate.total_experience < job.min_experience:
            experience_score = Decimal('0.0')
            # If experience is below minimum, they are excluded (total score will reflect this)
        
        # Requirement: Candidate must have at least 70% skill match (which is 49.0 points out of 70)
        # _calculate_skill_score already returns 0 if match < 70% of 100% (so < 49 points)
        
        total_score = skill_score + experience_score + location_score + notice_score

        return {
            "candidate_id": str(candidate.id),
            "match_score": float(total_score),
            "skill_score": float(skill_score),
            "experience_score": float(experience_score),
            "location_score": float(location_score),
            "notice_score": float(notice_score),
            "is_qualified": skill_score > 0 and candidate.total_experience >= job.min_experience
        }

    @staticmethod
    def _calculate_skill_score(job: Job, candidate: CandidateProfile) -> Decimal:
        job_skills = set(job.skills.values_list('skill_name', flat=True))
        if not job_skills:
            return Decimal('70.0')

        candidate_skills = set(candidate.skills.values_list('skill_name', flat=True))
        matched_skills = job_skills.intersection(candidate_skills)
        
        match_percent = (Decimal(len(matched_skills)) / Decimal(len(job_skills)))
        
        # Rule: Candidate must have at least 70% skill match
        if match_percent < Decimal('0.7'):
            return Decimal('0.0')

        score = match_percent * Decimal('70.0')
        return min(score, Decimal('70.0'))

    @staticmethod
    def _calculate_experience_score(job: Job, candidate: CandidateProfile) -> Decimal:
        # Rule: Candidate experience must be >= required experience
        if candidate.total_experience >= job.min_experience:
            return Decimal('20.0')
        return Decimal('0.0')

    @staticmethod
    def _calculate_location_score(job: Job, candidate: CandidateProfile) -> Decimal:
        if job.is_remote:
            return Decimal('5.0')
        
        if job.location.lower() == candidate.location.lower():
            return Decimal('5.0')
        
        return Decimal('0.0')

    @staticmethod
    def _calculate_notice_score(job: Job, candidate: CandidateProfile) -> Decimal:
        if candidate.is_immediate_joiner or candidate.notice_period <= 15:
            return Decimal('5.0')
        elif candidate.notice_period <= 30:
            return Decimal('4.0')
        elif candidate.notice_period <= 60:
            return Decimal('2.0')
        
        return Decimal('1.0')

    @staticmethod
    def calculate_ats_score(candidate: CandidateProfile, job: Job = None) -> int:
        analysis = CandidateMatchingService.calculate_job_ats_score(candidate, job)
        return analysis['total_score']

    @staticmethod
    def calculate_job_ats_score(candidate: CandidateProfile, job: Job = None) -> dict:
        import re
        from django.utils.html import strip_tags
        from apps.jobs.models import Job
        
        if not job:
            job = Job.objects.filter(status='ACTIVE').first() or Job.objects.first()
            
        if not job:
            return {
                'skills_score': 0,
                'skills_ratio': "0/0",
                'experience_score': 0,
                'education_score': 0,
                'keyword_score': 0,
                'keyword_ratio': "0/0",
                'location_score': 0,
                'certifications_score': 0,
                'completeness_score': 0,
                'title_score': 0,
                'ai_semantic_score': 0,
                'total_score': 0,
                'match_label': "Weak Match",
                'badge_class': "bg-danger text-white"
            }
            
        # 1. Skills Match (40% Weight)
        job_skills = {s.skill_name.strip().lower() for s in job.skills.all() if s.skill_name and s.skill_name.strip()}
        candidate_skills = {s.skill_name.strip().lower() for s in candidate.skills.all() if s.skill_name and s.skill_name.strip()}
        
        if job_skills:
            # Substring / partial match of skills
            matched_skills = set()
            for js in job_skills:
                for cs in candidate_skills:
                    if js in cs or cs in js:
                        matched_skills.add(js)
                        break
            skills_score = (len(matched_skills) / len(job_skills)) * 40
            skills_ratio = f"{len(matched_skills)}/{len(job_skills)}"
        else:
            # Fallback if no skill tags defined: extract domain skills from description
            skill_keywords = [
                'python', 'java', 'django', 'react', 'javascript', 'node', 'mern', 'aws', 'docker', 'kubernetes', 'sql', 
                'pharma', 'nurse', 'sales', 'hr', 'php', 'laravel', 'flutter', 'android', 'ios', 'data science', 'ml', 'ai'
            ]
            job_desc_lower = (job.description or "").lower() + " " + (job.title or "").lower()
            extracted_job_skills = {s for s in skill_keywords if s in job_desc_lower}
            if extracted_job_skills:
                # Substring / partial match of fallback skills
                matched_skills = set()
                for js in extracted_job_skills:
                    for cs in candidate_skills:
                        if js in cs or cs in js:
                            matched_skills.add(js)
                            break
                skills_score = (len(matched_skills) / len(extracted_job_skills)) * 40
                skills_ratio = f"{len(matched_skills)}/{len(extracted_job_skills)}"
            else:
                skills_score = 40
                skills_ratio = "0/0"
                
        # 2. Experience Match (20% Weight)
        if job.min_experience == 0:
            exp_score = 20
        else:
            ratio = float(candidate.total_experience or 0) / float(job.min_experience)
            exp_score = min(ratio * 20, 20)
            
        # 3. Education Match (10% Weight)
        educations_list = list(candidate.educations.all())
        if educations_list:
            degrees = [e.degree.lower().replace('.', '').strip() for e in educations_list if e.degree]
            if any(any(x in deg for x in ['phd', 'doctorate', 'master', 'mba', 'mtech', 'ms', 'pg', 'post graduate']) for deg in degrees):
                edu_score = 10
            elif any(any(x in deg for x in ['bachelor', 'btech', 'be', 'bs', 'bca', 'bba', 'bcom', 'bsc', 'graduate', 'degree']) for deg in degrees):
                edu_score = 8
            elif any('diploma' in deg for deg in degrees):
                edu_score = 6
            elif any(any(x in deg for x in ['school', 'high school', 'cbse', 'icse', 'hsc', 'ssc']) for deg in degrees):
                edu_score = 4
            else:
                edu_score = 5
        else:
            edu_score = 0
            
        # 4. Keyword Match (15% Weight)
        job_desc = job.description or ""
        job_desc_clean = strip_tags(job_desc)
        job_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', job_desc_clean.lower()))
        
        # Extended stop words list to filter out HTML parameters and general noise
        stop_words = {
            'with', 'they', 'that', 'this', 'from', 'have', 'your', 'will', 'about', 'their', 'there', 
            'would', 'should', 'could', 'about', 'here', 'more', 'some', 'than', 'them', 'then', 'these',
            'what', 'when', 'where', 'who', 'why', 'how', 'description', 'requirements', 'responsibilities',
            'duties', 'qualifications', 'experience', 'skills', 'benefits', 'company', 'candidate', 'position',
            'role', 'team', 'work', 'working', 'apply', 'please', 'required', 'preferred', 'highly', 'strong',
            'ability', 'excellent', 'years', 'using', 'build', 'building', 'join', 'plus', 'preferred'
        }
        job_words = job_words - stop_words
        
        candidate_text = f"{(candidate.summary or '')} {(candidate.current_designation or '')} {(candidate.current_company or '')}".lower()
        experiences_list = list(candidate.experiences.all())
        projects_list = list(candidate.projects.all())
        certifications_list = list(candidate.certifications.all())
        candidate_skills_list = list(candidate.skills.all())

        for exp in experiences_list:
            candidate_text += f" {(exp.designation or '')} {(exp.company_name or '')} {(exp.description or '')}".lower()
        for proj in projects_list:
            candidate_text += f" {(proj.title or '')} {(proj.description or '')}".lower()
        for cert in certifications_list:
            candidate_text += f" {(cert.name or '')}".lower()
        for skill in candidate_skills_list:
            candidate_text += f" {skill.skill_name.lower()}"
            
        if job_words:
            matched_words = {w for w in job_words if w in candidate_text}
            keyword_score = (len(matched_words) / len(job_words)) * 15
            keyword_ratio = f"{len(matched_words)}/{len(job_words)}"
        else:
            keyword_score = 15
            keyword_ratio = "0/0"
            
        # 5. Location Match (5% Weight)
        if job.is_remote:
            loc_score = 5
        elif job.location and candidate.location:
            j_loc = job.location.strip().lower()
            c_loc = candidate.location.strip().lower()
            if j_loc in c_loc or c_loc in j_loc:
                loc_score = 5
            else:
                loc_score = 0
        else:
            loc_score = 0
            
        # 6. Certifications Match (5% Weight)
        cert_count = len(certifications_list)
        if cert_count >= 2:
            cert_score = 5
        elif cert_count == 1:
            cert_score = 3
        else:
            cert_score = 0
            
        # 7. Resume Completeness (5% Weight)
        completeness = 0
        if candidate.resume:
            completeness += 1
        if candidate.summary and candidate.summary.strip():
            completeness += 1
        if experiences_list:
            completeness += 1
        if educations_list:
            completeness += 1
        if candidate_skills_list:
            completeness += 1
            
        completeness_score = completeness
        
        # 8. Extra Metrics (for Final Report: Title match and AI semantic match)
        title_score = 0
        if job.title and candidate.current_designation:
            j_title_words = set(re.findall(r'\w+', job.title.lower()))
            c_desig_words = set(re.findall(r'\w+', candidate.current_designation.lower()))
            common = j_title_words.intersection(c_desig_words)
            if common:
                title_score = int(round((len(common) / len(j_title_words)) * 10))
                
        ai_semantic_score = 0
        if job_words:
            overlap = job_words.intersection(set(re.findall(r'\b[a-zA-Z]{4,}\b', candidate_text)))
            ai_semantic_score = int(round((len(overlap) / len(job_words)) * 10))
            
        total_ats = int(round(skills_score + exp_score + edu_score + keyword_score + loc_score + cert_score + completeness_score))
        total_ats = min(max(total_ats, 0), 100)
        
        # Match Label and Badge Class
        if total_ats >= 90:
            match_label = "Excellent Match"
            badge_class = "bg-success text-white"
        elif total_ats >= 75:
            match_label = "Good Match"
            badge_class = "bg-primary text-white"
        elif total_ats >= 60:
            match_label = "Average Match"
            badge_class = "bg-warning text-dark"
        else:
            match_label = "Weak Match"
            badge_class = "bg-danger text-white"
            
        return {
            'skills_score': int(round(skills_score)),
            'skills_ratio': skills_ratio,
            'experience_score': int(round(exp_score)),
            'education_score': int(round(edu_score)),
            'keyword_score': int(round(keyword_score)),
            'keyword_ratio': keyword_ratio,
            'location_score': int(round(loc_score)),
            'certifications_score': int(round(cert_score)),
            'completeness_score': int(round(completeness_score)),
            'title_score': title_score,
            'ai_semantic_score': ai_semantic_score,
            'total_score': total_ats,
            'match_label': match_label,
            'badge_class': badge_class
        }

    @staticmethod
    def update_ats_scores(candidate_id=None, job_id=None):
        from apps.applications.models import Application
        from apps.candidates.models import CandidateProfile
        
        # 1. Sync Application match_score values
        apps = Application.objects.select_related('candidate', 'job').all()
        if candidate_id:
            apps = apps.filter(candidate_id=candidate_id)
        if job_id:
            apps = apps.filter(job_id=job_id)
            
        for app in apps:
            analysis = CandidateMatchingService.calculate_job_ats_score(app.candidate, app.job)
            app.match_score = analysis['total_score']
            app.save(update_fields=['match_score'])
            
        # 2. Sync CandidateProfile.ats_score to be the highest matching application or 0
        candidates = CandidateProfile.objects.all()
        if candidate_id:
            candidates = candidates.filter(id=candidate_id)
            
        for candidate in candidates:
            cand_apps = Application.objects.filter(candidate=candidate)
            if cand_apps.exists():
                highest_score = max(cand_apps.values_list('match_score', flat=True))
                candidate.ats_score = highest_score
            else:
                candidate.ats_score = CandidateMatchingService.calculate_ats_score(candidate, None)
            candidate.save(update_fields=['ats_score'])

    # ------------------------------------------------------------------
    # Smart Job Recommendation & Intent-Based Ranking
    # ------------------------------------------------------------------

    @staticmethod
    def _canonical_skill(name):
        n = (name or '').strip().lower()
        return SKILL_ALIASES.get(n, n)

    @staticmethod
    def _skill_tokens(name):
        n = CandidateMatchingService._canonical_skill(name)
        if not n:
            return set()
        return {t for t in re.findall(r'[a-z0-9+#.]+', n) if len(t) >= 2}

    @staticmethod
    def _title_tokens(text):
        if not text:
            return set()
        tokens = set(re.findall(r'[a-z0-9+#]+', (text or '').lower()))
        return {t for t in tokens if t not in GENERIC_TITLE_WORDS}

    @staticmethod
    def _location_tokens(text):
        if not text:
            return set()
        return {t for t in re.findall(r'[a-z0-9]+', (text or '').lower()) if len(t) >= 2}

    @staticmethod
    def _role_similarity(tokens_a, tokens_b):
        if not tokens_a or not tokens_b:
            return False
        if tokens_a & tokens_b:
            return True
        for group in ROLE_GROUPS:
            if (group & tokens_a) and (group & tokens_b):
                return True
        return False

    @staticmethod
    def _employment_compatible(cand_emp_type, job_type):
        cand = (cand_emp_type or '').upper()
        job = (job_type or '').upper()
        if not cand:
            return False
        if cand == job:
            return True
        # Remote-ish candidate preferences map loosely.
        remote_cand = cand in ('REMOTE', 'WORK_FROM_HOME', 'WFH')
        remote_job = job in ('REMOTE', 'WORK_FROM_HOME', 'WFH')
        return remote_cand and remote_job

    @staticmethod
    def _match_label(score):
        if score >= 85:
            return "Excellent Match", "bg-success text-white"
        if score >= 70:
            return "Good Match", "bg-primary text-white"
        if score >= 50:
            return "Average Match", "bg-warning text-dark"
        return "Weak Match", "bg-danger text-white"

    @staticmethod
    def invalidate_recommendations(candidate):
        try:
            from django.core.cache import cache
            cache.delete(f"candidate_recommended_jobs_{candidate.id}")
        except Exception:
            pass

    @staticmethod
    def record_job_search_intent(user, query, filters):
        """
        Persists a candidate's job-search intent as an additional ranking signal.
        Repeated searches of the same role are naturally weighted by recency + count.
        """
        if not user or not user.is_authenticated:
            return
        query = (query or '').strip()
        filters = filters or {}
        if not query and not any(filters.values()):
            return
        try:
            from apps.candidates.models import RecentCandidateSearch
            RecentCandidateSearch.objects.create(
                user=user,
                search_query=query,
                selected_tags=[],
                filters_payload=filters,
            )
            # Keep only the most recent 20 signals.
            keep_ids = list(
                RecentCandidateSearch.objects.filter(user=user)
                .order_by('-created_at')
                .values_list('id', flat=True)[:20]
            )
            RecentCandidateSearch.objects.filter(user=user).exclude(id__in=keep_ids).delete()
        except Exception:
            pass

    @staticmethod
    def build_candidate_intent(candidate):
        from apps.candidates.models import RecentCandidateSearch

        intent = {
            'skills': set(),
            'preferred_tokens': set(),
            'preferred_role_label': '',
            'current_tokens': set(),
            'current_role_label': '',
            'exp_desigs': [],
            'locations': set(),
            'search_terms': [],
            'search_skills': set(),
            'search_locations': set(),
            'saved_applied_titles': [],
            'expected_salary': None,
            'employment_type': '',
            'total_experience': 0,
            'prefer_remote': False,
        }

        # Skills (typed + AI/original parsed skills)
        for s in candidate.skills.all():
            intent['skills'] |= CandidateMatchingService._skill_tokens(s.skill_name)
        for raw in list(candidate.ai_skills or []) + list(candidate.original_skills or []):
            intent['skills'] |= CandidateMatchingService._skill_tokens(str(raw))

        # Preferred / current designation
        preferred_role = candidate.preferred_job_role or candidate.current_designation or ''
        intent['preferred_role_label'] = preferred_role
        intent['preferred_tokens'] = CandidateMatchingService._title_tokens(preferred_role)
        intent['current_role_label'] = candidate.current_designation or ''
        intent['current_tokens'] = CandidateMatchingService._title_tokens(candidate.current_designation or '')

        # Experience designations
        for exp in candidate.experiences.all():
            tokens = CandidateMatchingService._title_tokens(exp.designation or '')
            if tokens:
                intent['exp_desigs'].append(tokens)

        # Locations
        intent['locations'] = CandidateMatchingService._location_tokens(candidate.location)
        if candidate.preferred_location:
            intent['locations'] |= CandidateMatchingService._location_tokens(candidate.preferred_location)
        if candidate.employment_type in ('REMOTE', 'WORK_FROM_HOME', 'CONTRACT') or candidate.willing_to_relocate:
            intent['prefer_remote'] = True

        # Salary
        intent['expected_salary'] = candidate.expected_salary or candidate.current_salary
        intent['employment_type'] = candidate.employment_type or ''
        intent['total_experience'] = candidate.total_experience or 0

        # Recent job-search intent (recency-weighted)
        searches = list(
            RecentCandidateSearch.objects.filter(user=candidate.user).order_by('-created_at')[:10]
        )
        total = len(searches)
        for idx, rs in enumerate(searches):
            weight = 1.0 - (idx * 0.6 / max(total, 1))  # most recent ~1.0
            weight = max(weight, 0.4)
            q = (rs.search_query or '').strip()
            if q:
                tokens = CandidateMatchingService._title_tokens(q)
                if tokens:
                    intent['search_terms'].append((tokens, weight))
            fp = rs.filters_payload or {}
            skills_text = fp.get('skills') or fp.get('skill') or ''
            for part in str(skills_text).split(','):
                intent['search_skills'] |= CandidateMatchingService._skill_tokens(part)
            loc = fp.get('location') or fp.get('preferred_location') or ''
            if loc:
                intent['search_locations'] |= CandidateMatchingService._location_tokens(loc)
            title = fp.get('title') or fp.get('designation') or ''
            if title:
                tokens = CandidateMatchingService._title_tokens(title)
                if tokens:
                    intent['search_terms'].append((tokens, weight))

        # Saved / applied job titles as preference signals
        try:
            for sj in candidate.saved_jobs.select_related('job').all():
                tokens = CandidateMatchingService._title_tokens(sj.job.title if sj.job else '')
                if tokens:
                    intent['saved_applied_titles'].append(tokens)
        except Exception:
            pass
        try:
            for app in candidate.job_applications.select_related('job').all():
                tokens = CandidateMatchingService._title_tokens(app.job.title if app.job else '')
                if tokens:
                    intent['saved_applied_titles'].append(tokens)
        except Exception:
            pass

        intent['has_intent'] = bool(
            intent['skills']
            or intent['preferred_tokens']
            or intent['current_tokens']
            or intent['exp_desigs']
            or intent['search_terms']
            or intent['search_skills']
            or intent['search_locations']
            or intent['saved_applied_titles']
        )
        return intent

    @staticmethod
    def _score_job(job, intent):
        job_skills = set()
        for s in job.skills.all():
            job_skills |= CandidateMatchingService._skill_tokens(s.skill_name)
        for s in job.get_required_skills_list:
            job_skills |= CandidateMatchingService._skill_tokens(s)
        for s in job.get_preferred_skills_list:
            job_skills |= CandidateMatchingService._skill_tokens(s)

        job_title_tokens = CandidateMatchingService._title_tokens(job.title)
        job_desc_lower = (job.description or '').lower()

        score = 0.0
        reason = ''

        # 1. Explicit preferred designation / search intent (highest priority)
        if intent['preferred_tokens'] and CandidateMatchingService._role_similarity(job_title_tokens, intent['preferred_tokens']):
            score += 30
            if not reason:
                reason = f"Matches your preferred {intent['preferred_role_label']} role"

        # 2. Recent search intent
        search_hit = False
        for q_tokens, weight in intent['search_terms']:
            if not q_tokens:
                continue
            if (q_tokens & job_title_tokens) or any(tok in job_desc_lower for tok in q_tokens):
                score += 18 * weight
                search_hit = True
                break
        if intent['search_skills']:
            overlap = intent['search_skills'] & job_skills
            if overlap:
                score += min(12, 4 * len(overlap))
                search_hit = True
        if search_hit and not reason:
            reason = "Matches your recent search"

        # 3. Saved/applied jobs as preference signal
        for title_tokens in intent['saved_applied_titles']:
            if CandidateMatchingService._role_similarity(job_title_tokens, title_tokens):
                score += 10
                if not reason:
                    reason = "Matches your saved/applied jobs"
                break

        # 4. Current / previous designation match
        for dt in [intent['current_tokens']] + intent['exp_desigs']:
            if dt and CandidateMatchingService._role_similarity(job_title_tokens, dt):
                score += 15
                if not reason and intent['current_role_label']:
                    reason = f"Matches your {intent['current_role_label']} experience"
                break

        # 5. Skills match
        if job_skills:
            matched = job_skills & intent['skills']
            if matched:
                ratio = len(matched) / len(job_skills)
                score += ratio * 25
                if not reason:
                    top_skills = sorted(matched)[:2]
                    reason = f"Matches your {' + '.join(top_skills)} experience"
        elif intent['skills']:
            score += 6

        # 6. Experience compatibility
        try:
            cand_exp = float(intent['total_experience'] or 0)
        except (TypeError, ValueError):
            cand_exp = 0.0
        jmin = int(job.min_experience or 0)
        jmax = int(job.max_experience or 0)
        if jmin == 0 and jmax == 0:
            score += 6
        elif jmax and cand_exp > jmax:
            score += 2
        elif cand_exp >= jmin:
            score += 10

        # 7. Location / remote compatibility
        if job.is_remote or (job.work_mode or '').upper() == 'REMOTE':
            score += 8
            if intent['prefer_remote'] and not reason:
                reason = "Matches your remote preference"
        else:
            jloc = CandidateMatchingService._location_tokens(job.location)
            if jloc and (jloc & intent['locations']):
                score += 8
                if not reason:
                    reason = "Matches your preferred location"
            elif intent['search_locations'] and jloc and (jloc & intent['search_locations']):
                score += 8
                if not reason:
                    reason = "Matches your recent search"

        # 8. Salary compatibility (only when data exists)
        if intent['expected_salary']:
            try:
                exp_sal = Decimal(intent['expected_salary'])
                if job.min_salary is not None and job.max_salary is not None:
                    if job.min_salary <= exp_sal <= job.max_salary:
                        score += 5
                elif job.min_salary is not None and exp_sal >= job.min_salary:
                    score += 5
                elif job.max_salary is not None and exp_sal <= job.max_salary:
                    score += 3
            except Exception:
                pass

        # 9. Employment type compatibility
        if intent['employment_type'] and CandidateMatchingService._employment_compatible(intent['employment_type'], job.job_type):
            score += 5

        return min(score, 100.0), reason

    @staticmethod
    def get_job_recommendations(candidate, limit=5):
        from apps.jobs.models import Job

        intent = CandidateMatchingService.build_candidate_intent(candidate)

        if not intent['has_intent']:
            # Fallback: existing ATS-based ranking when no resume/profile intent exists.
            return CandidateMatchingService._fallback_recommendations(candidate, limit)

        jobs = list(
            Job.objects.filter(status='ACTIVE')
            .select_related('company', 'client')
            .prefetch_related('skills')
            .order_by('-created_at')[:200]
        )

        cand_skills_raw = {s.skill_name.strip().lower() for s in candidate.skills.all() if s.skill_name and s.skill_name.strip()}

        scored = []
        for job in jobs:
            score, reason = CandidateMatchingService._score_job(job, intent)
            if score < 20:
                continue  # clearly irrelevant — excluded from AI recommendations

            job_skills_list = [s.skill_name.strip() for s in job.skills.all() if s.skill_name and s.skill_name.strip()]
            missing_skills = [s for s in job_skills_list if s.lower() not in cand_skills_raw]

            label, badge = CandidateMatchingService._match_label(score)
            scored.append({
                'job': job,
                'match_score': int(round(score)),
                'total_score': int(round(score)),
                'match_label': label,
                'badge_class': badge,
                'missing_skills': missing_skills,
                'reason': reason,
            })

        scored.sort(key=lambda x: (-x['match_score'], -int(x['job'].created_at.timestamp())))
        return scored[:limit]

    @staticmethod
    def _fallback_recommendations(candidate, limit=5):
        from apps.jobs.models import Job
        jobs = list(
            Job.objects.filter(status='ACTIVE')
            .select_related('company', 'client')
            .prefetch_related('skills')
            .order_by('-created_at')[:20]
        )
        c_skills_lower = {s.skill_name.strip().lower() for s in candidate.skills.all() if s.skill_name and s.skill_name.strip()}
        recommended = []
        for job in jobs:
            analysis = CandidateMatchingService.calculate_job_ats_score(candidate, job)
            score = analysis['total_score']
            job_skills_list = [s.skill_name.strip() for s in job.skills.all() if s.skill_name and s.skill_name.strip()]
            missing_skills = [s for s in job_skills_list if s.lower() not in c_skills_lower]
            recommended.append({
                'job': job,
                'match_score': score,
                'total_score': score,
                'match_label': analysis['match_label'],
                'badge_class': analysis['badge_class'],
                'missing_skills': missing_skills,
                'reason': '',
            })
        recommended.sort(key=lambda x: x['match_score'], reverse=True)
        return recommended[:limit]

    @staticmethod
    def get_recommended_jobs(candidate, limit=5):
        from django.core.cache import cache
        cache_key = f"candidate_recommended_jobs_{candidate.id}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        final_result = CandidateMatchingService.get_job_recommendations(candidate, limit=limit)
        cache.set(cache_key, final_result, 60)
        return final_result
