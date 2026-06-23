import re

text = "Laxmi Sudharshan\nlaxmi@example.com\n+91 98765 43210\nExperience: Python Developer"

phone_match = re.search(r'(?:\+?\d{1,3}[- ]?)?(?:\d[- ]?){9}\d', text)
print("phone_match group(0):", phone_match.group(0) if phone_match else "None")

phone = re.sub(r'[\s-]', '', phone_match.group(0))[-10:] if phone_match else ""
print("extracted phone:", phone)
