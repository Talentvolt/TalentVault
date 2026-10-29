"""
Management command to process the candidate invitation email queue.

This command sends queued invitation emails with a 3-minute delay between
consecutive emails to ensure sequential delivery during bulk resume parsing.

Usage:
    python manage.py process_invitation_email_queue [--limit N] [--dry-run] [--run-once]

Options:
    --limit N         Maximum number of emails to process in one run (default: 10)
    --dry-run         Show what would be processed without sending
    --run-once        Process once and exit (default behavior for cron)
    --daemon          Run continuously, polling every 30 seconds
"""
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from apps.candidates.models import CandidateInvitationEmailQueue
from apps.accounts.services.email_service import _send_candidate_profile_invitation_email_now


class Command(BaseCommand):
    help = 'Process queued candidate invitation emails with 3-minute sequential delays'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Maximum number of emails to process in one run (default: 10)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually sending emails'
        )
        parser.add_argument(
            '--run-once',
            action='store_true',
            help='Process once and exit (default behavior)'
        )
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Run continuously, polling every 30 seconds'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        run_once = options['run_once']
        daemon = options['daemon']

        if daemon:
            self.stdout.write(self.style.SUCCESS('Starting invitation email queue processor in daemon mode...'))
            self.stdout.write('Press Ctrl+C to stop.')
            try:
                while True:
                    processed = self.process_queue(limit, dry_run)
                    if processed == 0:
                        self.stdout.write('No pending emails. Waiting 30 seconds...')
                    time.sleep(30)
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS('\nStopped by user.'))
        else:
            processed = self.process_queue(limit, dry_run)
            if dry_run:
                self.stdout.write(self.style.SUCCESS(f'Dry run complete. Would process {processed} emails.'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Processed {processed} queued invitation emails.'))

    def process_queue(self, limit: int, dry_run: bool) -> int:
        """Process pending emails that are due for sending."""
        now = timezone.now()
        
        # Find emails ready to send (scheduled_at <= now, status PENDING)
        pending_emails = CandidateInvitationEmailQueue.objects.filter(
            status='PENDING',
            scheduled_at__lte=now
        ).select_related('candidate_profile').order_by('scheduled_at')[:limit]

        count = 0
        for queue_item in pending_emails:
            if dry_run:
                self.stdout.write(
                    f'  [DRY RUN] Would send to {queue_item.candidate_email} '
                    f'(candidate: {queue_item.candidate_profile_id}, scheduled: {queue_item.scheduled_at})'
                )
                count += 1
                continue

            try:
                with transaction.atomic():
                    # Lock the row to prevent concurrent processing
                    queue_item = CandidateInvitationEmailQueue.objects.select_for_update().get(
                        id=queue_item.id,
                        status='PENDING'
                    )
                    
                    # Double-check it's still due
                    if queue_item.scheduled_at > timezone.now():
                        continue
                    
                    # Mark as sending
                    queue_item.status = 'SENDING'
                    queue_item.attempts += 1
                    queue_item.save(update_fields=['status', 'attempts'])

                    # Send the email
                    profile = queue_item.candidate_profile
                    if not profile:
                        queue_item.status = 'FAILED'
                        queue_item.last_error = 'Candidate profile not found'
                        queue_item.save(update_fields=['status', 'last_error'])
                        self.stdout.write(
                            self.style.ERROR(f'  Failed: Candidate profile {queue_item.candidate_profile_id} not found')
                        )
                        continue

                    success, message = _send_candidate_profile_invitation_email_now(
                        profile=profile,
                        candidate_email=queue_item.candidate_email,
                        candidate_name=queue_item.candidate_name,
                        request=None  # Queue processor runs without request context
                    )

                    if success:
                        queue_item.status = 'SENT'
                        queue_item.sent_at = timezone.now()
                        queue_item.save(update_fields=['status', 'sent_at'])
                        self.stdout.write(
                            self.style.SUCCESS(f'  Sent to {queue_item.candidate_email} (candidate: {profile.id})')
                        )
                    else:
                        if queue_item.attempts >= queue_item.max_attempts:
                            queue_item.status = 'FAILED'
                            queue_item.last_error = message
                            queue_item.save(update_fields=['status', 'last_error'])
                            self.stdout.write(
                                self.style.ERROR(f'  Failed permanently: {queue_item.candidate_email} - {message}')
                            )
                        else:
                            # Retry: schedule for 5 minutes later
                            queue_item.status = 'PENDING'
                            queue_item.scheduled_at = timezone.now() + timedelta(minutes=5)
                            queue_item.last_error = message
                            queue_item.save(update_fields=['status', 'scheduled_at', 'last_error'])
                            self.stdout.write(
                                self.style.WARNING(f'  Retry {queue_item.attempts}/{queue_item.max_attempts} for {queue_item.candidate_email}: {message}')
                            )

                    count += 1

            except CandidateInvitationEmailQueue.DoesNotExist:
                # Another process got it
                continue
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f'  Error processing queue item {queue_item.id}: {exc}')
                )
                try:
                    queue_item.status = 'FAILED'
                    queue_item.last_error = str(exc)
                    queue_item.save(update_fields=['status', 'last_error'])
                except Exception:
                    pass

        return count