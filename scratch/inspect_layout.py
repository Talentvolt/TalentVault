import os
import fitz

def inspect_pdf_layout(pdf_path):
    print("\n" + "="*80)
    print(f"LAYOUT INSPECTION: {pdf_path}")
    print("="*80)
    
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} does not exist")
        return
        
    doc = fitz.open(pdf_path)
    for page_idx, page in enumerate(doc):
        print(f"\n--- PAGE {page_idx+1} (Width: {page.rect.width}, Height: {page.rect.height}) ---")
        
        # We will get blocks, which contains: (x0, y0, x1, y1, "text", block_no, block_type)
        blocks = page.get_text("blocks")
        # Sort blocks by y0, then x0 to print in a readable layout-aware way
        # but let's also see their raw coordinates
        for b in blocks:
            x0, y0, x1, y1, text, block_no, block_type = b
            text_clean = " | ".join([line.strip() for line in text.split('\n') if line.strip()])
            print(f"Block {block_no} (x0={x0:.1f}, y0={y0:.1f}, x1={x1:.1f}, y1={y1:.1f}): {text_clean[:120]}")

if __name__ == "__main__":
    inspect_pdf_layout("scratch/shreya_chavda_Shreya_ZdEAJej.pdf")
    inspect_pdf_layout("scratch/vikke_gupta_Naukri_VikkeGupta16y_0m.pdf")
