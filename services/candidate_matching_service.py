from typing import Dict, List, Any
from decimal import Decimal
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile

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
        job_skills = {s.strip().lower() for s in job.skills.values_list('skill_name', flat=True) if s.strip()}
        candidate_skills = {s.strip().lower() for s in candidate.skills.values_list('skill_name', flat=True) if s.strip()}
        
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
        educations = candidate.educations.all()
        if educations.exists():
            degrees = [e.degree.lower().replace('.', '').strip() for e in educations if e.degree]
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
        for exp in candidate.experiences.all():
            candidate_text += f" {(exp.designation or '')} {(exp.company_name or '')} {(exp.description or '')}".lower()
        for proj in candidate.projects.all():
            candidate_text += f" {(proj.title or '')} {(proj.description or '')}".lower()
        for cert in candidate.certifications.all():
            candidate_text += f" {(cert.name or '')}".lower()
        for skill in candidate.skills.all():
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
        cert_count = candidate.certifications.count()
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
        if candidate.experiences.exists():
            completeness += 1
        if candidate.educations.exists():
            completeness += 1
        if candidate.skills.exists():
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
        apps = Application.objects.all()
        if candidate_id:
            apps = apps.filter(candidate_id=candidate_id)
        if job_id:
            apps = apps.filter(job_id=job_id)
            
        for app in apps:
            analysis = CandidateMatchingService.calculate_job_ats_score(app.candidate, app.job)
            app.match_score = analysis['total_score']
            app.save()
            
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
            candidate.save()
