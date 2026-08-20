import datetime
from collections import defaultdict
from typing import Dict, Any, List, Optional
from django.utils import timezone
from apps.candidates.models import BulkResumeJob, CandidateProfile


class ParsingActivityService:
    """
    High-performance service that reads real resume parsing and candidate import 
    activity logs without triggering parsing or re-evaluating candidate files.
    """

    @classmethod
    def get_recent_parsing_activity(cls, user=None, limit: int = 35) -> Dict[str, Any]:
        today = timezone.localdate()
        yesterday = today - datetime.timedelta(days=1)
        day_before = today - datetime.timedelta(days=2)

        events: List[Dict[str, Any]] = []

        # 1. Fetch Bulk Resume Jobs (Batch / ZIP / Excel uploads)
        bulk_qs = BulkResumeJob.objects.all()
        bulk_jobs = bulk_qs.only(
            'id', 'job_number', 'status', 'zip_filename', 'excel_filename',
            'total_files', 'processed_files', 'successful_count', 'updated_count',
            'skipped_count', 'failed_count', 'created_at'
        ).order_by('-created_at')[:limit]

        for job in bulk_jobs:
            loc_dt = timezone.localtime(job.created_at)
            total = job.total_files or (job.successful_count + job.skipped_count + job.failed_count)

            # Determine actual source
            if job.excel_filename and not job.zip_filename:
                source = "Excel Import"
            elif job.zip_filename:
                source = "ZIP Upload" if ".zip" in job.zip_filename.lower() else "Bulk Upload"
            else:
                source = "Bulk Upload"

            events.append({
                "id": f"bulk_{job.id}",
                "type": "bulk",
                "timestamp": job.created_at,
                "local_datetime": loc_dt,
                "date": loc_dt.date(),
                "time_str": loc_dt.strftime("%I:%M %p"),
                "source": source,
                "total_parsed": max(total, (job.successful_count + job.skipped_count + job.failed_count)),
                "successful_count": job.successful_count,
                "skipped_count": job.skipped_count,
                "failed_count": job.failed_count,
                "duplicate_count": job.updated_count,
                "detail_label": job.zip_filename or job.excel_filename or f"Job #{job.job_number}",
                "job_number": job.job_number,
                "status": job.status
            })

        # 2. Fetch Standalone parsed Candidate Profiles (parsed directly via Resume Parser)
        standalone_candidates = CandidateProfile.objects.filter(
            bulk_parsed_items__isnull=True
        ).exclude(
            original_filename__isnull=True
        ).exclude(
            original_filename=''
        ).only(
            'id', 'full_name', 'original_filename', 'parser_status', 'created_at'
        ).order_by('-created_at')[:limit]

        for cand in standalone_candidates:
            loc_dt = timezone.localtime(cand.created_at)
            source = "Resume Parser" if (cand.original_filename or cand.parser_status == 'SUCCESS') else "Manual Parsing"
            success = 1 if cand.parser_status in ['SUCCESS', None] else 0
            failed = 1 if cand.parser_status == 'FAILED' else 0

            events.append({
                "id": f"cand_{cand.id}",
                "type": "single",
                "timestamp": cand.created_at,
                "local_datetime": loc_dt,
                "date": loc_dt.date(),
                "time_str": loc_dt.strftime("%I:%M %p"),
                "source": source,
                "total_parsed": 1,
                "successful_count": success,
                "skipped_count": 0,
                "failed_count": failed,
                "duplicate_count": 0,
                "detail_label": cand.original_filename or cand.full_name or "Resume File",
                "candidate_name": cand.full_name,
                "status": "COMPLETED"
            })

        # Sort all events newest first
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        events = events[:limit]

        # Group by Date
        grouped_by_date = defaultdict(list)
        today_summary = {
            "total": 0,
            "successful": 0,
            "skipped": 0,
            "failed": 0,
            "has_activity": False
        }

        for ev in events:
            d = ev["date"]
            grouped_by_date[d].append(ev)
            if d == today:
                today_summary["total"] += ev["total_parsed"]
                today_summary["successful"] += ev["successful_count"]
                today_summary["skipped"] += ev["skipped_count"]
                today_summary["failed"] += ev["failed_count"]
                today_summary["has_activity"] = True

        # Construct ordered date groups: Today, Yesterday, Day Before Yesterday, Older dates
        date_groups = []
        sorted_dates = sorted(grouped_by_date.keys(), reverse=True)

        for d in sorted_dates:
            if d == today:
                header_label = "Today"
                sub_label = d.strftime("%d %b %Y")
                badge_type = "today"
            elif d == yesterday:
                header_label = "Yesterday"
                sub_label = d.strftime("%d %b %Y")
                badge_type = "yesterday"
            elif d == day_before:
                header_label = "Day Before Yesterday"
                sub_label = d.strftime("%d %b %Y")
                badge_type = "day_before"
            else:
                header_label = d.strftime("%d %b %Y")
                sub_label = ""
                badge_type = "older"

            date_groups.append({
                "date": d,
                "header_label": header_label,
                "sub_label": sub_label,
                "badge_type": badge_type,
                "activities": grouped_by_date[d]
            })

        return {
            "date_groups": date_groups,
            "today_summary": today_summary,
            "total_activities_count": len(events)
        }
