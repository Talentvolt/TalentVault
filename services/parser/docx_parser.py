import io
import logging
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table

logger = logging.getLogger(__name__)

class DOCXParser:
    """
    DOCXParser extracts paragraphs, runs, formatting (bold, italic, font details),
    and tables in their exact reading order from Word (.docx) files using python-docx.
    """

    def parse(self, docx_bytes: bytes) -> dict:
        """
        Parses DOCX bytes into structured blocks and tables.

        Returns:
            dict: {
                "blocks": [
                    {
                        "type": "text" | "table",
                        "text": str,  # paragraph text, or table rows represented as text
                        "style": str,  # style name (e.g. 'Normal', 'Heading 1')
                        "runs": [
                            {
                                "text": str,
                                "bold": bool,
                                "italic": bool,
                                "font_name": str or None,
                                "font_size": float or None
                            }
                        ],
                        "table_data": dict or None  # if type is 'table'
                    }
                ],
                "tables": [
                    {
                        "rows": [[str, ...], ...]
                    }
                ]
            }
        """
        doc = Document(io.BytesIO(docx_bytes))
        blocks = []
        tables_list = []

        # Iterate over all elements in body in reading order
        for item in self._iter_block_items(doc):
            if hasattr(item, "runs"):
                # Process paragraph
                runs_data = []
                for run in item.runs:
                    font_name = None
                    font_size = None
                    if run.font:
                        font_name = run.font.name
                        if run.font.size:
                            font_size = run.font.size.pt
                    
                    runs_data.append({
                        "text": run.text,
                        "bold": bool(run.bold),
                        "italic": bool(run.italic),
                        "font_name": font_name,
                        "font_size": font_size
                    })

                # Determine style name
                style_name = item.style.name if item.style else "Normal"
                
                blocks.append({
                    "type": "text",
                    "text": item.text,
                    "style": style_name,
                    "runs": runs_data,
                    "table_data": None
                })

            elif hasattr(item, "rows"):
                # Process table
                rows = []
                for row in item.rows:
                    row_cells = []
                    for cell in row.cells:
                        # Extract cell text, preserving paragraph linebreaks inside cells
                        cell_text = "\n".join(p.text for p in cell.paragraphs).strip()
                        row_cells.append(cell_text)
                    rows.append(row_cells)

                table_obj = {
                    "rows": rows
                }
                tables_list.append(table_obj)
                
                # Also represent table as a block for reading order flow
                blocks.append({
                    "type": "table",
                    "text": "\n".join(" | ".join(r) for r in rows),
                    "style": "TableGrid",
                    "runs": [],
                    "table_data": table_obj
                })

        return {
            "blocks": blocks,
            "tables": tables_list
        }

    def _iter_block_items(self, parent):
        """
        Yield each paragraph and table child within parent, in document order.
        Each returned value is an instance of either Paragraph or Table.
        """
        if hasattr(parent, "element") and hasattr(parent.element, "body"):
            parent_elm = parent.element.body
        else:
            parent_elm = parent._element
            
        for child in parent_elm.iterchildren():
            if child.tag.endswith('p'):
                yield Paragraph(child, parent)
            elif child.tag.endswith('tbl'):
                yield Table(child, parent)
