import importlib.util
import logging
import os
import threading
from django.conf import settings

logger = logging.getLogger(__name__)

class NLPService:
    _instance = None
    _lock = threading.Lock()
    _nlp = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(NLPService, cls).__new__(cls)
        return cls._instance

    def is_spacy_available(self) -> bool:
        return importlib.util.find_spec("spacy") is not None

    def get_nlp(self):
        if not self.is_spacy_available():
            return None
        if self._nlp is None:
            with self._lock:
                if self._nlp is None:
                    try:
                        import spacy
                        logger.info("Initializing and loading spaCy model 'en_core_web_sm' (Lazy Load)...")
                        self._nlp = spacy.load("en_core_web_sm")
                    except Exception as e:
                        logger.error(f"Failed to load spaCy model: {e}")
                        self._nlp = None
        return self._nlp

class OCRService:
    _instance = None
    _lock = threading.Lock()
    _paddle_ocr = None
    _easyocr_reader = None
    _pytesseract_checked = False
    _tesseract_available = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(OCRService, cls).__new__(cls)
        return cls._instance

    def is_paddle_available(self) -> bool:
        return importlib.util.find_spec("paddleocr") is not None

    def is_easy_available(self) -> bool:
        return importlib.util.find_spec("easyocr") is not None

    def is_tesseract_available(self) -> bool:
        if not self._pytesseract_checked:
            with self._lock:
                if not self._pytesseract_checked:
                    if importlib.util.find_spec("pytesseract") is not None:
                        try:
                            import pytesseract
                            pytesseract.get_tesseract_version()
                            self._tesseract_available = True
                        except Exception:
                            self._tesseract_available = False
                    else:
                        self._tesseract_available = False
                    self._pytesseract_checked = True
        return self._tesseract_available

    def get_paddle_ocr(self, use_textline_orientation=True):
        if not self.is_paddle_available():
            return None
        if self._paddle_ocr is None:
            with self._lock:
                if self._paddle_ocr is None:
                    try:
                        from paddleocr import PaddleOCR
                        # Suppress paddle logging if possible, but keep standard loading
                        logger.info("Initializing PaddleOCR model (Lazy Load)...")
                        self._paddle_ocr = PaddleOCR(use_textline_orientation=use_textline_orientation, lang='en')
                    except Exception as e:
                        logger.error(f"Failed to load PaddleOCR: {e}")
                        self._paddle_ocr = None
        return self._paddle_ocr

    def get_easyocr_reader(self):
        if not self.is_easy_available():
            return None
        if self._easyocr_reader is None:
            with self._lock:
                if self._easyocr_reader is None:
                    try:
                        import easyocr
                        logger.info("Initializing EasyOCR Reader (Lazy Load)...")
                        self._easyocr_reader = easyocr.Reader(['en'])
                    except Exception as e:
                        logger.error(f"Failed to load EasyOCR Reader: {e}")
                        self._easyocr_reader = None
        return self._easyocr_reader

class AIService:
    _instance = None
    _lock = threading.Lock()
    _openai_client = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(AIService, cls).__new__(cls)
        return cls._instance

    def get_openai_client(self):
        if self._openai_client is None:
            with self._lock:
                if self._openai_client is None:
                    try:
                        from openai import OpenAI
                        api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
                        if not api_key:
                            raise ValueError("OPENAI_API_KEY is not configured.")
                        logger.info("Initializing OpenAI Client (Lazy Load)...")
                        self._openai_client = OpenAI(api_key=api_key)
                    except Exception as e:
                        logger.error(f"Failed to initialize OpenAI client: {e}")
                        raise
        return self._openai_client

class StorageService:
    _instance = None
    _lock = threading.Lock()
    _storage = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(StorageService, cls).__new__(cls)
        return cls._instance

    def get_storage(self):
        if self._storage is None:
            with self._lock:
                if self._storage is None:
                    try:
                        from django.core.files.storage import default_storage
                        self._storage = default_storage
                    except Exception as e:
                        logger.error(f"Failed to load default storage: {e}")
                        self._storage = None
        return self._storage
