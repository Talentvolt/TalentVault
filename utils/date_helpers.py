"""
Date & Time helper functions for candidate activity and dashboard statistics.
"""
import zoneinfo
from django.utils import timezone as django_timezone

KOLKATA_TZ = zoneinfo.ZoneInfo('Asia/Kolkata')


def format_relative_time(dt):
    """
    Formats a datetime object into a human-readable relative time string in Asia/Kolkata timezone:
    'Just now', '5 minutes ago', '2 hours ago', 'Yesterday', '2 days ago', '1 week ago', etc.
    """
    if not dt:
        return "Never logged in"
    
    # Convert dt to Asia/Kolkata timezone aware datetime
    local_dt = django_timezone.localtime(dt, KOLKATA_TZ)
    local_now = django_timezone.localtime(django_timezone.now(), KOLKATA_TZ)

    if local_dt > local_now:
        return "Just now"
        
    diff = local_now - local_dt
    seconds = int(diff.total_seconds())
    
    if seconds < 60:
        return "Just now"
    
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        
    hours = minutes // 60
    if hours < 24:
        if local_dt.date() == (local_now.date() - django_timezone.timedelta(days=1)):
            return "Yesterday"
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
        
    days = (local_now.date() - local_dt.date()).days
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    
    weeks = days // 7
    if weeks < 4:
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months > 1 else ''} ago"
        
    years = max(1, days // 365)
    return f"{years} year{'s' if years > 1 else ''} ago"


def format_registration_date(dt):
    """
    Formats candidate registration timestamp in Asia/Kolkata timezone:
    - Today: 'Today 10:42 AM'
    - Yesterday: 'Yesterday 4:20 PM'
    - Same year: 'Jul 26'
    - Other year: 'Jul 26, 2025'
    """
    if not dt:
        return ""
    local_dt = django_timezone.localtime(dt, KOLKATA_TZ)
    local_now = django_timezone.localtime(django_timezone.now(), KOLKATA_TZ)
    today = local_now.date()
    yesterday = today - django_timezone.timedelta(days=1)
    
    if local_dt.date() == today:
        time_str = local_dt.strftime('%I:%M %p').lstrip('0')
        return f"Today {time_str}"
    elif local_dt.date() == yesterday:
        time_str = local_dt.strftime('%I:%M %p').lstrip('0')
        return f"Yesterday {time_str}"
    elif local_dt.year == today.year:
        return local_dt.strftime("%b %d")
    else:
        return local_dt.strftime("%b %d, %Y")
