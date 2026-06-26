import re
import json

with open("scratch/harneet_pymupdf_text.txt", "r", encoding="utf-8") as f:
    text = f.read()

def detect_heading_type(line_str):
    l = line_str.strip().lower()
    l = re.sub(r'[:\-\s]+$', '', l).strip()
    if len(l) > 60 or len(l) < 3:
        return None
    
    # Exact or close matching
    if l in ["work experience", "experience", "employment history", "work history", "professional experience"]:
        return "WORK"
    if l in ["education", "academic", "academic background", "qualification", "qualifications", "education history"]:
        return "EDU"
    if l in ["projects", "personal projects", "academic projects", "key projects"]:
        return "PROJECT"
    if l in ["technical skills", "core competencies", "skills", "key skills", "expertise", "competencies"]:
        return "SKILLS"
    if l in ["languages", "languages known"]:
        return "LANGUAGES"
    if l in ["personal details", "personal profile", "personal summary"]:
        return "PERSONAL"
    if l in ["profile summary", "summary", "career objective", "objective", "professional summary", "about me"]:
        return "SUMMARY"
    if l in ["notable accomplishments across the career"]:
        return "OTHER"
        
    return None

raw_lines = text.split('\n')
current_section = None
header_info_lines = []
sections = {
    "WORK": [],
    "EDU": [],
    "PROJECT": [],
    "CERT": [],
    "SKILLS": [],
    "SUMMARY": [],
    "LANGUAGES": [],
    "PERSONAL": [],
    "OTHER": []
}

date_range_regex = re.compile(
    r'\b(\d{1,2}[-/]\d{2,4}|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\s*[-–to\s]+\s*(\d{1,2}[-/]\d{2,4}|present|current|today|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\b',
    re.IGNORECASE
)

designation_keywords = [
    'manager', 'developer', 'executive', 'engineer', 'lead', 'associate', 'specialist', 'director', 
    'analyst', 'consultant', 'officer', 'administrator', 'coordinator', 'technician', 'representative', 
    'intern', 'programmer', 'architect', 'head', 'founder', 'co-founder', 'ceo', 'cto', 'supervisor',
    'leader', 'operator', 'agent', 'specialist', 'strategist', 'consultant', 'advisor', 'expert', 'auditor'
]

action_verbs = [
    'drove', 'ensured', 'maintained', 'strengthened', 'monitored', 'led', 'collaborated', 
    'performed', 'oversaw', 'directed', 'prepared', 'optimized', 'liaised', 'tracked', 
    'governed', 'crafted', 'built', 'delivered', 'reviewed', 'partnered', 'spearheaded',
    'successfully', 'instrumental', 'achieved', 'contributed', 'liaised', 'assisted',
    'supporting', 'developing', 'managing', 'providing', 'handling', 'identifying'
]

for line in raw_lines:
    line_str = line.strip()
    if not line_str:
        continue
    
    # Skip page boundary markers
    if line_str.startswith("--- PAGE"):
        continue
        
    heading_type = detect_heading_type(line_str)
    if heading_type:
        current_section = heading_type
        continue
        
    # Check for implicit transition to WORK:
    date_match = date_range_regex.search(line_str)
    if date_match:
        non_date_text = line_str.replace(date_match.group(0), "").strip()
        non_date_text = re.sub(r'^[|/\-\s\.,:]+|[|/\-\s\.,:]+$', '', non_date_text).strip()
        if len(non_date_text) > 3 and any(char.isalpha() for char in non_date_text):
            current_section = "WORK"
    elif current_section in ["SKILLS", "OTHER"]:
        is_bullet = line_str.startswith(('-', '•', '*', '+'))
        if not is_bullet and len(line_str) < 120:
            l_lower = line_str.lower()
            if not l_lower.startswith("key result areas") and any(re.search(r'\b' + re.escape(kw) + r'\b', l_lower) for kw in designation_keywords):
                first_word = re.sub(r'[^a-zA-Z]', '', line_str.split()[0].lower()) if line_str.split() else ""
                if first_word not in action_verbs and "leadership" not in l_lower and "summary" not in l_lower:
                    current_section = "WORK"
                
    if current_section is None:
        header_info_lines.append(line_str)
    else:
        if current_section in ["SKILLS", "OTHER"]:
            is_bullet = line_str.startswith(('-', '•', '*', '+'))
            is_long = len(line_str) > 50
            first_word = re.sub(r'[^a-zA-Z]', '', line_str.split()[0].lower()) if line_str.split() else ""
            is_action = first_word in action_verbs
            
            if is_bullet or is_long or is_action:
                sections["WORK"].append(line_str)
                continue
                
        sections[current_section].append(line_str)

