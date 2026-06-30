import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from services.parser.pdf_parser import PDFParser
from services.parser.docx_parser import DOCXParser
from services.parser.layout_detector import LayoutDetector
from services.parser.table_detector import TableDetector

logger = logging.getLogger(__name__)

@dataclass
class NormalizedBlock:
    page: int
    bbox: Optional[List[float]]
    font_size: float
    font_weight: str  # "bold" or "normal"
    text: str
    type: str  # "text", "table_row", "header", "footer", "section_title", "table"

@dataclass
class RawDocument:
    blocks: List[NormalizedBlock] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    ocr_confidence: Optional[float] = None

class BlockBuilder:
    """
    BlockBuilder coordinates the parsing pipeline:
    - Identifies document format (PDF or DOCX)
    - Calls appropriate Parser (PDFParser or DOCXParser)
    - Runs LayoutDetector to segment headers, footers, columns, and sort reading order
    - Runs TableDetector to classify tables (education, experience, etc.)
    - Normalizes the output into a structured RawDocument
    """

    def __init__(self, pdf_parser: Optional[PDFParser] = None, docx_parser: Optional[DOCXParser] = None,
                 layout_detector: Optional[LayoutDetector] = None, table_detector: Optional[TableDetector] = None):
        self.pdf_parser = pdf_parser or PDFParser()
        self.docx_parser = docx_parser or DOCXParser()
        self.layout_detector = layout_detector or LayoutDetector()
        self.table_detector = table_detector or TableDetector()

    def build_raw_document(self, file_bytes: bytes, filename: str) -> RawDocument:
        """
        Builds a normalized RawDocument from document bytes and filename.
        """
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        if ext == "pdf":
            return self._parse_pdf(file_bytes)
        elif ext in ("docx", "doc"):
            # Note: doc files should ideally be converted, but we try to parse them if they are actually docx format,
            # or fall back to python-docx directly.
            return self._parse_docx(file_bytes)
        else:
            raise ValueError(f"Unsupported file format: .{ext}")

    def _parse_pdf(self, file_bytes: bytes) -> RawDocument:
        parsed_pdf = self.pdf_parser.parse(file_bytes)
        normalized_blocks = []
        normalized_tables = []
        normalized_images = []

        for page_data in parsed_pdf["pages"]:
            page_idx = page_data["page_index"]
            page_width = page_data["width"]
            page_height = page_data["height"]
            
            # Detect table categories and format tables as blocks for layout sorting
            page_tables = page_data["tables"]
            table_blocks = []
            
            for t in page_tables:
                category = self.table_detector.detect_table_category(t["rows"])
                
                # Format table text
                table_text = "\n".join(" | ".join(str(cell) for cell in row if cell) for row in t["rows"])
                
                table_blocks.append({
                    "type": "table",
                    "bbox": t["bbox"],
                    "text": table_text,
                    "font_name": "Table-Default",
                    "font_size": 10.0,
                    "is_bold": False,
                    "is_italic": False,
                    "category": category,
                    "rows": t["rows"]
                })
                
                normalized_tables.append({
                    "page": page_idx,
                    "bbox": t["bbox"],
                    "category": category,
                    "rows": t["rows"]
                })

            # Combine page text blocks and table blocks
            combined_blocks = page_data["blocks"] + table_blocks

            # Run LayoutDetector to sort and label blocks
            sorted_blocks = self.layout_detector.detect_layout(combined_blocks, page_width, page_height)

            # Map to NormalizedBlock
            for b in sorted_blocks:
                weight = "bold" if b.get("is_bold", False) else "normal"
                b_type = b.get("layout_type", "text")
                if b.get("type") == "table":
                    b_type = "table"
                
                normalized_blocks.append(NormalizedBlock(
                    page=page_idx,
                    bbox=b["bbox"],
                    font_size=b.get("font_size", 10.0),
                    font_weight=weight,
                    text=b["text"],
                    type=b_type
                ))

            # Gather images
            for img in page_data["images"]:
                normalized_images.append({
                    "page": page_idx,
                    "bbox": img["bbox"],
                    "width": img["width"],
                    "height": img["height"],
                    "image_bytes": img["image_bytes"]
                })

        return RawDocument(
            blocks=normalized_blocks,
            images=normalized_images,
            tables=normalized_tables,
            ocr_confidence=parsed_pdf["ocr_confidence"]
        )

    def _parse_docx(self, file_bytes: bytes) -> RawDocument:
        parsed_docx = self.docx_parser.parse(file_bytes)
        normalized_blocks = []
        normalized_tables = []

        # DOCX blocks are already sequential in reading order
        for idx, b in enumerate(parsed_docx["blocks"]):
            if b["type"] == "text":
                # Find dominant font size/weight from runs
                font_size = 10.0
                is_bold = False
                
                if b["runs"]:
                    sizes = [r["font_size"] for r in b["runs"] if r["font_size"]]
                    if sizes:
                        font_size = max(sizes)
                    is_bold = any(r["bold"] for r in b["runs"])

                weight = "bold" if is_bold else "normal"
                b_type = "text"
                if b["style"].startswith("Heading"):
                    b_type = "section_title"
                
                normalized_blocks.append(NormalizedBlock(
                    page=0,
                    bbox=None,
                    font_size=font_size,
                    font_weight=weight,
                    text=b["text"],
                    type=b_type
                ))

            elif b["type"] == "table" and b["table_data"]:
                t_data = b["table_data"]
                category = self.table_detector.detect_table_category(t_data["rows"])
                
                # Format table text
                table_text = "\n".join(" | ".join(str(cell) for cell in row if cell) for row in t_data["rows"])
                
                normalized_blocks.append(NormalizedBlock(
                    page=0,
                    bbox=None,
                    font_size=10.0,
                    font_weight="normal",
                    text=table_text,
                    type="table"
                ))

        for t in parsed_docx["tables"]:
            category = self.table_detector.detect_table_category(t["rows"])
            normalized_tables.append({
                "page": 0,
                "bbox": None,
                "category": category,
                "rows": t["rows"]
            })

        return RawDocument(
            blocks=normalized_blocks,
            images=[],
            tables=normalized_tables,
            ocr_confidence=None
        )
