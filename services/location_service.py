import re

# Comprehensive Indian Locations Master Database
MASTER_LOCATIONS = [
    # Tier 1 Cities
    {"name": "Delhi NCR", "city": "Delhi NCR", "state": "Delhi", "tier": "Tier 1"},
    {"name": "New Delhi", "city": "New Delhi", "state": "Delhi", "tier": "Tier 1"},
    {"name": "Mumbai", "city": "Mumbai", "state": "Maharashtra", "tier": "Tier 1"},
    {"name": "Navi Mumbai", "city": "Navi Mumbai", "state": "Maharashtra", "tier": "Tier 1"},
    {"name": "Thane", "city": "Thane", "state": "Maharashtra", "tier": "Tier 1"},
    {"name": "Bengaluru", "city": "Bengaluru", "state": "Karnataka", "tier": "Tier 1"},
    {"name": "Bangalore", "city": "Bengaluru", "state": "Karnataka", "tier": "Tier 1"},
    {"name": "Hyderabad", "city": "Hyderabad", "state": "Telangana", "tier": "Tier 1"},
    {"name": "Chennai", "city": "Chennai", "state": "Tamil Nadu", "tier": "Tier 1"},
    {"name": "Kolkata", "city": "Kolkata", "state": "West Bengal", "tier": "Tier 1"},
    {"name": "Pune", "city": "Pune", "state": "Maharashtra", "tier": "Tier 1"},
    {"name": "Ahmedabad", "city": "Ahmedabad", "state": "Gujarat", "tier": "Tier 1"},

    # Tier 2 Cities
    {"name": "Noida", "city": "Noida", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Greater Noida", "city": "Greater Noida", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Greater Noida West", "city": "Greater Noida", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Ghaziabad", "city": "Ghaziabad", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Indirapuram", "city": "Ghaziabad", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Vaishali", "city": "Ghaziabad", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Vasundhara", "city": "Ghaziabad", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Raj Nagar Extension", "city": "Ghaziabad", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Gurugram", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "Gurgaon", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "Manesar", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "Lucknow", "city": "Lucknow", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Jaipur", "city": "Jaipur", "state": "Rajasthan", "tier": "Tier 2"},
    {"name": "Chandigarh", "city": "Chandigarh", "state": "Chandigarh", "tier": "Tier 2"},
    {"name": "Mohali", "city": "Mohali", "state": "Punjab", "tier": "Tier 2"},
    {"name": "Panchkula", "city": "Panchkula", "state": "Haryana", "tier": "Tier 2"},
    {"name": "Indore", "city": "Indore", "state": "Madhya Pradesh", "tier": "Tier 2"},
    {"name": "Bhopal", "city": "Bhopal", "state": "Madhya Pradesh", "tier": "Tier 2"},
    {"name": "Kochi", "city": "Kochi", "state": "Kerala", "tier": "Tier 2"},
    {"name": "Coimbatore", "city": "Coimbatore", "state": "Tamil Nadu", "tier": "Tier 2"},
    {"name": "Surat", "city": "Surat", "state": "Gujarat", "tier": "Tier 2"},
    {"name": "Vadodara", "city": "Vadodara", "state": "Gujarat", "tier": "Tier 2"},
    {"name": "Visakhapatnam", "city": "Visakhapatnam", "state": "Andhra Pradesh", "tier": "Tier 2"},
    {"name": "Patna", "city": "Patna", "state": "Bihar", "tier": "Tier 2"},
    {"name": "Bhubaneswar", "city": "Bhubaneswar", "state": "Odisha", "tier": "Tier 2"},
    {"name": "Nagpur", "city": "Nagpur", "state": "Maharashtra", "tier": "Tier 2"},
    {"name": "Nashik", "city": "Nashik", "state": "Maharashtra", "tier": "Tier 2"},
    {"name": "Mysuru", "city": "Mysuru", "state": "Karnataka", "tier": "Tier 2"},
    {"name": "Vijayawada", "city": "Vijayawada", "state": "Andhra Pradesh", "tier": "Tier 2"},
    {"name": "Raipur", "city": "Raipur", "state": "Chhattisgarh", "tier": "Tier 2"},
    {"name": "Ranchi", "city": "Ranchi", "state": "Jharkhand", "tier": "Tier 2"},
    {"name": "Dehradun", "city": "Dehradun", "state": "Uttarakhand", "tier": "Tier 2"},
    {"name": "Jammu", "city": "Jammu", "state": "Jammu & Kashmir", "tier": "Tier 2"},
    {"name": "Srinagar", "city": "Srinagar", "state": "Jammu & Kashmir", "tier": "Tier 2"},
    {"name": "Guwahati", "city": "Guwahati", "state": "Assam", "tier": "Tier 2"},
    {"name": "Amritsar", "city": "Amritsar", "state": "Punjab", "tier": "Tier 2"},
    {"name": "Ludhiana", "city": "Ludhiana", "state": "Punjab", "tier": "Tier 2"},
    {"name": "Agra", "city": "Agra", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Varanasi", "city": "Varanasi", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Kanpur", "city": "Kanpur", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Prayagraj", "city": "Prayagraj", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Allahabad", "city": "Prayagraj", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Meerut", "city": "Meerut", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Gwalior", "city": "Gwalior", "state": "Madhya Pradesh", "tier": "Tier 2"},
    {"name": "Jabalpur", "city": "Jabalpur", "state": "Madhya Pradesh", "tier": "Tier 2"},
    {"name": "Rajkot", "city": "Rajkot", "state": "Gujarat", "tier": "Tier 2"},
    {"name": "Jodhpur", "city": "Jodhpur", "state": "Rajasthan", "tier": "Tier 2"},
    {"name": "Udaipur", "city": "Udaipur", "state": "Rajasthan", "tier": "Tier 2"},
    {"name": "Madurai", "city": "Madurai", "state": "Tamil Nadu", "tier": "Tier 2"},
    {"name": "Trichy", "city": "Tiruchirappalli", "state": "Tamil Nadu", "tier": "Tier 2"},
    {"name": "Mangaluru", "city": "Mangaluru", "state": "Karnataka", "tier": "Tier 2"},
    {"name": "Belagavi", "city": "Belagavi", "state": "Karnataka", "tier": "Tier 2"},
    {"name": "Hubballi", "city": "Hubballi", "state": "Karnataka", "tier": "Tier 2"},
    {"name": "Kozhikode", "city": "Kozhikode", "state": "Kerala", "tier": "Tier 2"},
    {"name": "Thrissur", "city": "Thrissur", "state": "Kerala", "tier": "Tier 2"},
    {"name": "Tirupati", "city": "Tirupati", "state": "Andhra Pradesh", "tier": "Tier 2"},
    {"name": "Warangal", "city": "Warangal", "state": "Telangana", "tier": "Tier 2"},
    {"name": "Cuttack", "city": "Cuttack", "state": "Odisha", "tier": "Tier 2"},
    {"name": "Rourkela", "city": "Rourkela", "state": "Odisha", "tier": "Tier 2"},
    {"name": "Durgapur", "city": "Durgapur", "state": "West Bengal", "tier": "Tier 2"},
    {"name": "Siliguri", "city": "Siliguri", "state": "West Bengal", "tier": "Tier 2"},
    {"name": "Asansol", "city": "Asansol", "state": "West Bengal", "tier": "Tier 2"},
    {"name": "Agartala", "city": "Agartala", "state": "Tripura", "tier": "Tier 2"},
    {"name": "Shillong", "city": "Shillong", "state": "Meghalaya", "tier": "Tier 2"},
    {"name": "Imphal", "city": "Imphal", "state": "Manipur", "tier": "Tier 2"},
    {"name": "Aizawl", "city": "Aizawl", "state": "Mizoram", "tier": "Tier 2"},
    {"name": "Kohima", "city": "Kohima", "state": "Nagaland", "tier": "Tier 2"},
    {"name": "Itanagar", "city": "Itanagar", "state": "Arunachal Pradesh", "tier": "Tier 2"},
    {"name": "Gangtok", "city": "Gangtok", "state": "Sikkim", "tier": "Tier 2"},
    {"name": "Panaji", "city": "Panaji", "state": "Goa", "tier": "Tier 2"},
    {"name": "Puducherry", "city": "Puducherry", "state": "Puducherry", "tier": "Tier 2"},
]

# Generate Noida Sectors
NOIDA_SECTORS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 18, 19, 21, 22, 27, 28, 29, 30, 34, 37, 41, 44, 45, 50, 51, 52, 53, 55, 56, 62, 63, 64, 65, 67, 71, 73, 75, 76, 77, 78, 80, 81, 93, 104, 110, 120, 121, 128, 132, 135, 137, 142, 144, 150, 168]
for sec in NOIDA_SECTORS:
    MASTER_LOCATIONS.append({
        "name": f"Noida Sector {sec}",
        "city": "Noida",
        "state": "Uttar Pradesh",
        "tier": "Tier 2"
    })

