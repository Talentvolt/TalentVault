import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass
django.setup()

from apps.clients.models import Client
from apps.jobs.models import Job

def analyze():
    clients = Client.objects.all().order_by('created_at', 'company_name')
    print(f"Total Client Records in DB: {clients.count()}\n")

    trusted_names = {
        "ShipGlobal", "Lumax", "CARS24", "CARS24 Australia", "ExpertPanel", "Murugappa",
        "Vame", "Scaler Academy", "OYO", "Gumlet", "Meshr", "Alyfy Freight System",
        "Ambak", "ACT Fibernet", "Entri", "Zingbus", "magicpin", "NoBroker Vanguard",
        "Spinny", "Aye Finance", "Hero Group", "Suraasa", "redBus", "apna", "QuickShift",
        "Rane", "Truck Loans", "Wired", "CloudFuze", "WheelsEye", "DriveX", "IndusInd Bank",
        "Justdial", "BuyY Commodity", "Netcore", "FleetX.io", "Motilal Oswal",
        "Unicorn DenMart", "CUMI", "SmartWinnr", "TVS", "Bonanza", "Vutto", "Insurity",
        "TECHXR", "91TRUCKS", "EchoVME", "ATI Motors", "MG / Morris Garages", "Lenskart",
        # Case variations or names present in logo list
        "Alyf Freight System", "Hero", "NoBroker"
    }

    imported_records = []
    legitimate_records = []
    ambiguous_records = []

    for c in clients:
        job_count = Job.objects.filter(client=c).count()
        
        # Criteria for auto-imported landing page client record:
        # 1. spoc_name is exact pattern f'{company_name} HR' or ends with ' HR'
        # 2. created_by is None
        # 3. email is None/empty
        # 4. phone_number is None/empty
        # 5. website is None/empty
        # 6. industry is 'OTHERS'
        # 7. no jobs attached
        is_spoc_hr_pattern = c.spoc_name == f"{c.company_name} HR" or c.spoc_name == f"{c.company_name}  HR"
        no_contact_info = not c.email and not c.phone_number and not c.website
        
        if (is_spoc_hr_pattern or c.company_name in trusted_names) and no_contact_info and job_count == 0 and c.created_by is None and c.industry == 'OTHERS':
            imported_records.append((c, job_count))
        elif job_count > 0 or c.email or c.phone_number or c.created_by is not None or (c.spoc_name and not c.spoc_name.endswith(' HR')):
            legitimate_records.append((c, job_count))
        else:
            ambiguous_records.append((c, job_count))

    print(f"=== IDENTIFIED AUTO-IMPORTED RECORDS: {len(imported_records)} ===")
    for c, jc in imported_records:
        print(f"ID: {c.id} | Name: '{c.company_name}' | SPOC: '{c.spoc_name}' | Created: {c.created_at}")

    print(f"\n=== LEGITIMATE RECORDS TO PRESERVE: {len(legitimate_records)} ===")
    for c, jc in legitimate_records:
        print(f"ID: {c.id} | Name: '{c.company_name}' | SPOC: '{c.spoc_name}' | Jobs: {jc} | Email: {c.email} | CreatedBy: {c.created_by} | Created: {c.created_at}")

    print(f"\n=== AMBIGUOUS RECORDS: {len(ambiguous_records)} ===")
    for c, jc in ambiguous_records:
        print(f"ID: {c.id} | Name: '{c.company_name}' | SPOC: '{c.spoc_name}' | Jobs: {jc} | Email: {c.email} | CreatedBy: {c.created_by} | Created: {c.created_at}")

if __name__ == '__main__':
    analyze()
