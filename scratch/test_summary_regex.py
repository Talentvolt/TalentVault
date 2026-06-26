import re

summary = """A dedicated and enthusiastic individual currently pursuing a B.A. in Psychology from
Gujarat University, with a strong academic foundation in science from Adani Vidya
Mandir (CBSE Board). Possess 1 year of hands-on experience as a Marketing
Executive and in Floor Management, demonstrating a solid understanding of brand
communication, customer engagement, and operational coordination. Known for
excellent interpersonal skills, attention to detail, and the ability to adapt quickly in
dynamic environments. Eager to leverage academic knowledge and practical
experience to contribute effectively in marketing, coordination, or customer-facing
roles."""

current_desig = "marketing executive"

summary_clean = " ".join(summary.split())
match = re.search(r'experience as a?\s*([^,.]+?)\s+and\s+(?:in\s+)?([^,.]+)', summary_clean, re.I)
if match:
    print("Match found!")
    print("Group 1:", repr(match.group(1)))
    print("Group 2:", repr(match.group(2)))
else:
    print("No match found.")
