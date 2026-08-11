from django.core.management.base import BaseCommand
from django.conf import settings
from apps.candidates.models import CandidateProfile

class Command(BaseCommand):
    help = "Verifies that every candidate resume resolves through Django's configured storage."

    def handle(self, *args, **options):
        self.stdout.write("Checking Django storage configuration...")
        storage_backend = getattr(settings, 'STORAGES', {}).get('default', {}).get('BACKEND', 'Unknown')
        self.stdout.write(f"Configured Storage Backend: {storage_backend}")

        candidates = CandidateProfile.objects.all()
        total_candidates = candidates.count()
        candidates_with_resume = candidates.exclude(resume='').exclude(resume__isnull=True)
        total_resume_refs = candidates_with_resume.count()

        valid_storage_resumes = 0
        failed_storage_resumes = 0

        self.stdout.write(f"\nEvaluating {total_resume_refs} candidate resume references...\n")

        for candidate in candidates_with_resume:
            resume_file = candidate.resume
            if not resume_file or not resume_file.name:
                continue

            try:
                exists = resume_file.storage.exists(resume_file.name)
                url = resume_file.url if exists else "N/A"
            except Exception as e:
                exists = False
                url = f"ERROR: {e}"

            if exists:
                valid_storage_resumes += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[VALID] Candidate {candidate.id} ({candidate.full_name}): "
                        f"key='{resume_file.name}' -> url='{url}'"
                    )
                )
            else:
                failed_storage_resumes += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"[MISSING/BROKEN] Candidate {candidate.id} ({candidate.full_name}): "
                        f"key='{resume_file.name}'"
                    )
                )

        self.stdout.write("\n" + "=" * 55)
        self.stdout.write(self.style.SUCCESS("        RESUME STORAGE VERIFICATION REPORT        "))
        self.stdout.write("=" * 55)
        self.stdout.write(f"  Total Candidates                 : {total_candidates}")
        self.stdout.write(f"  Candidates with Resume References: {total_resume_refs}")
        self.stdout.write(f"  Successfully Resolved via Storage: {valid_storage_resumes}")
        self.stdout.write(f"  Failed / Missing via Storage     : {failed_storage_resumes}")
        self.stdout.write("=" * 55 + "\n")
