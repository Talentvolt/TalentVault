import os
import sys
import json
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

def export_and_audit():
    clients = Client.objects.all().order_by('created_at', 'company_name')
    print(f"Total Client Records in DB: {clients.count()}")

    backup_data = []
    auto_imported_ids = []
    legitimate_ids = []

    for c in clients:
        jobs = Job.objects.filter(client=c)
        job_list = [{"id": str(j.id), "title": j.title, "status": j.status} for j in jobs]
        
        record = {
            "id": str(c.id),
            "company_name": c.company_name,
            "spoc_name": c.spoc_name,
            "designation": c.designation,
            "email": c.email,
            "phone_number": c.phone_number,
            "website": c.website,
            "industry": c.industry,
            "company_size": c.company_size,
            "city": c.city,
            "state": c.state,
            "country": c.country,
            "notes": c.notes,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "created_by_id": str(c.created_by_id) if c.created_by_id else None,
            "updated_by_id": str(c.updated_by_id) if c.updated_by_id else None,
            "jobs_count": len(job_list),
            "jobs": job_list
        }
        backup_data.append(record)

        # Audit criteria:
        # Auto-imported records have:
        # - spoc_name matches f"{c.company_name} HR" or ends with " HR"
        # - created_by_id is None
        # - no email, no phone_number, no website
        # - industry is 'OTHERS'
        # - 0 jobs linked
        # - created_at on 2026-08-11 or 2026-08-12 (recent logo import work)
        is_spoc_hr = c.spoc_name and c.spoc_name.endswith(' HR')
        no_contact = not c.email and not c.phone_number and not c.website
        is_auto = is_spoc_hr and no_contact and c.created_by_id is None and len(job_list) == 0 and c.industry == 'OTHERS'

        if is_auto:
            auto_imported_ids.append(record)
        else:
            legitimate_ids.append(record)

    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    backup_file = os.path.join(backup_dir, 'clients_backup_before_cleanup.json')
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, indent=2)

    print(f"\n[SUCCESS] Exported {len(backup_data)} client records to: {backup_file}")
    print(f"Identified Auto-Imported Records: {len(auto_imported_ids)}")
    print(f"Identified Legitimate Records: {len(legitimate_ids)}")

    if legitimate_ids:
        print("\nLegitimate Client Records:")
        for leg in legitimate_ids:
            print(f"  - ID: {leg['id']}, Company: '{leg['company_name']}', SPOC: '{leg['spoc_name']}', Jobs: {leg['jobs_count']}, CreatedBy: {leg['created_by_id']}")

if __name__ == '__main__':
    export_and_audit()
