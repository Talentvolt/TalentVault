import os
import fitz

pdf_path = os.path.join(os.path.dirname(__file__), 'harneet_resume.pdf')
doc = fitz.open(pdf_path)

header_text = []
col1_text = [] # Left column (Skills, Education)
col2_text = [] # Right column (Summary, Work Experience)
footer_text = []

for page_idx, page in enumerate(doc):
    blocks = page.get_text("blocks")
    # Filter and sort
    valid_blocks = []
    for b in blocks:
        x0, y0, x1, y1, text, block_no, block_type = b
        text_clean = text.strip()
        if text_clean:
            valid_blocks.append((x0, y0, x1, y1, text_clean))
            
    # Sort by y0
    valid_blocks_sorted = sorted(valid_blocks, key=lambda b: b[1])
    
    if page_idx == 0:
        # Page 1
        for b in valid_blocks_sorted:
            x0, y0, x1, y1, text = b
            if y1 < 135:
                header_text.append(text)
            else:
                # Split by columns
                if x0 < 200:
                    col1_text.append(text)
                else:
                    col2_text.append(text)
    elif page_idx == 1:
        # Page 2
        for b in valid_blocks_sorted:
            x0, y0, x1, y1, text = b
            if x0 < 200:
                col1_text.append(text)
            else:
                col2_text.append(text)
    elif page_idx == 2:
        # Page 3
        for b in valid_blocks_sorted:
            x0, y0, x1, y1, text = b
            if y0 >= 580:
                footer_text.append(text)
            else:
                if x0 < 200:
                    col1_text.append(text)
                else:
                    col2_text.append(text)

print("=== HEADER ===")
print("\n".join(header_text))
print("\n=== COLUMN 2 (WORK & SUMMARY) ===")
print("\n".join(col2_text))
print("\n=== COLUMN 1 (EDUCATION & SKILLS) ===")
print("\n".join(col1_text))
print("\n=== FOOTER ===")
print("\n".join(footer_text))

# Let's combine them into a single stream
full_stream = []
full_stream.extend(header_text)
full_stream.append("\nWORK EXPERIENCE\n")
full_stream.extend(col2_text)
full_stream.append("\nEDUCATION\n")
full_stream.extend(col1_text)
full_stream.extend(footer_text)

with open("scratch/harneet_reconstructed.txt", "w", encoding="utf-8") as f:
    f.write("\n\n".join(full_stream))
print("\nReconstructed text written to scratch/harneet_reconstructed.txt")
