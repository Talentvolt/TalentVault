import pytest
from services.resume_intelligence import ResumeIntelligenceService

def test_is_valid_name_blacklist():
    # Ignore resume titles and run-ons
    assert ResumeIntelligenceService.is_valid_name("CURRICULUM VITAE") is False
    assert ResumeIntelligenceService.is_valid_name("CURRICULUMVITAE") is False
    assert ResumeIntelligenceService.is_valid_name("RESUME") is False
    assert ResumeIntelligenceService.is_valid_name("BIODATA") is False
    assert ResumeIntelligenceService.is_valid_name("CV") is False
    assert ResumeIntelligenceService.is_valid_name("Rohan CV") is False
    # Valid name
    assert ResumeIntelligenceService.is_valid_name("ROHAN KUMAR") is True

def test_resume_parser_rohan_kumar_resume():
    resume_text = (
        "CURRICULUM VITAE\n"
        "ROHAN KUMAR\n"
        "Email: rohan.kumar@example.com\n"
        "Phone: +91 98765 43210\n"
        "Address: Sector 62, Noida, UP\n\n"
        "Career Objective:\n"
        "To work as a Hardware Design Engineer and contribute to semiconductor technology.\n\n"
        "Work Experience:\n"
        "Presently working as Hardware Design Engineer in Champion Semiconductor LLP - Aug 2023 to Present\n"
        "Worked as Junior Design Engineer at Champion Semiconductor LLP - Dec 2021 to Aug 2023\n\n"
        "Education:\n"
        "B.Tech in Electronics - 2021 - College of Engineering\n"
        "Diploma in Electronics - 2017 - State Polytechnic\n"
        "Intermediate - 2014 - City School\n"
        "High School - 2012 - City School\n"
    )
    
    parsed = ResumeIntelligenceService.parse_resume_nlp(resume_text)
    
    # 1. Candidate Name
    assert parsed["personal_info"]["name"] == "Rohan Kumar"
    
    # 2. Contact
    assert parsed["personal_info"]["email"] == "rohan.kumar@example.com"
    assert parsed["personal_info"]["phone"] == "9876543210"
    assert "Noida" in parsed["personal_info"]["city"] or "Noida" in parsed["personal_info"]["location"]
    assert "Noida" in parsed["personal_info"]["address"]
    
    # 3. Summary
    assert "contribution" in parsed["summary"].lower() or "contribute to semiconductor" in parsed["summary"].lower()
    assert "ROHAN KUMAR" not in parsed["summary"]
    
    # 4. Current Designation & Work Experience
    experiences = parsed["experience"]
    assert len(experiences) >= 2
    
    # Current job
    current_job = experiences[0]
    assert current_job["designation"] == "Hardware Design Engineer"
    assert current_job["company"] == "Champion Semiconductor LLP"
    assert current_job["start_date"] == "2023-08-01"
    
    # Previous job
    prev_job = experiences[1]
    assert prev_job["designation"] == "Junior Design Engineer"
    assert prev_job["company"] == "Champion Semiconductor LLP"
    assert prev_job["start_date"] == "2021-12-01"
    assert prev_job["end_date"] == "2023-08-31"

    # 5. Experience Calculation (Dec 2021–Aug 2023 & Aug 2023–Present)
    assert parsed["personal_info"]["total_experience"] > 0.0
    
    # 6. Education
    education = parsed["education"]
    assert len(education) >= 4
    
    improved = ResumeIntelligenceService.ai_improve_resume_data(parsed)
    improved_degrees = [edu["degree"] for edu in improved["education"]]
    
    assert "B.Tech" in improved_degrees
    assert "Diploma" in improved_degrees
    assert "Intermediate" in improved_degrees
    assert "High School" in improved_degrees


def test_resume_parser_harneet_singh():
    import os
    from services.resume_intelligence import ResumeIntelligenceService
    
    pdf_path = os.path.join(os.path.dirname(__file__), "..", "scratch", "harneet_resume.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("harneet_resume.pdf not found in scratch folder")
        
    with open(pdf_path, 'rb') as f:
        file_bytes = f.read()
        
    # Run OCR and layout parsing pipeline
    ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, "harneet_resume.pdf")
    parsed = ResumeIntelligenceService.parse_resume_nlp(ocr_result["text"])
    improved = ResumeIntelligenceService.ai_improve_resume_data(parsed)
    
    # 6 Work Experience entries
    experiences = parsed["experience"]
    assert len(experiences) == 6
    
    # Check companies and designations
    expected_companies = [
        "Hero MotoCorp. Ltd",
        "Akums Lifesciences Ltd",
        "Adani Power Rajasthan Ltd",
        "L&T – MHPS Boilers Pvt. Ltd",
        "Jindal Drilling & Industries Ltd",
        "Grant Thornton"
    ]
    expected_designations = [
        "Finance Head",
        "Manager",
        "Deputy Manager",
        "Assistant Manager",
        "Deputy Manager",
        "Senior Auditor"
    ]
    
    for idx, exp in enumerate(experiences):
        assert exp["designation"] == expected_designations[idx]
        assert expected_companies[idx] in exp["company"]
        
    # 2 Education entries
    educations = improved["education"]
    assert len(educations) == 2
    
    edu_degrees = [edu["degree"] for edu in educations]
    edu_insts = [edu["institution"] for edu in educations]
    
    assert "Chartered Accountant" in edu_degrees
    assert "Bachelor of Commerce (Hons.)" in edu_degrees
    assert "ICAI" in edu_insts
    assert "Sambalpur University" in edu_insts
    
    # Technical Skills populated
    assert len(improved["skills"]) > 0
    # Make sure no junk like 'Practices.' is in skills
    assert "Practices" not in improved["skills"]
    assert "Practices." not in improved["skills"]
    assert "Inventory For Action." not in improved["skills"]
    
    # Projects empty
    assert len(improved["projects"]) == 0


