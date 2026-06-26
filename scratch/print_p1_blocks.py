import os
import fitz

pdf_path = os.path.join(os.path.dirname(__file__), 'harneet_resume.pdf')
doc = fitz.open(pdf_path)

page = doc[0]
print("--- PAGE 1 BLOCKS ---")
blocks = page.get_text("blocks")
# Sort blocks by y0
blocks_sorted = sorted(blocks, key=lambda b: b[1])
for b in blocks_sorted:
    x0, y0, x1, y1, text, block_no, block_type = b
    text_clean = text.replace('\n', ' ').strip()
    if text_clean:
        print(f"[{x0:6.1f}, {y0:6.1f}, {x1:6.1f}, {y1:6.1f}] -> {text_clean}")
