from apps.notifications.models import Notification

def unread_notifications(request):
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        count = Notification.objects.filter(recipient=user, is_read=False).count()
        return {'unread_notifications_count': count}
    return {'unread_notifications_count': 0}
