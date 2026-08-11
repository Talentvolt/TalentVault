import hashlib
import os
import json
from concurrent.futures import ThreadPoolExecutor
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.candidates.models import CandidateProfile
import boto3

class Command(BaseCommand):
    help = "Automatically repairs candidate resume paths using existing S3 objects and outputs a verification report."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform repair analysis without saving changes to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode. No changes will be saved to DB."))

        self.stdout.write("Fetching S3 bucket inventory...")
        
        # Connect to S3 using configured credentials
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        if not bucket_name:
            self.stdout.write(self.style.ERROR("AWS_STORAGE_BUCKET_NAME is not configured."))
            return

        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

        # 1. Fetch all object keys in S3
        s3_keys = []
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name):
            if 'Contents' in page:
                for obj in page['Contents']:
                    s3_keys.append(obj['Key'])

        s3_keys_set = set(s3_keys)
        self.stdout.write(self.style.SUCCESS(f"Found {len(s3_keys)} total objects in S3 bucket '{bucket_name}'."))

        # Build basename map
        s3_basename_map = {}
        for k in s3_keys:
            bn = os.path.basename(k)
            if bn:
                s3_basename_map.setdefault(bn, []).append(k)

        # 2. Hash resume objects in S3 for SHA256 matching
        self.stdout.write("Indexing S3 objects by SHA256 hash...")
        s3_resume_keys = [k for k in s3_keys if k.startswith('resumes/') and not k.endswith('/')]
        
        sha_to_s3_keys = {}
        
        # Check if local precomputed hashes file exists for instant loading
        cache_file = os.path.join(settings.BASE_DIR, 'scratch', 'all_s3_hashes.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    sha_to_s3_keys = cache_data.get('sha_to_keys', {})
                self.stdout.write(self.style.SUCCESS(f"Loaded {len(sha_to_s3_keys)} precomputed SHA256 hashes from cache."))
            except Exception:
                pass

        if not sha_to_s3_keys:
            def hash_s3_object(key):
                try:
                    obj = s3.get_object(Bucket=bucket_name, Key=key)
                    content = obj['Body'].read()
                    sha = hashlib.sha256(content).hexdigest().lower()
                    return key, sha
                except Exception:
                    return key, None

            with ThreadPoolExecutor(max_workers=30) as executor:
                results = executor.map(hash_s3_object, s3_resume_keys)
                for key, sha in results:
                    if sha:
                        sha_to_s3_keys.setdefault(sha, []).append(key)

        def filter_preferred_s3_keys(keys_list):
            main_keys = [k for k in keys_list if k.startswith('resumes/') and not k.startswith('resumes/original/') and not k.startswith('resumes/generated/')]
            if main_keys:
                return main_keys
            return list(keys_list)

        # 3. Analyze and Repair Candidate Resume Paths
        self.stdout.write("Analyzing and repairing candidate resume paths in database...")
        
        candidates = CandidateProfile.objects.all()
        total_candidates = candidates.count()

        candidates_with_references = 0
        valid_s3_resumes = 0
        repaired_references = 0
        ambiguous_references = 0
        broken_references = 0
        missing_resumes = 0

        # Track assignment of target keys to enforce Rule 10 (no double-assignment if ambiguous across candidates)
        assigned_target_keys = {}

        for candidate in candidates:
            current_resume = candidate.resume.name if candidate.resume else None
            sha256 = (candidate.sha256 or '').lower()
            sec_fn = candidate.secure_filename
            orig_fn = candidate.original_filename
            gen_file = candidate.generated_resume.name if candidate.generated_resume else None

            # Priority check: check if candidate has any resume reference at all
            if not current_resume and not orig_fn and not sec_fn and not gen_file and not candidate.original_file:
                missing_resumes += 1
                continue

            candidates_with_references += 1

            # Priority 1: Exact database resume.name / S3 key
            if current_resume and current_resume in s3_keys_set:
                valid_s3_resumes += 1
                continue

            # Case 2: Broken reference, evaluate priority matching rules 2..8
            matches = []

            # Priority 2: Remove leading "media/" if present
            if not matches and current_resume and current_resume.startswith('media/'):
                stripped = current_resume[6:]
                if stripped in s3_keys_set:
                    matches.append(stripped)

            # Priority 3: Normalize to "resumes/<filename>" when appropriate
            if not matches and current_resume:
                bn = os.path.basename(current_resume)
                norm = f"resumes/{bn}"
                if norm in s3_keys_set:
                    matches.append(norm)

            # Priority 4: Match by original_filename
            if not matches and orig_fn:
                if orig_fn in s3_keys_set:
                    matches.append(orig_fn)
                elif f"resumes/{orig_fn}" in s3_keys_set:
                    matches.append(f"resumes/{orig_fn}")
                elif orig_fn in s3_basename_map:
                    matches.extend(s3_basename_map[orig_fn])

            # Priority 5: Match by secure_filename
            if not matches and sec_fn:
                if sec_fn in s3_keys_set:
                    matches.append(sec_fn)
                elif f"resumes/{sec_fn}" in s3_keys_set:
                    matches.append(f"resumes/{sec_fn}")
                elif sec_fn in s3_basename_map:
                    matches.extend(s3_basename_map[sec_fn])

            # Priority 6: Match by generated_resume
            if not matches and gen_file:
                if gen_file in s3_keys_set:
                    matches.append(gen_file)
                elif os.path.basename(gen_file) in s3_basename_map:
                    matches.extend(s3_basename_map[os.path.basename(gen_file)])

            # Priority 7: Match by filename basename
            if not matches and current_resume:
                bn = os.path.basename(current_resume)
                if bn in s3_basename_map:
                    matches.extend(s3_basename_map[bn])

            # Priority 8: Compare SHA256 / content hash
            if not matches and sha256 and sha256 in sha_to_s3_keys:
                matches.extend(sha_to_s3_keys[sha256])

            # Deduplicate and filter preferred keys
            unique_matches = list(dict.fromkeys(matches))
            preferred_matches = filter_preferred_s3_keys(unique_matches)

            # Priority 9: Never guess between multiple possible S3 files
            if len(preferred_matches) == 1:
                target_key = preferred_matches[0]
                # Priority 10: Check for multi-candidate ambiguity
                if target_key in assigned_target_keys:
                    ambiguous_references += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Ambiguous reference for Candidate ID {candidate.id} ({candidate.full_name}): "
                            f"Target S3 key '{target_key}' already matched Candidate ID {assigned_target_keys[target_key]}."
                        )
                    )
                else:
                    assigned_target_keys[target_key] = candidate.id
                    if not dry_run:
                        candidate.resume.name = target_key
                        candidate.save(update_fields=['resume'])
                    repaired_references += 1
                    valid_s3_resumes += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Fixed Candidate ID {candidate.id} ({candidate.full_name}): "
                            f"'{current_resume}' -> '{target_key}'"
                        )
                    )
            elif len(preferred_matches) > 1:
                ambiguous_references += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Ambiguous reference for Candidate ID {candidate.id} ({candidate.full_name}): "
                        f"Multiple S3 matches found: {preferred_matches}"
                    )
                )
            else:
                broken_references += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Broken S3 reference for Candidate ID {candidate.id} ({candidate.full_name}): "
                        f"'{current_resume}' not found in S3."
                    )
                )

        # Output Verification Report
        self.stdout.write("\n" + "=" * 55)
        self.stdout.write(self.style.SUCCESS("          RESUME REPAIR VERIFICATION REPORT          "))
        self.stdout.write("=" * 55)
        self.stdout.write(f"  Total Candidates                 : {total_candidates}")
        self.stdout.write(f"  Candidates with Resume References: {candidates_with_references}")
        self.stdout.write(f"  Valid S3 Resumes                 : {valid_s3_resumes}")
        self.stdout.write(f"  Missing Resumes                  : {missing_resumes}")
        self.stdout.write(f"  Broken S3 References             : {broken_references}")
        self.stdout.write(f"  Repaired References              : {repaired_references}")
        self.stdout.write(f"  Ambiguous References             : {ambiguous_references}")
        self.stdout.write("=" * 55 + "\n")

