import io
import re
import logging
from PIL import Image

logger = logging.getLogger(__name__)

class OCREngine:
    """
    OCREngine performs OCR on image bytes.
    It attempts to use PaddleOCR first, falling back to Tesseract if PaddleOCR fails or is unavailable.
    It returns structured words, bounding boxes, text, and an overall confidence score.
    """

    def __init__(self):
        self._paddle_ocr = None

    def _get_paddle_ocr(self):
        if self._paddle_ocr is None:
            try:
                from paddleocr import PaddleOCR
                # Initialize PaddleOCR (downloads models if not present)
                self._paddle_ocr = PaddleOCR(lang='en')
            except Exception as e:
                logger.warning(f"Failed to initialize PaddleOCR: {str(e)}. Will fallback to Tesseract.")
                self._paddle_ocr = False
        return self._paddle_ocr

    def perform_ocr(self, image_bytes: bytes) -> dict:
        """
        Performs OCR on the provided image bytes.

        Returns:
            dict: {
                "text": str,
                "confidence": float,  # 0.0 to 100.0
                "words": [
                    {"text": str, "bbox": [x0, y0, x1, y1], "confidence": float}
                ],
                "engine": str  # "paddleocr" or "tesseract"
            }
        """
        # Try PaddleOCR first
        paddle_ocr_inst = self._get_paddle_ocr()
        if paddle_ocr_inst:
            try:
                # Convert image bytes to format acceptable by PaddleOCR (numpy array or file path)
                # We can write to a temp file or convert PIL image to numpy array
                import numpy as np
                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                img_np = np.array(image)
                
                # Perform OCR
                result = paddle_ocr_inst.ocr(img_np, cls=True)
                if result and result[0]:
                    words = []
                    lines = []
                    total_conf = 0.0
                    count = 0
                    
                    # PaddleOCR result is [[ [bbox, (text, confidence)], ... ]]
                    for line in result[0]:
                        bbox, (text, confidence) = line
                        conf_percent = float(confidence) * 100.0
                        
                        # bbox structure is [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]
                        x0 = min(pt[0] for pt in bbox)
                        y0 = min(pt[1] for pt in bbox)
                        x1 = max(pt[0] for pt in bbox)
                        y1 = max(pt[1] for pt in bbox)
                        
                        words.append({
                            "text": text,
                            "bbox": [x0, y0, x1, y1],
                            "confidence": conf_percent
                        })
                        lines.append(text)
                        total_conf += conf_percent
                        count += 1
                    
                    avg_confidence = total_conf / count if count > 0 else 0.0
                    return {
                        "text": "\n".join(lines),
                        "confidence": avg_confidence,
                        "words": words,
                        "engine": "paddleocr"
                    }
            except Exception as e:
                logger.error(f"PaddleOCR execution failed: {str(e)}. Falling back to Tesseract.", exc_info=True)

        # Fallback to Tesseract OCR
        try:
            import pytesseract
            image = Image.open(io.BytesIO(image_bytes))
            
            # Use image_to_data to get structured layout & word level confidence
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            words = []
            lines_dict = {}
            total_conf = 0.0
            count = 0
            
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                text_val = data['text'][i].strip()
                conf_val = float(data['conf'][i])
                
                # Filter out empty texts and non-word elements (confidence -1)
                if text_val and conf_val >= 0:
                    x0 = float(data['left'][i])
                    y0 = float(data['top'][i])
                    x1 = x0 + float(data['width'][i])
                    y1 = y0 + float(data['height'][i])
                    
                    words.append({
                        "text": text_val,
                        "bbox": [x0, y0, x1, y1],
                        "confidence": conf_val
                    })
                    total_conf += conf_val
                    count += 1
                    
                    # Group by line_num to construct line-based text
                    line_num = data['line_num'][i]
                    if line_num not in lines_dict:
                        lines_dict[line_num] = []
                    lines_dict[line_num].append(text_val)
            
            # Reconstruct lines
            sorted_line_keys = sorted(lines_dict.keys())
            reconstructed_text = "\n".join(" ".join(lines_dict[k]) for k in sorted_line_keys)
            avg_confidence = total_conf / count if count > 0 else 0.0
            
            return {
                "text": reconstructed_text,
                "confidence": avg_confidence,
                "words": words,
                "engine": "tesseract"
            }
        except Exception as e:
            logger.critical(f"Tesseract OCR also failed: {str(e)}", exc_info=True)
            return {
                "text": "",
                "confidence": 0.0,
                "words": [],
                "engine": "failed"
            }
