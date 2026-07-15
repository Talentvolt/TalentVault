import os
import sys
import django

# Setup path and environment
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Load env variables
try:
    import dotenv
    dotenv.load_dotenv(os.path.join(project_root, '.env'))
except ImportError:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")
django.setup()

from services.resume_intelligence import ResumeIntelligenceService

def main():
    resume_path = "scratch/prashant_resume.docx"
    with open(resume_path, "rb") as f:
        file_bytes = f.read()
        
    print(f"Reading: {resume_path} ({len(file_bytes)} bytes)")
    ocr_result = ResumeIntelligenceService.run_ocr_pipeline(file_bytes, os.path.basename(resume_path))
    text = ocr_result["text"]
    
    print("\n--- RAW EXTRACTED DOCX TEXT ---")
    with open("scratch/prashant_text.txt", "w", encoding="utf-8") as f_out:
        f_out.write(text)
    print("  Saved raw text to scratch/prashant_text.txt")
    print("--------------------------------")
    
    # Check contact details presence
    print("\nCheck Presence:")
    print(f"  Has 'Prashant': {'Prashant' in text}")
    print(f"  Has 'prashantsingh372@gmail.com': {'prashantsingh372@gmail.com' in text}")
    print(f"  Has '9651400687': {'9651400687' in text}")

if __name__ == "__main__":
    main()