def test_work_experience_only_parses_work_section():
    resume_text = (
        "Asha Mehta\n"
        "asha.mehta@example.com\n\n"
        "Profile Summary\n"
        "Product leader from Jan 2020 to Dec 2021 with Python and AWS exposure.\n\n"
        "Projects\n"
        "Inventory Migration - Feb 2022 to Apr 2022\n"
        "Built migration tooling.\n\n"
        "Work Experience\n"
        "Senior Product Manager at Bright Systems Pvt Ltd - May 2022 to Present\n"
        "- Led roadmap planning across three product squads.\n"
        "Product Manager at Clear Labs Pvt Ltd - Jan 2020 to Apr 2022\n"
        "- Managed analytics releases for enterprise customers.\n"
    )

    parsed = ResumeIntelligenceService.parse_resume_nlp(resume_text)

    assert len(parsed["experience"]) == 2
    assert parsed["experience"][0]["company"] == "Bright Systems Pvt Ltd"
    assert parsed["experience"][1]["company"] == "Clear Labs Pvt Ltd"
    assert "Inventory Migration" not in [exp["designation"] for exp in parsed["experience"]]


def test_skills_are_limited_to_skills_section_and_grouped():
    resume_text = (
        "Neha Rao\n"
        "neha.rao@example.com\n\n"
        "Professional Summary\n"
        "Engineer with Python, AWS and stakeholder communication experience.\n\n"
        "Work Experience\n"
        "Software Engineer at BuildGrid Technologies Pvt Ltd - Jan 2021 to Present\n"
        "- Built APIs using Django and PostgreSQL.\n\n"
        "Skills\n"
        "Python, Django, PostgreSQL, AWS, Git, Leadership\n"
    )

    parsed = ResumeIntelligenceService.parse_resume_nlp(resume_text)

    assert parsed["skills"] == ["Python", "Django", "PostgreSQL", "AWS", "Git", "Leadership"]
    assert parsed["skill_groups"]["Programming Languages"] == ["Python"]
    assert parsed["skill_groups"]["Frameworks"] == ["Django"]
    assert parsed["skill_groups"]["Databases"] == ["PostgreSQL"]
    assert parsed["skill_groups"]["Cloud"] == ["AWS"]
    assert parsed["skill_groups"]["Tools"] == ["Git"]
    assert parsed["skill_groups"]["Soft Skills"] == ["Leadership"]


def test_parse_experience_description_preserves_blank_lines():
    desc_with_blanks = (
        "• Bullet point 1\n"
        "\n"
        "• Bullet point 2\n"
        "\n"
        "Paragraph after spacing."
    )
    html = ResumeIntelligenceService.parse_experience_description_to_html(desc_with_blanks)
    assert "<li>Bullet point 1</li>" in html
    assert "<li>Bullet point 2</li>" in html
    assert '<p class="mb-1">&nbsp;</p>' in html
    assert '<p class="mb-1">Paragraph after spacing.</p>' in html


def test_parse_experience_description_with_ordered_lists():
    desc = (
        "Responsibilities:\n"
        "1. Managed client interactions.\n"
        "2) Conducted QA checks.\n"
        "• Bullet point item\n"
        "Ending text."
    )
    html = ResumeIntelligenceService.parse_experience_description_to_html(desc)
    assert '<p class="mb-1">Responsibilities:</p>' in html
    assert "<ol class='resume-ordered'>" in html
    assert "<li>Managed client interactions.</li>" in html
    assert "<li>Conducted QA checks.</li>" in html
    assert "</ol>" in html
    assert "<ul class='resume-bullets'>" in html
    assert "<li>Bullet point item</li>" in html
    assert "</ul>" in html
    assert '<p class="mb-1">Ending text.</p>' in html


