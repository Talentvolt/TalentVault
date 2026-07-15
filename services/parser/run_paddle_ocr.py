import sys
import io
import json
import numpy as np
from PIL import Image
import logging

# Suppress all logging to stdout/stderr from paddle
logging.getLogger("ppocr").setLevel(logging.ERROR)

def main():
    try:
        # Read image bytes from stdin
        img_bytes = sys.stdin.buffer.read()
        if not img_bytes:
            print("__JSON_START__" + json.dumps({"error": "No image bytes received"}) + "__JSON_END__")
            return
        
        # Load image
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_np = np.array(img)
        
        # Initialize PaddleOCR with paddle_dynamic engine
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang='en', engine='paddle_dynamic')
        
        # Run prediction
        result = ocr.predict(img_np)
        
        # Convert paddlex dictionary results to classic nested list format:
        # [[ [bbox, (text, confidence)], ... ]]
        classic_result = []
        for item in result:
            page_res = []
            rec_texts = item.get("rec_texts", [])
            rec_scores = item.get("rec_scores", [])
            dt_polys = item.get("dt_polys", [])
            
            for text, score, poly in zip(rec_texts, rec_scores, dt_polys):
                bbox = [[float(pt[0]), float(pt[1])] for pt in poly]
                page_res.append([bbox, (text, float(score))])
            classic_result.append(page_res)
            
        # Return result
        print("__JSON_START__" + json.dumps({"result": classic_result}) + "__JSON_END__")
    except Exception as e:
        import traceback
        print("__JSON_START__" + json.dumps({"error": str(e), "traceback": traceback.format_exc()}) + "__JSON_END__")

if __name__ == "__main__":
    main()