# 1. Parse Work Experiences
work_blocks = []
current_block = {
    "title_line": "",
    "description_lines": []
}

for line in sections["WORK"]:
    line_str = line.strip()
    if not line_str:
        continue
        
    date_match = date_range_regex.search(line_str)
    is_new_job_line = False
    
    if date_match:
        non_date_text = line_str.replace(date_match.group(0), "").strip()
        non_date_text = re.sub(r'^[|/\-\s\.,:]+|[|/\-\s\.,:]+$', '', non_date_text).strip()
        if len(non_date_text) > 3 and any(char.isalpha() for char in non_date_text):
            is_new_job_line = True
    else:
        is_bullet = line_str.startswith(('-', '•', '*', '+'))
        if not is_bullet and len(line_str) < 120:
            l_lower = line_str.lower()
            first_word = re.sub(r'[^a-zA-Z]', '', line_str.split()[0].lower()) if line_str.split() else ""
            if l_lower.startswith("key result areas"):
                is_new_job_line = False
            elif first_word in action_verbs:
                is_new_job_line = False
            elif any(re.search(r'\b' + re.escape(kw) + r'\b', l_lower) for kw in designation_keywords):
                if "leadership" not in l_lower and "summary" not in l_lower:
                    is_new_job_line = True
                
    if is_new_job_line:
        if current_block["title_line"].strip():
            work_blocks.append(current_block)
        current_block = {
            "title_line": line_str,
            "description_lines": []
        }
    else:
        current_block["description_lines"].append(line_str)

if current_block["title_line"].strip():
    work_blocks.append(current_block)

experiences = []
for block in work_blocks:
    title_line = block["title_line"]
    date_match = date_range_regex.search(title_line)
    date_str = ""
    start_date_val = ""
    end_date_val = ""
    if date_match:
        date_str = date_match.group(0)
        raw_start = date_match.group(1).strip() if date_match.group(1) else ""
        raw_end = date_match.group(2).strip() if date_match.group(2) else ""
        start_date_val = raw_start
        end_date_val = raw_end
        
    title_clean = title_line.replace(date_str, "").strip()
    title_clean = re.sub(r'^[|/\-\s\.,:]+|[|/\-\s\.,:]+$', '', title_clean).strip()
    
    parts = [p.strip() for p in re.split(r'[|]+', title_clean) if p.strip()]
    if len(parts) == 1:
        parts = [p.strip() for p in re.split(r'[,–\-]+', title_clean) if p.strip()]
        
    designation = ""
    company = ""
    location = ""
    
    if len(parts) >= 1:
        designation = parts[0]
    if len(parts) >= 2:
        company = parts[1]
    if len(parts) >= 3:
        location = parts[2]
        
    designation = re.sub(r'^(presently|currently|actively)?\s*working\s+as\s+', '', designation, flags=re.I).strip()
    designation = re.sub(r'^worked\s+as\s+', '', designation, flags=re.I).strip()
    designation = re.sub(r'^role\s*:\s*', '', designation, flags=re.I).strip()
    
    # Split designation by company separators if company is empty
    if designation and not company:
        company_separators = [r'\bin\b', r'\bat\b', r'\bfor\b', r'\bwith\b', r'\b@\b', r'\s*-\s*', r'\s*\|\s*']
        for sep in company_separators:
            c_parts = re.split(sep, designation, maxsplit=1, flags=re.I)
            if len(c_parts) == 2:
                designation = c_parts[0].strip()
                company = c_parts[1].strip()
                break

    desc_lines = []
    for line in block["description_lines"]:
        line_str = line.strip()
        if not line_str:
            continue
        if line_str.lower().startswith("key result areas"):
            desc_lines.append(line_str)
        else:
            line_clean = line_str.lstrip('-•*+ ').strip()
            if line_clean:
                desc_lines.append(f"• {line_clean}")
                
    description = "\n".join(desc_lines)
    
    experiences.append({
        "designation": designation,
        "company": company,
        "location": location,
        "start_date": start_date_val,
        "end_date": end_date_val,
        "description_summary": description[:60] + "..."
    })

# Print parsed outputs
print(f"EXPERIENCES COUNT: {len(experiences)}")
for idx, exp in enumerate(experiences):
    print(f" {idx+1}. {exp['designation']} @ {exp['company']} ({exp['start_date']} - {exp['end_date']})")
