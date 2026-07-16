import fitz  # PyMuPDF
import logging
from typing import List, Dict, Any, Optional
from services.parser.ocr_engine import OCREngine

logger = logging.getLogger(__name__)

class PDFParser:
    """
    PDFParser extracts text, styles, fonts, columns, images, tables,
    and reading order from PDF files using PyMuPDF.
    If pages are scanned (image-only), it runs OCR using OCREngine.
    """

    def __init__(self, ocr_engine: Optional[OCREngine] = None):
        self.ocr_engine = ocr_engine or OCREngine()

    def parse(self, pdf_bytes: bytes) -> dict:
        """
        Parses PDF bytes into structured pages, blocks, images, tables, and OCR metadata.

        Returns:
            dict: {
                "pages": [
                    {
                        "page_index": int,
                        "width": float,
                        "height": float,
                        "blocks": [
                            {
                                "type": "text" | "header" | "footer",
                                "bbox": [x0, y0, x1, y1],
                                "text": str,
                                "font_name": str,
                                "font_size": float,
                                "is_bold": bool,
                                "is_italic": bool
                            }
                        ],
                        "tables": [
                            {
                                "bbox": [x0, y0, x1, y1],
                                "rows": [[str, ...], ...]
                            }
                        ],
                        "images": [
                            {
                                "bbox": [x0, y0, x1, y1],
                                "width": int,
                                "height": int,
                                "image_bytes": bytes
                            }
                        ],
                        "is_scanned": bool
                    }
                ],
                "ocr_confidence": float or None
            }
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_data = []
        total_ocr_conf = 0.0
        ocr_page_count = 0

        import concurrent.futures

        # Phase 1: Native metadata extraction & determine scanned/images status
        ocr_tasks = []
        
        for page_idx, page in enumerate(doc):
            page_width = page.rect.width
            page_height = page.rect.height

            # Extract tables first (so we can filter text blocks inside tables)
            extracted_tables = []
            try:
                tables = page.find_tables()
                for t in tables:
                    rows = t.extract()
                    extracted_tables.append({
                        "bbox": list(t.bbox),
                        "rows": rows
                    })
            except Exception as e:
                logger.warning(f"Failed to find tables on page {page_idx}: {str(e)}")

            # Extract images
            extracted_images = []
            try:
                image_list = page.get_images(full=True)
                for img_info in image_list:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    # Try to get image rect on page
                    rects = page.get_image_rects(xref)
                    bbox = list(rects[0]) if rects else [0.0, 0.0, 0.0, 0.0]
                    
                    extracted_images.append({
                        "bbox": bbox,
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "image_bytes": image_bytes
                    })
            except Exception as e:
                logger.warning(f"Failed to extract images on page {page_idx}: {str(e)}")

            # Extract raw blocks to determine if scanned
            text_dict = page.get_text("dict")
            blocks = text_dict.get("blocks", [])

            # Check if page is scanned: very little text and/or only image blocks
            total_text_len = sum(
                sum(len(span["text"]) for line in b.get("lines", []) for span in line.get("spans", []))
                for b in blocks if b.get("type") == 0
            )

            is_scanned = total_text_len < 15
            has_images = len(extracted_images) > 0 or len(page.get_images()) > 0

            # If it's scanned and contains images, prepare OCR task
            if is_scanned and has_images:
                try:
                    pix = page.get_pixmap(dpi=150)
                    png_bytes = pix.tobytes("png")
                    ocr_tasks.append((page_idx, png_bytes))
                except Exception as e:
                    logger.error(f"Failed to render page {page_idx} for OCR: {e}")

            pages_data.append({
                "page_index": page_idx,
                "width": page_width,
                "height": page_height,
                "blocks": [], # Filled below
                "tables": extracted_tables,
                "images": extracted_images,
                "is_scanned": is_scanned,
                "has_images": has_images,
                "blocks_dict_blocks": blocks,
                "ocr_confidence": None
            })

        # Phase 2: Run OCR tasks in parallel
        ocr_results = {}
        if ocr_tasks:
            def run_single_ocr(p_idx, png_bytes):
                try:
                    return p_idx, self.ocr_engine.perform_ocr(png_bytes)
                except Exception as e:
                    logger.error(f"Parallel OCR failed for page {p_idx}: {e}")
                    return p_idx, None

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(ocr_tasks))) as executor:
                futures = [executor.submit(run_single_ocr, p_idx, png_bytes) for p_idx, png_bytes in ocr_tasks]
                for future in concurrent.futures.as_completed(futures):
                    p_idx, res = future.result()
                    if res:
                        ocr_results[p_idx] = res

        # Phase 3: Post-process pages (OCR grouping or digital blocks extraction)
        for page_data in pages_data:
            page_idx = page_data["page_index"]
            is_scanned = page_data["is_scanned"]
            has_images = page_data["has_images"]
            extracted_blocks = []
            page_ocr_conf = None

            if is_scanned:
                if has_images and page_idx in ocr_results:
                    ocr_res = ocr_results[page_idx]
                    page_ocr_conf = ocr_res.get("confidence", 0.0)
                    total_ocr_conf += page_ocr_conf
                    ocr_page_count += 1
                    
                    # Convert OCR words into normalized line blocks
                    # Group words by vertical coordinates (similar line lines)
                    ocr_words = ocr_res.get("words", [])
                    if ocr_words:
                        # Simple line grouping: sort words by y0, group if they overlap vertically
                        ocr_words_sorted = sorted(ocr_words, key=lambda w: w["bbox"][1])
                        current_line = []
                        
                        for w in ocr_words_sorted:
                            if not current_line:
                                current_line.append(w)
                            else:
                                # If word overlaps vertically with current line's average height
                                prev_y0 = sum(item["bbox"][1] for item in current_line) / len(current_line)
                                prev_y1 = sum(item["bbox"][3] for item in current_line) / len(current_line)
                                curr_y0 = w["bbox"][1]
                                curr_y1 = w["bbox"][3]
                                
                                overlap = min(prev_y1, curr_y1) - max(prev_y0, curr_y0)
                                height = min(prev_y1 - prev_y0, curr_y1 - curr_y0)
                                
                                if overlap > 0.4 * height:
                                    current_line.append(w)
                                else:
                                    # Sort line horizontally
                                    current_line.sort(key=lambda item: item["bbox"][0])
                                    line_text = " ".join(item["text"] for item in current_line)
                                    line_bbox = [
                                        min(item["bbox"][0] for item in current_line),
                                        min(item["bbox"][1] for item in current_line),
                                        max(item["bbox"][2] for item in current_line),
                                        max(item["bbox"][3] for item in current_line),
                                    ]
                                    extracted_blocks.append({
                                        "type": "text",
                                        "bbox": line_bbox,
                                        "text": line_text,
                                        "font_name": "OCR-Default",
                                        "font_size": 10.0,
                                        "is_bold": False,
                                        "is_italic": False
                                    })
                                    current_line = [w]
                                    
                        # Append trailing line
                        if current_line:
                            current_line.sort(key=lambda item: item["bbox"][0])
                            line_text = " ".join(item["text"] for item in current_line)
                            line_bbox = [
                                min(item["bbox"][0] for item in current_line),
                                min(item["bbox"][1] for item in current_line),
                                max(item["bbox"][2] for item in current_line),
                                max(item["bbox"][3] for item in current_line),
                            ]
                            extracted_blocks.append({
                                "type": "text",
                                "bbox": line_bbox,
                                "text": line_text,
                                "font_name": "OCR-Default",
                                "font_size": 10.0,
                                "is_bold": False,
                                "is_italic": False
                            })
                else:
                    logger.info(f"Page {page_idx} is scanned but has no images. Skipping OCR.")
            else:
                # Page is digital, extract text blocks natively
                blocks = page_data["blocks_dict_blocks"]
                extracted_tables = page_data["tables"]
                for b in blocks:
                    if b.get("type") == 0:  # Text block
                        for line in b.get("lines", []):
                            line_text = ""
                            max_font_size = 0.0
                            is_bold = False
                            is_italic = False
                            font_names = []
                            
                            for span in line.get("spans", []):
                                span_text = span["text"]
                                line_text += span_text
                                
                                flags = span["flags"]
                                span_font = span["font"]
                                span_size = span["size"]
                                
                                span_bold = bool(flags & 16) or "bold" in span_font.lower()
                                span_italic = bool(flags & 2) or "italic" in span_font.lower()
                                
                                if span_size > max_font_size:
                                    max_font_size = span_size
                                if span_bold:
                                    is_bold = True
                                if span_italic:
                                    is_italic = True
                                if span_font not in font_names:
                                    font_names.append(span_font)
                            
                            line_bbox = list(line["bbox"])
                            
                            # Filter out blocks inside tables to prevent duplication
                            if self._is_inside_any_table(line_bbox, extracted_tables):
                                continue
                                
                            extracted_blocks.append({
                                "type": "text",
                                "bbox": line_bbox,
                                "text": line_text,
                                "font_name": font_names[0] if font_names else "Unknown",
                                "font_size": max_font_size,
                                "is_bold": is_bold,
                                "is_italic": is_italic
                            })

            page_data["blocks"] = extracted_blocks
            page_data.pop("blocks_dict_blocks", None)
            page_data.pop("has_images", None)

        avg_ocr_conf = total_ocr_conf / ocr_page_count if ocr_page_count > 0 else None
        return {
            "pages": pages_data,
            "ocr_confidence": avg_ocr_conf
        }

    def _is_inside_any_table(self, bbox: list, tables: list) -> bool:
        # Check if the center of bbox lies inside any table bounding box
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        for t in tables:
            t_x0, t_y0, t_x1, t_y1 = t["bbox"]
            if t_x0 <= cx <= t_x1 and t_y0 <= cy <= t_y1:
                return True
        return False
