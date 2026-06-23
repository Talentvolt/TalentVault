import re
import json

raw_text = """
WORK EXPERIENCE Project Management Professional - PMP
Project Management Institute Certification
Number: 3979067
Operations Manager 2
Valid upto November 2027
Webhelp Concentrix
03-2020 - Present
PROJECTS
- Manage three sub-business verticals comprising
250+ employees, driving key performance
Project Revenue Improvisation
indicators (KPIs) across multiple units to enhance
42 Months
utilization, quality, and productivity, ensuring
Improvised revenue generation by optimising
successful and timely client deliverables.
- Lead ABRs, QBRs, MBRs, WBRs, and various
headcount of the team and removing the
business review meetings to report critical
leakages in the project for continous sustainance
metrics, identify performance improvement
and improvement of the LoB wise delivery and
opportunities, and sustain long-term project
improvement in the delivery hours.
success.
The project involves continous traction, rigrous
- Maintain and optimize headcount movement
actions and anticipating revenue of 25+ lines of
plans across 35 sub-line verticals to ensure
business in the process. This was sustained and
optimal staffing levels aligned with revenue
we were able to avoid leakage of 3.28% in the
targets and month-end operational goals.
- Achieve 100% revenue realization site-wide by
project and 88% efficiency across multiple lines
minimizing leakage through effective optimization
of business.
of billable hours across all sub-line businesses.

- Mentor and support 25+ team leaders and 2 Live Tool Improvement
operations managers across multiple verticals, 10 Months
fostering KPI adherence and strengthening client
Suggestion to the bytedance team to integrate
relationship management.
there existing old platform with there new
platform by supporting them on tool suggestion
and improvement about the addons required to
streamline ancillary processes, optimize overhead
monitor live stream, playback feature on live
hours, and ensure on-time delivery across all sub-
stream, box feature etc
business verticals.
- Oversee UK-based client Creative X with 80+
full-time employees for ad moderation, enhancing
KPI compliance and driving continuous process
improvements.
- Develop and refine platform guidelines to
improve ad targeting accuracy and clarity,
resulting in enhanced customer reach and
increased user satisfaction.
Associate Customer Service Manager
Urban Company (UC)
02-2019 - 12-2019
- Established and optimized end-to-end
operational processes for customers and
professionals in the UAE market, increasing
overall efficiency by 20%.
- Launched five new service categories in the
UAE, expanding market presence and driving a
25% increase in customer acquisition.
- Elevate Net Promoter Score (NPS) from 45 to
78, significantly boosting customer satisfaction
and loyalty metrics.
- Streamlined operational interventions, reducing
issue rates from 14% to 6% within six months,
enhancing service reliability and customer
retention.
Transaction and Risk Manager
Amazon
10-2017 - 01-2019
- Managed risk for TRMS, effectively safeguarding
buyers from fraudulent activities and maintaining
risk levels below 2%.
- Revamped and standardized Business SOPs,
consistently reducing buyer risk to under 0.2%.
Assistant Manager
Concentrix
06-2010 - 09-2017
Experience with IBM/CNX for US, UK & IN
"""

lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

# Correct regex distribution
date_range_regex = re.compile(
    r'\b(\d{1,2}[-/]\d{2,4}|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\s*[-–to\s]+\s*(\d{1,2}[-/]\d{2,4}|present|current|today|19\d\d|20\d\d|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-/ ]?\d{2,4})\b',
    re.IGNORECASE
)

designation_keywords = [
    'manager', 'developer', 'executive', 'engineer', 'lead', 'associate', 'specialist', 'director', 
    'analyst', 'consultant', 'officer', 'administrator', 'coordinator', 'technician', 'representative', 
    'intern', 'programmer', 'architect', 'head', 'founder', 'co-founder', 'ceo', 'cto', 'supervisor',
    'leader', 'operator', 'agent', 'specialist', 'strategist', 'consultant', 'advisor', 'expert'
]

