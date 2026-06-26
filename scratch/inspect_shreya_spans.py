import fitz
doc = fitz.open("scratch/shreya_chavda_Shreya_ZdEAJej.pdf")
page = doc[0]
blocks_dict = page.get_text("dict")
count = 0
for b in blocks_dict.get("blocks", []):
    if b.get("type") == 0: # text block
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                print(f"Span {count}: {span.get('text')!r} | Size: {span.get('size')} | Font: {span.get('font')} | Flags: {span.get('flags')}")
                count += 1
                if count >= 60:
                    break
            if count >= 60:
                break
        if count >= 60:
            break
