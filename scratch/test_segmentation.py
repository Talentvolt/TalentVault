import re

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
- Collaborate with workforce management and
platform by supporting them on tool suggestion
finance teams to prepare accurate site invoices,
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
- Elevated Net Promoter Score (NPS) from 45 to
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

date_pattern = re.compile(
    r'\b(19\d\d|20\d\d|0?\d/19\d\d|0?\d/20\d\d|0?\d-19\d\d|0?\d-20\d\d|'
    r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(?:19\d\d|20\d\d))\b'
    r'\s*[-–to\s]+\s*'
    r'\b(present|current|today|19\d\d|20\d\d|0?\d/19\d\d|0?\d/20\d\d|0?\d-19\d\d|0?\d-20\d\d|'
    r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(?:19\d\d|20\d\d))\b',
    re.IGNORECASE
)

designation_keywords = [
    'manager', 'developer', 'executive', 'engineer', 'lead', 'associate', 'specialist', 'director', 
    'analyst', 'consultant', 'officer', 'administrator', 'coordinator', 'technician', 'representative', 
    'intern', 'programmer', 'architect', 'head', 'founder', 'co-founder', 'ceo', 'cto', 'supervisor'
]

# Extract work experience lines (all lines after WORK EXPERIENCE start)
work_lines = []
is_work = False
for line in lines:
    if "WORK EXPERIENCE" in line:
        is_work = True
        # remove section header
        line = line.replace("WORK EXPERIENCE", "").strip()
        if not line:
            continue
    elif any(h in line.upper() for h in ["EDUCATION", "PROJECTS", "LANGUAGES", "HOBBIES", "CERTIFICATION"]):
        # But wait, in the raw text projects and certification are interleaved on the right.
        # For this test, we assume we just scan the list of lines.
        pass
    if is_work:
        # Ignore columns from the right side of the page (PROJECTS, etc.)
        # If the line contains "Project Revenue", "Live Tool", etc. we can filter it out or just run the parser
        work_lines.append(line)

print("Total lines found under WORK:", len(work_lines))

# Grouping logic
blocks = []
current_block = {
    "title_candidate_lines": [],
    "date_line": "",
    "description_lines": []
}

for line in work_lines:
    is_date = bool(date_pattern.search(line))
    # Check if bullet point or starts with typical bullet/action verb
    is_bullet = line.startswith(('-', '•', '*', '+'))
    
    # We trigger a new block if:
    # 1. We find a date line, and the current block already has a date line
    # 2. We find a designation/company candidate line, and the current block already has description lines
    if is_date and current_block["date_line"]:
        blocks.append(current_block)
        current_block = {
            "title_candidate_lines": [],
            "date_line": "",
            "description_lines": []
        }
    elif not is_date and not is_bullet and current_block["description_lines"]:
        # If it's a non-bullet line, and we already have description lines, it starts a new job!
        blocks.append(current_block)
        current_block = {
            "title_candidate_lines": [],
            "date_line": "",
            "description_lines": []
        }
        
    if is_date:
        current_block["date_line"] = line
    elif is_bullet:
        current_block["description_lines"].append(line)
    else:
        # Check if it looks like description anyway (e.g. starts with action verb or Experience with...)
        lower_line = line.lower()
        if lower_line.startswith(("manage", "lead", "maintain", "achieve", "collaborate", "oversaw", "responsible", "experience with")):
            current_block["description_lines"].append(line)
        else:
            current_block["title_candidate_lines"].append(line)

# Add last block
if current_block["title_candidate_lines"] or current_block["date_line"] or current_block["description_lines"]:
    blocks.append(current_block)

print(f"\nGrouped into {len(blocks)} blocks:")
for idx, b in enumerate(blocks):
    print(f"\nBLOCK {idx+1}:")
    print("  Title Candidates:", b["title_candidate_lines"])
    print("  Date Line:", b["date_line"])
    print("  Description Lines count:", len(b["description_lines"]))

# Now let's parse title & company from each block
experiences = []
for b in blocks:
    title = "Role"
    company = "Company"
    
    candidates = [c for c in b["title_candidate_lines"] if len(c) > 2]
    
    # Heuristic for 1 candidate line
    if len(candidates) == 1:
        line = candidates[0]
        # Look for separators
        for sep in [" at ", " - ", " @ ", " | ", " , "]:
            if sep in line:
                parts = line.split(sep, 1)
                title = parts[0].strip()
                company = parts[1].strip()
                break
        else:
            title = line
    elif len(candidates) >= 2:
        # Determine which line is the title (designation)
        line1 = candidates[0]
        line2 = candidates[1]
        
        has_deg1 = any(kw in line1.lower() for kw in designation_keywords)
        has_deg2 = any(kw in line2.lower() for kw in designation_keywords)
        
        if has_deg1 and not has_deg2:
            title = line1
            company = line2
        elif has_deg2 and not has_deg1:
            title = line2
            company = line1
        else:
            title = line1
            company = line2
            
    # Extract dates
    start_date = "2022-01-01"
    end_date = "2024-01-01"
    if b["date_line"]:
        match = date_pattern.search(b["date_line"])
        if match:
            start_date = match.group(1).strip()
            end_date = match.group(2).strip()
            
    experiences.append({
        "designation": title.strip(),
        "company": company.strip(),
        "description": "\n".join(b["description_lines"]),
        "start_date": start_date,
        "end_date": end_date
    })

print("\n--- EXTRACTED EXPERIENCES JSON ---")
import json
print(json.dumps(experiences, indent=2))
