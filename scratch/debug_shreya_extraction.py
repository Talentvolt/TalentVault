import os
import io
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from services.resume_intelligence import ResumeIntelligenceService, SPACY_AVAILABLE

def generate_shreya_pdf(filename):
    print(f"Generating PDF: {filename}")
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    body_style = ParagraphStyle(
        'ResumeBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        spaceAfter=6
    )
    
    # We want SHREYA CHAVDA to be in a larger bold font
    name_style = ParagraphStyle(
        'ResumeName',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        spaceAfter=10
    )
    
    story.append(Paragraph("SHREYA CHAVDA", name_style))
    story.append(Paragraph("Anant Zaveri Pvt Ltd.", body_style))
    story.append(Paragraph("Email: shreya.chavda1712@gmail.com", body_style))
    story.append(Paragraph("Phone: +91 99999 88888", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Career Objective:", body_style))
    story.append(Paragraph("To work as a Senior Associate and contribute to business growth.", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Work Experience:", body_style))
    story.append(Paragraph("Presently working as Associate in Anant Zaveri Pvt Ltd. - Jan 2024 to Present", body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Education:", body_style))
    story.append(Paragraph("MBA - 2023 - Business School", body_style))
    
    doc.build(story)
    print("PDF generation complete.")

def debug_extraction():
    pdf_path = "scratch/shreya_chavda_resume.pdf"
    generate_shreya_pdf(pdf_path)
    
    with open(pdf_path, 'rb') as f:
        file_bytes = f.read()
        
    ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, "shreya_chavda_resume.pdf")
    text = ocr_result["text"]
    
    print("\n==============================================")
    print("=== CANDIDATE-NAME DECISION STEPS ===")
    print("==============================================")
    
    # 1. Header Text
    lines = [l.strip() for l in text.split('\n')]
    BREAKING_SECTION_HEADINGS = {
        'workexperience', 'experience', 'employmenthistory', 'workhistory', 'professionalexperience',
        'education', 'academic', 'academicbackground', 'qualification', 'qualifications', 'educationhistory',
        'skills', 'technicalskills', 'corecompetencies', 'keyskills', 'expertise', 'competencies',
        'projects', 'personalprojects', 'academicprojects', 'keyprojects',
        'certifications', 'certification', 'courses', 'credentials', 'licensescertifications',
        'summary', 'careerobjective', 'objective', 'professionalsummary', 'aboutme', 'profilesummary'
    }
    
    header_lines = []
    for line in lines:
        if not line:
            continue
        normalized = re.sub(r'[^a-z0-9]', '', line.lower()).strip()
        if normalized in BREAKING_SECTION_HEADINGS:
            break
        header_lines.append(line)
    
    print(f"\n[1] Header Text Lines:")
    for hl in header_lines:
        print(f"  -> {hl}")
        
    # 2. Photo Region
    print(f"\n[2] Detected Photo Region:")
    print("  -> None (No photo metadata/region found)")
    
    # 3. Largest Text
    largest_text = ocr_result.get("largest_bold_name")
    print(f"\n[3] Largest bold/styled text candidate:")
    print(f"  -> {largest_text}")
    
    # 4. PERSON and ORGANIZATION Entities (spaCy)
    person_ents = []
    org_ents = []
    if SPACY_AVAILABLE:
        try:
            import spacy
            nlp = spacy.load("en_core_web_sm")
            header_text = "\n".join(header_lines[:12])
            doc = nlp(header_text)
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    person_ents.append(ent.text.strip())
                elif ent.label_ in ("ORG", "GPE", "FAC", "LOC"):
                    org_ents.append(ent.text.strip())
        except Exception as e:
            print(f"  -> spaCy execution failed: {e}")
            
    print(f"\n[4] PERSON Entities detected:")
    for pe in person_ents:
        print(f"  -> {pe}")
    print(f"[5] ORGANIZATION/GPE Entities detected:")
    for oe in org_ents:
        print(f"  -> {oe}")
        
    # 5. Final Selected Name
    final_name = ResumeIntelligenceService.extract_candidate_name(
        text, 
        parsed_name=largest_text,
        email="shreya.chavda1712@gmail.com"
    )
    print(f"\n[6] Final Selected Candidate Name:")
    print(f"  -> {final_name}")
    print("==============================================\n")

if __name__ == '__main__':
    debug_extraction()
