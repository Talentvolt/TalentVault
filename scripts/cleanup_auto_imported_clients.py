import os
import sys
import django
from django.db import transaction

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

def cleanup():
    print("Starting Client Database Cleanup...")
    initial_count = Client.objects.count()
    print(f"Total Client Records in DB before cleanup: {initial_count}")

    # Query auto-imported records
    all_clients = Client.objects.all()
    to_delete_ids = []
    to_keep_ids = []

    for c in all_clients:
        jobs_count = Job.objects.filter(client=c).count()
        is_spoc_hr = c.spoc_name and c.spoc_name.endswith(' HR')
        no_contact = not c.email and not c.phone_number and not c.website
        is_auto_imported = (
            c.created_by_id is None and
            is_spoc_hr and
            no_contact and
            jobs_count == 0 and
            c.industry == 'OTHERS'
        )

        if is_auto_imported:
            to_delete_ids.append(c.id)
        else:
            to_keep_ids.append(c)

    print(f"Identified {len(to_delete_ids)} records to remove.")
    print(f"Identified {len(to_keep_ids)} records to keep.")

    print("\nLegitimate records being PRESERVED:")
    for k in to_keep_ids:
        print(f"  - ID: {k.id} | Name: '{k.company_name}' | SPOC: '{k.spoc_name}' | Email: '{k.email}' | Jobs: {Job.objects.filter(client=k).count()}")

    with transaction.atomic():
        deleted_count, details = Client.objects.filter(id__in=to_delete_ids).delete()
        print(f"\n[ATOMIC TRANSACTION] Deleted {deleted_count} database objects.")
        print("Details:", details)

    final_count = Client.objects.count()
    print(f"\nTotal Client Records in DB after cleanup: {final_count}")

if __name__ == '__main__':
    cleanup()
