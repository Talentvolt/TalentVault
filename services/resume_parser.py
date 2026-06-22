import random

def parse_resume(file_path):
    """
    Parses a resume (PDF/DOCX) and extracts key information.
    Mock implementation for now.
    """
    return {
        'name': f"Extracted Candidate {random.randint(1000, 9999)}",
        'email': f"candidate.{random.randint(100, 999)}@example.com",
        'phone': '+1234567890',
        'skills': 'Python, Django, React, SQL, AWS, Docker',
        'experience': 'Software Engineer - 5 years',
        'education': 'B.Tech in Computer Science',
        'certifications': 'AWS Certified Solutions Architect'
    }

def process_bulk_resumes(zip_file_path):
    """
    Processes a ZIP containing multiple resumes.
    Mock implementation for now.
    """
    candidates = []
    for i in range(5):
        candidates.append(parse_resume(f"resume_{i}.pdf"))
    return candidates
