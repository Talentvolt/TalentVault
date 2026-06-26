import fitz
doc = fitz.open("scratch/shreya_chavda_Shreya_ZdEAJej.pdf")
for i, page in enumerate(doc):
    print(f"--- PAGE {i} ---")
    print(page.get_text("text"))