description_start_keywords = [
    "manage", "lead", "maintain", "achieve", "collaborate", "oversaw", "responsible", 
    "experience", "rectifying", "improving", "training", "coaching", "publishing", 
    "handling", "headed", "interacting", "streamline", "establish", "launch", "elevate", 
    "identify", "resolve", "implement", "redesign", "coordinate", "ensure", "support",
    "developed", "designed", "built", "created", "worked", "assisted", "monitored",
    "analyzed", "facilitated", "supervised"
]

def is_designation_line(line):
    if line.strip().startswith(('-', '•', '*', '+')):
        return False
    lower_line = line.lower()
    if len(line) > 100:
        return False
    return any(re.search(r'\b' + re.escape(kw) + r'\b', lower_line) for kw in designation_keywords)

def is_description_line(line):
    line_clean = line.strip().lstrip('-•*+ ').strip()
    if not line_clean:
        return True
    first_word = line_clean.split()[0].lower()
    if line.strip().startswith(('-', '•', '*', '+')):
        return True
    if first_word in description_start_keywords:
        return True
    if len(line) > 120 or line.endswith(('.', ';')):
        return True
    return False

# Grouping logic
work_lines = []
is_work = False
for line in lines:
    if "WORK EXPERIENCE" in line:
        is_work = True
        line = line.replace("WORK EXPERIENCE", "").strip()
        if not line:
            continue
    if is_work:
        if any(h in line.upper() for h in ["EDUCATION", "PROJECTS", "LANGUAGES", "HOBBIES", "CERTIFICATION"]):
            continue
        work_lines.append(line)

work_blocks = []
current_block = {
    "header_lines": [],
    "date_line": "",
    "description_lines": []
}

for line in work_lines:
    line_str = line.strip()
    if not line_str:
        continue
        
    is_date = bool(date_range_regex.search(line_str))
    is_desc = is_description_line(line_str)
    is_desig = is_designation_line(line_str)
    
    if is_date and current_block["date_line"]:
        work_blocks.append(current_block)
        current_block = {"header_lines": [], "date_line": "", "description_lines": []}
    elif is_desig and current_block["description_lines"]:
        work_blocks.append(current_block)
        current_block = {"header_lines": [], "date_line": "", "description_lines": []}
        
    if is_date:
        current_block["date_line"] = line_str
    elif is_desc:
        current_block["description_lines"].append(line_str)
    else:
        current_block["header_lines"].append(line_str)
        
# Append last block
if current_block["header_lines"] or current_block["date_line"] or current_block["description_lines"]:
    work_blocks.append(current_block)

experiences = []
for block in work_blocks:
    description = "\n".join(block["description_lines"])
    
    start_date_val = "2022-01-01"
    end_date_val = "2024-01-01"
    if block["date_line"]:
        match = date_range_regex.search(block["date_line"])
        if match:
            start_date_val = match.group(1).strip() if match.group(1) else "2022-01-01"
            end_date_val = match.group(2).strip() if match.group(2) else "Present"
    
    designation = "Role"
    company = "Company"
    
    headers = [h.strip() for h in block["header_lines"] if h.strip()]
    
    designation_line = ""
    designation_idx = -1
    for idx, h in enumerate(headers):
        if is_designation_line(h):
            designation_line = h
            designation_idx = idx
            break
            
    if designation_line:
        designation = designation_line
        other_headers = [h for i, h in enumerate(headers) if i != designation_idx]
        if other_headers:
            company = other_headers[0]
    else:
        if len(headers) == 1:
            designation = headers[0]
        elif len(headers) >= 2:
            designation = headers[0]
            company = headers[1]
            
    # If the designation contains a company separator, split it!
    for sep in [" at ", " @ ", " - ", " | ", " , "]:
        if sep in designation:
            parts = designation.split(sep, 1)
            designation = parts[0].strip()
            company = parts[1].strip()
            break
            
    company = re.sub(r'\s*\([^)]*\)', '', company).strip()
    designation = re.sub(r'\s*\([^)]*\)', '', designation).strip()
    
    experiences.append({
        "designation": designation or "Role",
        "company": company or "Company",
        "description": description,
        "start_date": start_date_val,
        "end_date": end_date_val
    })

print(json.dumps(experiences, indent=2))
