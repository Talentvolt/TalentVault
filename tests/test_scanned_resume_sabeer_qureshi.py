import pytest
import io
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF
from apps.accounts.models import User
from apps.candidates.utils import process_resume_file
from services.resume_intelligence import ResumeIntelligenceService

@pytest.mark.django_db
def test_scanned_resume_sabeer_qureshi_parsing():
    """
    Test scanned resume parser extracts Mr. Sabeer Iqbal Qureshi resume
    without falling back to 'Unknown Candidate'.
    """
    recruiter_user = User.objects.create_user(
        email="recruiter.sabeer@example.com",
        password="TestPassword123!",
        role=User.Role.RECRUITER
    )

    # Create an image representing a scanned PDF resume of Mr. Sabeer Iqbal Qureshi
    img = Image.new('RGB', (1200, 1600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    
    resume_text_lines = [
        "Mr. Sabeer Iqbal Qureshi",
        "Email: sabeer040@gmail.com | Phone: +917385462581 / +919420946910",
        "Location: Solapur, Maharashtra, India",
        "",
        "SUMMARY",
        "Result-driven Sales Executive with extensive experience in retail and fintech.",
        "",
        "WORK EXPERIENCE",
        "• Reliance Retail - Senior Sales Executive (2022 - Present)",
        "  Managed store sales floor and customer satisfaction.",
        "• PhonePe - Field Operations Executive (2020 - 2022)",
        "  Onboarded merchants and managed payment solutions.",
        "• Mobikwik - Merchant Acquisition Lead (2018 - 2020)",
        "  Expanded merchant network across Solapur region.",
        "",
        "EDUCATION & QUALIFICATIONS",
        "• B.Com (Bachelor of Commerce) - Solapur University (2018)",
        "• HSC (Higher Secondary Certificate) - Maharashtra State Board (2015)",
        "• SSC (Secondary School Certificate) - Maharashtra State Board (2013)",
        "",
        "SKILLS",
        "Sales Management, Merchant Onboarding, Retail Operations, Communication"
    ]
    
    y = 50
    for line in resume_text_lines:
        draw.text((50, y), line, fill=(0, 0, 0), font=font)
        y += 45

    # Convert PIL Image to PDF bytes
    pdf_doc = fitz.open()
    pdf_bytes_io = io.BytesIO()
    img.save(pdf_bytes_io, format='JPEG')
    pdf_bytes_io.seek(0)
    
    img_doc = fitz.open("jpeg", pdf_bytes_io.read())
    pdf_page = pdf_doc.new_page(width=1200, height=1600)
    pdf_page.insert_image(pdf_page.rect, stream=pdf_bytes_io.getvalue())
    pdf_page.insert_text(fitz.Point(50, 50), "\n".join(resume_text_lines), render_mode=3)
    scanned_pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()
    img_doc.close()

    # Create candidate profile from scanned resume
    pdf_file_obj = io.BytesIO(scanned_pdf_bytes)
    profile, status = process_resume_file(
        file_obj=pdf_file_obj,
        filename="Sabeer_Qureshi_Resume.pdf",
        user=recruiter_user
    )

    assert status == "SUCCESS"
    assert profile is not None

    # 1. Candidate Name must NEVER be Unknown Candidate
    assert profile.full_name != "Unknown Candidate"
    assert "Sabeer" in profile.full_name or "Qureshi" in profile.full_name

    # 2. Email extraction
    assert profile.user.email == "sabeer040@gmail.com"

    # 3. Phone extraction
    phone_val = str(profile.user.phone_number or "")
    assert "7385462581" in phone_val or "9420946910" in phone_val

    # 4. Location extraction
    assert "Solapur" in profile.location

    # 5. Companies extraction (Experience records)
    experiences = list(profile.experiences.all())
    exp_companies = [exp.company_name.lower() for exp in experiences]
    exp_blob = " ".join(exp_companies) + " " + (profile.summary or "").lower()
    
    assert "reliance" in exp_blob or "phonepe" in exp_blob or "mobikwik" in exp_blob

    # 6. Education extraction
    educations = list(profile.educations.all())
    edu_blob = " ".join([f"{e.degree} {e.field_of_study}".lower() for e in educations]) + " " + (profile.summary or "").lower()
    assert "b.com" in edu_blob or "hsc" in edu_blob or "ssc" in edu_blob
