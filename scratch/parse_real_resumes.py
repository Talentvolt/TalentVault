import os
import sys
import json
import re

# Setup Django settings
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
import django
django.setup()

from services.resume_intelligence import ResumeIntelligenceService
import fitz

def reconstruct_pdf_layout(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    
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
                        if len(text) > 3 and any(c.isalpha() for c in text):
                            if text.lower() not in ["education", "experience", "work experience", "skills", "projects", "certifications", "profile", "summary"]:
                                if size > largest_font_size:
                                    largest_font_size = size
                                    bbox = span.get("bbox", (0,0,0,0))
                                    name_block_x_center = (bbox[0] + bbox[2]) / 2

    main_stream_parts = []
    sidebar_stream_parts = []
    
    right_column_first = False
    
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
            
        best_x = None
        min_cross = 9999
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
                if cross_count < min_cross:
                    min_cross = cross_count
                    best_x = x
                elif cross_count == min_cross:
                    if best_x is None or abs(x - 297.5) < abs(best_x - 297.5):
                        best_x = x
                        
        has_columns = best_x is not None and min_cross <= max(2, len(valid_blocks) * 0.25)
        
        if page_idx == 0 and has_columns:
            if name_block_x_center > best_x:
                right_column_first = True
                
        if has_columns:
            header_blocks = []
            footer_blocks = []
            left_blocks = []
            right_blocks = []
            
            for b in valid_blocks:
                x0, y0, x1, y1, text = b
                if x0 < best_x < x1:
                    if y1 < 150:
                        header_blocks.append(b)
                    elif y0 > 700:
                        footer_blocks.append(b)
                    else:
                        center_x = (x0 + x1) / 2
                        if center_x <= best_x:
                            left_blocks.append(b)
                        else:
                            right_blocks.append(b)
                elif x1 <= best_x:
                    left_blocks.append(b)
                else:
                    right_blocks.append(b)
                    
            header_blocks.sort(key=lambda x: x[1])
            footer_blocks.sort(key=lambda x: x[1])
            left_blocks.sort(key=lambda x: x[1])
            right_blocks.sort(key=lambda x: x[1])
            
            main_parts = []
            if header_blocks:
                main_parts.append("\n".join([b[4] for b in header_blocks]))
                
            left_text = "\n".join([b[4] for b in left_blocks])
            right_text = "\n".join([b[4] for b in right_blocks])
            
            if right_column_first:
                if right_text: main_parts.append(right_text)
                if left_text: sidebar_stream_parts.append(left_text)
            else:
                if left_text: main_parts.append(left_text)
                if right_text: sidebar_stream_parts.append(right_text)
                
            if footer_blocks:
                main_parts.append("\n".join([b[4] for b in footer_blocks]))
                
            if main_parts:
                main_stream_parts.append("\n\n".join(main_parts))
        else:
            valid_blocks.sort(key=lambda x: x[1])
            main_stream_parts.append("\n\n".join([b[4] for b in valid_blocks]))
            
    reconstructed_text = "\n\n".join(main_stream_parts)
    if sidebar_stream_parts:
        reconstructed_text += "\n\n=== COLUMN RESET ===\n\n" + "\n\n".join(sidebar_stream_parts)
        
    return reconstructed_text

def parse_work_experience_custom(work_lines) -> list:
    job_blocks = []
    current_block = []
    
    date_range_regex = re.compile(
        r'\b(\d{1,2}[-/]\d{2,4}|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\s*[-–to\s]+\s*(\d{1,2}[-/]\d{2,4}|present|current|today|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\b',
        re.IGNORECASE
    )
    
    designation_keywords = {
        'manager', 'developer', 'executive', 'engineer', 'lead', 'associate', 'specialist', 'director', 
        'analyst', 'consultant', 'officer', 'administrator', 'coordinator', 'technician', 'representative', 
        'intern', 'programmer', 'architect', 'head', 'founder', 'co-founder', 'ceo', 'cto', 'supervisor',
        'leader', 'operator', 'agent', 'strategist', 'advisor', 'expert', 'auditor', 'salesperson'
    }
    
    company_keywords = {
        'ltd', 'limited', 'pvt', 'private', 'llp', 'llc', 'inc', 'company',
        'corporation', 'technologies', 'solutions', 'industries', 'group', 'corp', 'jewellers'
    }
    
    responsibility_keywords = {
        'managing', 'handling', 'ensuring', 'reporting', 'coordinating', 'developing', 
        'providing', 'assisting', 'performing', 'working', 'responsible', 'led', 
        'managed', 'coordinated', 'assisted', 'prepared', 'monitored', 'maintained',
        'drove', 'ensured', 'strengthened', 'oversaw', 'directed', 'optimized', 'tracked', 
        'governed', 'crafted', 'built', 'delivered', 'reviewed', 'partnered', 'spearheaded',
        'achieved', 'contributed', 'liaised', 'supporting', 'giving', 'execute', 'implementation',
        'involved', 'handling', 'floor', 'inventory', 'to', 'maintain', 'fostering', 'monitor',
        'lead', 'manage', 'coordinate', 'prepare', 'monitor', 'maintain', 'perform', 'ensure', 'assist', 'provide'
    }

    in_description = False
    
    for line in work_lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        is_bullet = line_str.startswith(('-', '•', '*', '+'))
        has_date = bool(date_range_regex.search(line_str))
        
        words = re.sub(r'[^a-zA-Z\s]', ' ', line_str).lower().split()
        first_word = words[0] if words else ""
        is_resp = is_bullet or (first_word in responsibility_keywords)
        
        is_new = False
        if current_block:
            if has_date:
                block_has_date = any(date_range_regex.search(b) for b in current_block)
                if block_has_date or in_description:
                    is_new = True
            elif in_description and not is_resp and len(line_str) < 80:
                has_desig = any(w in designation_keywords for w in words)
                has_comp = any(w in company_keywords for w in words)
                if has_desig or has_comp:
                    is_new = True
                    
        if is_new:
            # Pull-up heuristic: if the last line of the current block was a potential company name
            # (short, capitalized, no bullets, not responsibility), pull it into the new block
            pulled_line = None
            if current_block and len(current_block) > 1:
                last_line = current_block[-1].strip()
                last_words = re.sub(r'[^a-zA-Z\s]', ' ', last_line).lower().split()
                last_first_word = last_words[0] if last_words else ""
                
                is_last_bullet = last_line.startswith(('-', '•', '*', '+'))
                is_last_resp = is_last_bullet or (last_first_word in responsibility_keywords)
                
                if not is_last_bullet and not is_last_resp and len(last_line) < 60 and last_line[0].isupper():
                    pulled_line = current_block.pop()
                    
            job_blocks.append(current_block)
            
            if pulled_line:
                current_block = [pulled_line, line_str]
            else:
                current_block = [line_str]
            in_description = False
        else:
            current_block.append(line_str)
            
        if is_resp:
            in_description = True
            
    if current_block:
        job_blocks.append(current_block)
        
    experiences = []
    for block in job_blocks:
        header_lines = []
        desc_lines = []
        
        block_in_desc = False
        for line in block:
            line_str = line.strip()
            is_bullet = line_str.startswith(('-', '•', '*', '+'))
            words = re.sub(r'[^a-zA-Z\s]', ' ', line_str).lower().split()
            first_word = words[0] if words else ""
            is_resp = is_bullet or (first_word in responsibility_keywords)
            
            if is_resp:
                block_in_desc = True
                
            if block_in_desc:
                desc_lines.append(line_str)
            else:
                header_lines.append(line_str)
                
        if not header_lines and block:
            header_lines = [block[0]]
            desc_lines = block[1:]
            
        date_str = ""
        start_date_val = ""
        end_date_val = ""
        
        remaining_headers = []
        for h in header_lines:
            dm = date_range_regex.search(h)
            if dm:
                date_str = dm.group(0)
                raw_start = dm.group(1).strip() if dm.group(1) else ""
                raw_end = dm.group(2).strip() if dm.group(2) else ""
                start_date_val = ResumeIntelligenceService.normalize_date_to_string(raw_start, is_end=False) or ""
                end_date_val = ResumeIntelligenceService.normalize_date_to_string(raw_end, is_end=True) or ""
                
                h_clean = h.replace(date_str, "").strip()
                h_clean = re.sub(r'^[|/\-\s\.,:]+|[|/\-\s\.,:]+$', '', h_clean).strip()
                if h_clean:
                    remaining_headers.append(h_clean)
            else:
                remaining_headers.append(h)
                
        designation = ""
        company = ""
        location = ""
        
        desig_line_idx = -1
        for idx, h in enumerate(remaining_headers):
            words = re.sub(r'[^a-zA-Z\s]', ' ', h).lower().split()
            if any(w in designation_keywords for w in words):
                desig_line_idx = idx
                designation = h
                break
                
        if desig_line_idx == -1 and remaining_headers:
            desig_line_idx = 0
            designation = remaining_headers[0]
            
        other_headers = [h for idx, h in enumerate(remaining_headers) if idx != desig_line_idx]
        
        if other_headers:
            comp_line_idx = -1
            for idx, h in enumerate(other_headers):
                words = re.sub(r'[^a-zA-Z\s]', ' ', h).lower().split()
                if any(w in company_keywords for w in words):
                    comp_line_idx = idx
                    company = h
                    break
            if comp_line_idx != -1:
                company = other_headers[comp_line_idx]
                loc_headers = [h for idx, h in enumerate(other_headers) if idx != comp_line_idx]
                if loc_headers:
                    location = loc_headers[0]
            else:
                company = other_headers[0]
                if len(other_headers) > 1:
                    location = other_headers[1]
        
        if designation and not company:
            for sep in [r'\bin\b', r'\bat\b', r'\bfor\b', r'\bwith\b', r'\b@\b', r'\s*-\s*', r'\s*\|\s*']:
                c_parts = re.split(sep, designation, maxsplit=1, flags=re.I)
                if len(c_parts) == 2:
                    designation = c_parts[0].strip()
                    company = c_parts[1].strip()
                    break
                    
        designation = re.sub(r'^(presently|currently|actively)?\s*working\s+as\s+', '', designation, flags=re.I).strip()
        designation = re.sub(r'^worked\s+as\s+', '', designation, flags=re.I).strip()
        designation = re.sub(r'^role\s*:\s*', '', designation, flags=re.I).strip()
        
        designation = re.sub(r'^[•\-\*\+\s\.,]+|[•\-\*\+\s\.,]+$', '', designation).strip()
        company = re.sub(r'^[•\-\*\+\s\.,]+|[•\-\*\+\s\.,]+$', '', company).strip()
        location = re.sub(r'^[•\-\*\+\s\.,]+|[•\-\*\+\s\.,]+$', '', location).strip()
        
        cleaned_desc = []
        for d in desc_lines:
            d_clean = d.strip().lstrip('-•*+ ').strip()
            if d_clean:
                cleaned_desc.append(f"• {d_clean}")
        description = "\n".join(cleaned_desc)
        
        duration = ""
        if start_date_val:
            duration = ResumeIntelligenceService.get_duration_display(start_date_val, end_date_val)
            
        experiences.append({
            "designation": designation or "",
            "company": company or "",
            "location": location or "",
            "duration": duration,
            "description": description,
            "start_date": start_date_val,
            "end_date": end_date_val
        })
        
    return experiences

def test_resume(pdf_path, name):
    print("\n" + "="*50)
    print(f"TESTING {name}: {pdf_path}")
    print("="*50)
    
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    text = reconstruct_pdf_layout(file_bytes)
    
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    work_lines = []
    current_section = None
    
    for line in lines:
        if "=== COLUMN RESET ===" in line:
            current_section = None
            continue
        heading_type = ResumeIntelligenceService.detect_heading_type(line)
        if heading_type:
            current_section = heading_type
            continue
        if current_section == "WORK":
            work_lines.append(line)
            
    custom_exps = parse_work_experience_custom(work_lines)
    
    print("\n--- Parsed Output ---")
    print(f"Custom Experience Blocks count: {len(custom_exps)}")
    for i, exp in enumerate(custom_exps):
        print(f"  {i+1}. Designation: {exp['designation']} | Company: {exp['company']} | Dates: {exp['start_date']} to {exp['end_date']}")

if __name__ == "__main__":
    test_resume("scratch/shreya_chavda_Shreya_ZdEAJej.pdf", "Shreya Chavda")
    test_resume("scratch/vikke_gupta_Naukri_VikkeGupta16y_0m.pdf", "Vikke Gupta")
