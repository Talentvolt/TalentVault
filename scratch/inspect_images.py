import os
import fitz

def inspect_images(pdf_path):
    print("\n" + "="*80)
    print(f"IMAGES IN: {pdf_path}")
    print("="*80)
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found")
        return
        
    doc = fitz.open(pdf_path)
    for page_idx, page in enumerate(doc):
        images = page.get_images(full=True)
        print(f"Page {page_idx+1} has {len(images)} images")
        for img_idx, img_info in enumerate(images):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            width = base_image.get("width")
            height = base_image.get("height")
            ext = base_image.get("ext")
            img_bytes = base_image.get("image")
            print(f"  Image {img_idx+1}: xref={xref}, width={width}, height={height}, ext={ext}, size={len(img_bytes)} bytes")

if __name__ == "__main__":
    inspect_images("scratch/shreya_chavda_Shreya_ZdEAJej.pdf")
    inspect_images("scratch/vikke_gupta_Naukri_VikkeGupta16y_0m.pdf")
