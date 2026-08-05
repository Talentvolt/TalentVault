import os
import sys
import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Pre-load and pre-download PaddleOCR models to prevent runtime download delays."

    def handle(self, *args, **options):
        self.stdout.write("=== PRE-LOADING PADDLEOCR MODELS FOR PRODUCTION ===")
        try:
            from services.resume_intelligence import get_paddle_ocr_instance
            ocr = get_paddle_ocr_instance()
            if ocr is not None:
                self.stdout.write(self.style.SUCCESS("PaddleOCR models successfully pre-loaded and cached!"))
            else:
                self.stdout.write(self.style.WARNING("PaddleOCR unavailable. Fallback engines will be used."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during PaddleOCR pre-load: {str(e)}"))
