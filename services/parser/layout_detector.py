import re
from typing import List, Dict, Any

class LayoutDetector:
    """
    LayoutDetector analyzes the spatial layout of blocks on a page to identify:
    - Headers & Footers
    - Section Titles
    - Columns and Sidebars
    - Reading Order (preserving column segregation)
    """

    # Common section title keywords
    SECTION_KEYWORDS = {
        "experience", "work", "employment", "history", "career",
        "education", "qualification", "academic", "study",
        "skills", "competencies", "expertise", "languages",
        "projects", "accomplishments", "achievements",
        "certifications", "licenses", "credentials", "summary",
        "objective", "publications", "interests", "hobbies"
    }

    def detect_layout(self, blocks: List[Dict[str, Any]], page_width: float, page_height: float) -> List[Dict[str, Any]]:
        """
        Detects layout metadata for each block and sorts them into the correct human reading order.
        Adds "layout_type" key to each block: "header", "footer", "section_title", "body", "spanning".
        """
        if not blocks:
            return []

        # 1. Classify Headers and Footers based on vertical boundaries (top 8% and bottom 8%)
        header_threshold = page_height * 0.08
        footer_threshold = page_height * 0.92

        classified_blocks = []
        for b in blocks:
            x0, y0, x1, y1 = b["bbox"]
            b_copy = dict(b)
            
            if y1 <= header_threshold:
                b_copy["layout_type"] = "header"
            elif y0 >= footer_threshold:
                b_copy["layout_type"] = "footer"
            else:
                b_copy["layout_type"] = "body"
            classified_blocks.append(b_copy)

        # 2. Detect Section Titles among body blocks
        for b in classified_blocks:
            if b["layout_type"] == "body":
                text = b["text"].strip()
                # A block is a section title if it is short, starts/contains keywords, and is styled (bold/large)
                if text and len(text) < 50:
                    text_clean = re.sub(r'[^a-zA-Z\s]', ' ', text).lower().strip()
                    words = set(text_clean.split())
                    
                    is_title_style = b.get("is_bold", False) or b.get("font_size", 10.0) >= 11.0 or text.isupper()
                    if is_title_style and (words & self.SECTION_KEYWORDS or any(kw in text_clean for kw in ["work history", "key skills", "professional summary"])):
                        b["layout_type"] = "section_title"

        # 3. Detect column split X coordinate
        # Filter body blocks to find vertical dividers
        body_blocks = [b for b in classified_blocks if b["layout_type"] in ("body", "section_title")]
        split_x = self._find_column_split(body_blocks, page_width, page_height)

        # Classify column sidebars and spanning blocks
        if split_x:
            # Classify columns
            left_width = split_x
            right_width = page_width - split_x
            layout_name = "two_columns"
            if left_width < 0.35 * page_width:
                layout_name = "left_sidebar"
            elif right_width < 0.35 * page_width:
                layout_name = "right_sidebar"
                
            for b in body_blocks:
                x0, y0, x1, y1 = b["bbox"]
                # A block is spanning if it crosses the split and is relatively wide
                if x0 < split_x < x1 and (x1 - x0) > 0.45 * page_width:
                    b["layout_type"] = "spanning"
                else:
                    b["column"] = "left" if x1 <= split_x else "right"
                    b["layout_name"] = layout_name
        else:
            for b in body_blocks:
                b["column"] = "main"
                b["layout_name"] = "single_column"

        # 4. Sort into Reading Order
        sorted_blocks = self._sort_reading_order(classified_blocks, split_x, page_width, page_height)
        return sorted_blocks

    def _find_column_split(self, body_blocks: List[Dict[str, Any]], page_width: float, page_height: float) -> Optional[float]:
        """
        Finds a vertical split X coordinate that divides blocks into two columns.
        """
        if len(body_blocks) < 4:
            return None

        # Scan X axis from 20% to 80% page width
        scan_start = int(page_width * 0.20)
        scan_end = int(page_width * 0.80)
        
        best_split = None
        min_intersections = len(body_blocks)

        for x in range(scan_start, scan_end, 5):
            intersections = 0
            for b in body_blocks:
                x0, y0, x1, y1 = b["bbox"]
                # Only count intersection if the block is NOT spanning the entire page width
                if x0 < x < x1:
                    if (x1 - x0) > 0.65 * page_width:
                        continue  # ignore spanning banners/headers
                    intersections += 1
            
            if intersections < min_intersections:
                min_intersections = intersections
                best_split = x

        # We accept a split if it cuts clean (very few intersecting blocks)
        # and we have enough blocks on both sides of the split line
        if best_split is not None:
            left_side = [b for b in body_blocks if b["bbox"][2] <= best_split]
            right_side = [b for b in body_blocks if b["bbox"][0] >= best_split]
            
            # At least 2 blocks on both sides, and no more than 2 body intersections
            if len(left_side) >= 2 and len(right_side) >= 2 and min_intersections <= 2:
                return float(best_split)
                
        return None

    def _sort_reading_order(self, blocks: List[Dict[str, Any]], split_x: Optional[float], page_width: float, page_height: float) -> List[Dict[str, Any]]:
        """
        Sorts the blocks of a page into a clean reading order flow.
        """
        # Segregate headers, footers, and body
        headers = sorted([b for b in blocks if b["layout_type"] == "header"], key=lambda b: (b["bbox"][1], b["bbox"][0]))
        footers = sorted([b for b in blocks if b["layout_type"] == "footer"], key=lambda b: (b["bbox"][1], b["bbox"][0]))
        
        body = [b for b in blocks if b["layout_type"] not in ("header", "footer")]
        
        if not body:
            return headers + footers

        if not split_x:
            # Single column: sort top-to-bottom
            body_sorted = sorted(body, key=lambda b: (b["bbox"][1], b["bbox"][0]))
            return headers + body_sorted + footers

        # Split columns using spanning blocks as vertical zone dividers
        spanning_blocks = sorted([b for b in body if b["layout_type"] == "spanning"], key=lambda b: b["bbox"][1])
        
        # Divide body blocks into vertical zones
        zones = []
        last_y = 0.0
        
        for span in spanning_blocks:
            span_y0 = span["bbox"][1]
            # Get body blocks in this zone (above the spanning block)
            zone_blocks = [b for b in body if last_y <= b["bbox"][1] < span_y0 and b["layout_type"] != "spanning"]
            zones.append((zone_blocks, span))
            last_y = span["bbox"][3]
            
        # Add the final zone below the last spanning block
        final_zone_blocks = [b for b in body if b["bbox"][1] >= last_y and b["layout_type"] != "spanning"]
        zones.append((final_zone_blocks, None))

        body_sorted = []
        for zone_blocks, span_block in zones:
            if zone_blocks:
                # Segment zone_blocks into left and right columns
                left_col = sorted([b for b in zone_blocks if b.get("column") == "left"], key=lambda b: (b["bbox"][1], b["bbox"][0]))
                right_col = sorted([b for b in zone_blocks if b.get("column") == "right"], key=lambda b: (b["bbox"][1], b["bbox"][0]))
                
                # We read left column first, then right column
                body_sorted.extend(left_col)
                body_sorted.extend(right_col)
                
            if span_block:
                body_sorted.append(span_block)

        return headers + body_sorted + footers