# Add Noida landmarks
MASTER_LOCATIONS.extend([
    {"name": "Noida Extension", "city": "Noida", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Knowledge Park", "city": "Greater Noida", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Pari Chowk", "city": "Greater Noida", "state": "Uttar Pradesh", "tier": "Tier 2"},
    {"name": "Cyber City", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "Golf Course Road", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "Sohna Road", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "Udyog Vihar", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "DLF Phase 1", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "DLF Phase 2", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "DLF Phase 3", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "DLF Phase 4", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
    {"name": "DLF Phase 5", "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"},
])

# Generate Gurugram Sectors
GURGAON_SECTORS = [14, 15, 18, 21, 23, 24, 27, 28, 29, 30, 31, 32, 33, 38, 43, 44, 45, 47, 48, 49, 50, 51, 52, 53, 54, 56, 57, 62, 65, 66, 67, 69, 70, 71, 79, 81, 82, 83]
for sec in GURGAON_SECTORS:
    MASTER_LOCATIONS.append({
        "name": f"Gurugram Sector {sec}",
        "city": "Gurugram",
        "state": "Haryana",
        "tier": "Tier 2"
    })

# Popular Tier 3 Cities and Towns
TIER_3_CITIES = [
    ("Aligarh", "Uttar Pradesh"), ("Mathura", "Uttar Pradesh"), ("Moradabad", "Uttar Pradesh"), ("Bareilly", "Uttar Pradesh"), ("Saharanpur", "Uttar Pradesh"), ("Jhansi", "Uttar Pradesh"), ("Muzaffarnagar", "Uttar Pradesh"), ("Firozabad", "Uttar Pradesh"), ("Rampur", "Uttar Pradesh"), ("Shahjahanpur", "Uttar Pradesh"), ("Ayodhya", "Uttar Pradesh"), ("Basti", "Uttar Pradesh"), ("Deoria", "Uttar Pradesh"), ("Azamgarh", "Uttar Pradesh"), ("Jaunpur", "Uttar Pradesh"), ("Mirzapur", "Uttar Pradesh"), ("Sitapur", "Uttar Pradesh"), ("Lakhimpur", "Uttar Pradesh"), ("Unnao", "Uttar Pradesh"), ("Hapur", "Uttar Pradesh"), ("Bulandshahr", "Uttar Pradesh"), ("Amroha", "Uttar Pradesh"), ("Bijnor", "Uttar Pradesh"), ("Etawah", "Uttar Pradesh"), ("Mainpuri", "Uttar Pradesh"), ("Sultanpur", "Uttar Pradesh"), ("Raebareli", "Uttar Pradesh"), ("Banda", "Uttar Pradesh"), ("Hardoi", "Uttar Pradesh"), ("Bahraich", "Uttar Pradesh"),
    ("Solapur", "Maharashtra"), ("Kolhapur", "Maharashtra"), ("Amravati", "Maharashtra"), ("Nanded", "Maharashtra"), ("Sangli", "Maharashtra"), ("Jalgaon", "Maharashtra"), ("Akola", "Maharashtra"), ("Latur", "Maharashtra"), ("Dhule", "Maharashtra"), ("Ahmednagar", "Maharashtra"), ("Chandrapur", "Maharashtra"), ("Parbhani", "Maharashtra"), ("Satara", "Maharashtra"), ("Yavatmal", "Maharashtra"), ("Wardha", "Maharashtra"),
    ("Davanagere", "Karnataka"), ("Ballari", "Karnataka"), ("Tumakuru", "Karnataka"), ("Shivamogga", "Karnataka"), ("Bidar", "Karnataka"), ("Raichur", "Karnataka"), ("Hosapete", "Karnataka"), ("Hassan", "Karnataka"), ("Kalaburagi", "Karnataka"), ("Udupi", "Karnataka"), ("Karwar", "Karnataka"), ("Kolar", "Karnataka"), ("Mandya", "Karnataka"), ("Chikkamagaluru", "Karnataka"),
    ("Thanjavur", "Tamil Nadu"), ("Dindigul", "Tamil Nadu"), ("Cuddalore", "Tamil Nadu"), ("Kanchipuram", "Tamil Nadu"), ("Erode", "Tamil Nadu"), ("Tirunelveli", "Tamil Nadu"), ("Vellore", "Tamil Nadu"), ("Thoothukudi", "Tamil Nadu"), ("Nagercoil", "Tamil Nadu"), ("Karur", "Tamil Nadu"), ("Kumbakonam", "Tamil Nadu"),
    ("Jamnagar", "Gujarat"), ("Junagadh", "Gujarat"), ("Gandhidham", "Gujarat"), ("Nadiad", "Gujarat"), ("Anand", "Gujarat"), ("Morbi", "Gujarat"), ("Bharuch", "Gujarat"), ("Navsari", "Gujarat"), ("Veraval", "Gujarat"), ("Porbandar", "Gujarat"), ("Godhra", "Gujarat"), ("Vapi", "Gujarat"), ("Valsad", "Gujarat"), ("Mehsana", "Gujarat"),
    ("Bhilwara", "Rajasthan"), ("Alwar", "Rajasthan"), ("Sikar", "Rajasthan"), ("Pali", "Rajasthan"), ("Tonk", "Rajasthan"), ("Kishangarh", "Rajasthan"), ("Beawar", "Rajasthan"), ("Hanumangarh", "Rajasthan"), ("Jhunjhunu", "Rajasthan"), ("Sawai Madhopur", "Rajasthan"), ("Chittorgarh", "Rajasthan"), ("Churu", "Rajasthan"),
    ("Pathankot", "Punjab"), ("Hoshiarpur", "Punjab"), ("Batala", "Punjab"), ("Abohar", "Punjab"), ("Khanna", "Punjab"), ("Phagwara", "Punjab"), ("Patiala", "Punjab"), ("Bathinda", "Punjab"), ("Rohtak", "Haryana"), ("Panipat", "Haryana"), ("Karnal", "Haryana"), ("Hisar", "Haryana"), ("Ambala", "Haryana"), ("Yamunanagar", "Haryana"), ("Sonipat", "Haryana"), ("Rewari", "Haryana"), ("Sirsa", "Haryana"), ("Bhiwani", "Haryana"), ("Bahadurgarh", "Haryana"), ("Jind", "Haryana"),
    ("Sagar", "Madhya Pradesh"), ("Satna", "Madhya Pradesh"), ("Rewa", "Madhya Pradesh"), ("Singrauli", "Madhya Pradesh"), ("Ratlam", "Madhya Pradesh"), ("Dewas", "Madhya Pradesh"), ("Katni", "Madhya Pradesh"), ("Burhanpur", "Madhya Pradesh"), ("Khandwa", "Madhya Pradesh"), ("Bhind", "Madhya Pradesh"), ("Chhindwara", "Madhya Pradesh"), ("Guna", "Madhya Pradesh"), ("Shivpuri", "Madhya Pradesh"), ("Vidisha", "Madhya Pradesh"), ("Neemuch", "Madhya Pradesh"),
    ("Hazaribagh", "Jharkhand"), ("Deoghar", "Jharkhand"), ("Giridih", "Jharkhand"), ("Ramgarh", "Jharkhand"), ("Bokaro", "Jharkhand"), ("Katihar", "Bihar"), ("Arrah", "Bihar"), ("Purnia", "Bihar"), ("Begusarai", "Bihar"), ("Sasaram", "Bihar"), ("Samastipur", "Bihar"), ("Hajipur", "Bihar"), ("Motihari", "Bihar"), ("Bettiah", "Bihar"), ("Siwan", "Bihar"), ("Kishanganj", "Bihar"),
    ("Bardhaman", "West Bengal"), ("Malda", "West Bengal"), ("Kharagpur", "West Bengal"), ("Berhampore", "West Bengal"), ("Haldia", "West Bengal"), ("Jalpaiguri", "West Bengal"), ("Krishnanagar", "West Bengal"), ("Bankura", "West Bengal"),
    ("Sambalpur", "Odisha"), ("Puri", "Odisha"), ("Balasore", "Odisha"), ("Brahmapur", "Odisha"), ("Baripada", "Odisha"), ("Bhadrak", "Odisha"), ("Jharsuguda", "Odisha"),
    ("Kakinada", "Andhra Pradesh"), ("Rajahmundry", "Andhra Pradesh"), ("Eluru", "Andhra Pradesh"), ("Anantapur", "Andhra Pradesh"), ("Vizianagaram", "Andhra Pradesh"), ("Machilipatnam", "Andhra Pradesh"), ("Tenali", "Andhra Pradesh"), ("Nandyal", "Andhra Pradesh"), ("Nizamabad", "Telangana"), ("Khammam", "Telangana"), ("Karimnagar", "Telangana"), ("Ramagundam", "Telangana"), ("Mahbubnagar", "Telangana"),
    ("Kollam", "Kerala"), ("Alappuzha", "Kerala"), ("Palakkad", "Kerala"), ("Kannur", "Kerala"), ("Kottayam", "Kerala"), ("Kasaragod", "Kerala"), ("Malappuram", "Kerala"), ("Pathanamthitta", "Kerala"),
    ("Silchar", "Assam"), ("Tezpur", "Assam"), ("Jorhat", "Assam"), ("Dibrugarh", "Assam"), ("Tinsukia", "Assam"), ("Bongaigaon", "Assam"), ("Nagaon", "Assam"), ("Solan", "Himachal Pradesh"), ("Mandi", "Himachal Pradesh"), ("Hamirpur", "Himachal Pradesh"), ("Una", "Himachal Pradesh"), ("Kullu", "Himachal Pradesh"), ("Manali", "Himachal Pradesh")
]

for city_name, state_name in TIER_3_CITIES:
    MASTER_LOCATIONS.append({
        "name": city_name,
        "city": city_name,
        "state": state_name,
        "tier": "Tier 3"
    })

# Deduplicate by name
_seen = set()
UNIQUE_MASTER_LOCATIONS = []
for item in MASTER_LOCATIONS:
    key = item['name'].lower()
    if key not in _seen:
        _seen.add(key)
        UNIQUE_MASTER_LOCATIONS.append(item)

class LocationService:
    @staticmethod
    def search_locations(query: str, limit: int = 30) -> list:
        """
        Fast case-insensitive search matching locations by name, city, or state.
        Prefix matches rank first, followed by substring matches.
        """
        q = query.strip().lower()
        if not q:
            return UNIQUE_MASTER_LOCATIONS[:limit]

        prefix_matches = []
        substring_matches = []

        for item in UNIQUE_MASTER_LOCATIONS:
            name_lower = item['name'].lower()
            city_lower = item['city'].lower()
            state_lower = item['state'].lower()

            if name_lower.startswith(q) or city_lower.startswith(q):
                prefix_matches.append(item)
            elif q in name_lower or q in city_lower or q in state_lower:
                substring_matches.append(item)

            if len(prefix_matches) >= limit * 2:
                break

        combined = prefix_matches + substring_matches
        return combined[:limit]

    @staticmethod
    def parse_location_info(location_name: str) -> dict:
        """
        Extracts city, state, tier for a given location string.
        """
        if not location_name:
            return {"name": "", "city": "", "state": "", "tier": "Tier 3"}

        clean = location_name.strip()
        clean_lower = clean.lower()

        for item in UNIQUE_MASTER_LOCATIONS:
            if item['name'].lower() == clean_lower or item['city'].lower() == clean_lower:
                return {
                    "name": clean,
                    "city": item['city'],
                    "state": item['state'],
                    "tier": item['tier']
                }

        # Substring heuristics
        if "noida" in clean_lower:
            return {"name": clean, "city": "Noida", "state": "Uttar Pradesh", "tier": "Tier 2"}
        elif "gurugram" in clean_lower or "gurgaon" in clean_lower:
            return {"name": clean, "city": "Gurugram", "state": "Haryana", "tier": "Tier 2"}
        elif "delhi" in clean_lower:
            return {"name": clean, "city": "New Delhi", "state": "Delhi", "tier": "Tier 1"}
        elif "mumbai" in clean_lower:
            return {"name": clean, "city": "Mumbai", "state": "Maharashtra", "tier": "Tier 1"}
        elif "bengaluru" in clean_lower or "bangalore" in clean_lower:
            return {"name": clean, "city": "Bengaluru", "state": "Karnataka", "tier": "Tier 1"}
        elif "hyderabad" in clean_lower:
            return {"name": clean, "city": "Hyderabad", "state": "Telangana", "tier": "Tier 1"}
        elif "chennai" in clean_lower:
            return {"name": clean, "city": "Chennai", "state": "Tamil Nadu", "tier": "Tier 1"}
        elif "pune" in clean_lower:
            return {"name": clean, "city": "Pune", "state": "Maharashtra", "tier": "Tier 1"}

        return {"name": clean, "city": clean, "state": "", "tier": "Tier 3"}
