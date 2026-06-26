import os
import sys
import fitz
import re

def reconstruct_pdf_layout(pdf_path):
    if not os.path.exists(pdf_path):
        return f"Error: {pdf_path} not found"
        
    doc = fitz.open(pdf_path)
    full_text_parts = []
    
    # Let's first find the candidate name block (largest font size on page 1)
    largest_font_size = 0
    name_block_x_center = 0
    
    if len(doc) > 0:
        page = doc[0]
        blocks_dict = page.get_text("dict")
        for b in blocks_dict.get("blocks", []):
            if b.get("type") == 0:  # text
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        size = span.get("size", 0)
                        text = span.get("text", "").strip()
                        # Simple valid name characters check
                        if len(text) > 3 and any(c.isalpha() for c in text):
                            # Exclude typical headings
                            if text.lower() not in ["education", "experience", "work experience", "skills", "projects", "certifications", "profile", "summary"]:
                                if size > largest_font_size:
                                    largest_font_size = size
                                    # Calculate center x
                                    bbox = span.get("bbox", (0,0,0,0))
                                    name_block_x_center = (bbox[0] + bbox[2]) / 2

    for page_idx, page in enumerate(doc):
        blocks = page.get_text("blocks")
        valid_blocks = []
        for b in blocks:
            x0, y0, x1, y1, text, block_no, block_type = b
            text_clean = text.strip()
            if text_clean:
                valid_blocks.append((x0, y0, x1, y1, text_clean))
                
        if not valid_blocks:
            continue
            
        # Detect best split point x
        best_x = None
        min_cross = 9999
        best_left_count = 0
        best_right_count = 0
        
        # Test split points from x = 120 to x = 400
        for x in range(120, 400, 10):
            left_count = 0
            right_count = 0
            cross_count = 0
            for x0, y0, x1, y1, text in valid_blocks:
                if x1 <= x:
                    left_count += 1
                elif x0 >= x:
                    right_count += 1
                else:
                    cross_count += 1
            
            if left_count > 0 and right_count > 0:
                # We want to minimize crossing blocks
                if cross_count < min_cross:
                    min_cross = cross_count
                    best_x = x
                    best_left_count = left_count
                    best_right_count = right_count
                elif cross_count == min_cross:
                    # Prefer center split points
                    if best_x is None or abs(x - 297.5) < abs(best_x - 297.5):
                        best_x = x
                        best_left_count = left_count
                        best_right_count = right_count
                        
        # If we have a clear split and cross count is small relative to total blocks
        has_columns = best_x is not None and min_cross <= max(2, len(valid_blocks) * 0.25)
        
        if has_columns:
            header_blocks = []
            footer_blocks = []
            left_blocks = []
            right_blocks = []
            
            for b in valid_blocks:
                x0, y0, x1, y1, text = b
                # Crossing blocks
                if x0 < best_x < x1:
                    if y1 < 150:
                        header_blocks.append(b)
                    elif y0 > 700:
                        footer_blocks.append(b)
                    else:
                        # Put in left or right depending on center
                        center_x = (x0 + x1) / 2
                        if center_x <= best_x:
                            left_blocks.append(b)
                        else:
                            right_blocks.append(b)
                elif x1 <= best_x:
                    left_blocks.append(b)
                else:
                    right_blocks.append(b)
                    
            # Sort blocks by y0
            header_blocks.sort(key=lambda x: x[1])
            footer_blocks.sort(key=lambda x: x[1])
            left_blocks.sort(key=lambda x: x[1])
            right_blocks.sort(key=lambda x: x[1])
            
            # Determine which column to place first
            # Default to left column first unless the name block center is on the right side
            right_column_first = False
            if page_idx == 0 and name_block_x_center > best_x:
                right_column_first = True
            
            # For subsequent pages, match the first page column order
            page_text_parts = []
            if header_blocks:
                page_text_parts.append("\n".join([b[4] for b in header_blocks]))
                
            left_text = "\n".join([b[4] for b in left_blocks])
            right_text = "\n".join([b[4] for b in right_blocks])
            
            if right_column_first:
                if right_text: page_text_parts.append(right_text)
                if left_text: page_text_parts.append(left_text)
            else:
                if left_text: page_text_parts.append(left_text)
                if right_text: page_text_parts.append(right_text)
                
            if footer_blocks:
                page_text_parts.append("\n".join([b[4] for b in footer_blocks]))
                
            full_text_parts.append("\n\n".join(page_text_parts))
        else:
            # Single column
            valid_blocks.sort(key=lambda x: x[1])
            full_text_parts.append("\n\n".join([b[4] for b in valid_blocks]))
            
    return "\n\n=== NEW PAGE ===\n\n".join(full_text_parts)

if __name__ == "__main__":
    shreya_path = "scratch/shreya_chavda_Shreya_ZdEAJej.pdf"
    print("="*60)
    print("SHREYA RECONSTRUCTED TEXT")
    print("="*60)
    print(reconstruct_pdf_layout(shreya_path)[:1500])
    
    vikke_path = "scratch/vikke_gupta_Naukri_VikkeGupta16y_0m.pdf"
    print("="*60)
    print("VIKKE RECONSTRUCTED TEXT")
    print("="*60)
    print(reconstruct_pdf_layout(vikke_path)[:1500])
