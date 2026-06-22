import os
import django
from django.db import connection

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.accounts.models import User
from apps.companies.models import Company
from apps.jobs.models import Job
from apps.candidates.models import CandidateProfile
from apps.applications.models import Application
from apps.interviews.models import Interview

def main():
    print("=" * 60)
    print("Django Database Status Verification")
    print("=" * 60)
    
    # 1. Database Connection Info
    engine = connection.settings_dict.get('ENGINE')
    name = connection.settings_dict.get('NAME')
    host = connection.settings_dict.get('HOST')
    port = connection.settings_dict.get('PORT')
    
    print(f"Database Engine:  {engine}")
    print(f"Database Name:    {name}")
    print(f"Database Host:    {host}")
    print(f"Database Port:    {port}")
    print("-" * 60)
    
    # 2. Record Counts
    models_to_check = [
        User, Company, Job, CandidateProfile, Application, Interview
    ]
    
    print("Record Counts for Major Tables:")
    for model in models_to_check:
        print(f" - {model.__name__:<20}: {model.objects.count()} records")
    print("-" * 60)
    
    # 3. Test Insert/Write to PostgreSQL
    print("Testing Insert Capability in PostgreSQL...")
    try:
        test_company = Company.objects.create(
            name="Migration Test Company",
            slug="migration-test-company",
            location="Verification Host"
        )
        print(f" - Created test record successfully with ID: {test_company.id}")
        
        # Verify it exists in db
        retrieved = Company.objects.get(id=test_company.id)
        print(f" - Retrieved test record from database: '{retrieved.name}'")
        
        # Clean up
        test_company.delete()
        print(" - Deleted test record to keep database clean.")
        print("Write test: PASSED")
    except Exception as e:
        print(f"Write test: FAILED -> {e}")
        
    print("-" * 60)
    
    # 4. Check SQLite status
    sqlite_exists = os.path.exists('db.sqlite3')
    print(f"SQLite file ('db.sqlite3') exists in project root? {'YES (Error!)' if sqlite_exists else 'NO (Success!)'}")
    print("=" * 60)

if __name__ == "__main__":
    main()
