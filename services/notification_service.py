from apps.notifications.models import Notification
from django.contrib.auth import get_user_model
from typing import Optional

User = get_user_model()

class NotificationService:
    """
    Service to send in-app notifications.
    """

    @staticmethod
    def send_notification(
        recipient_id: str,
        title: str,
        message: str,
        notification_type: str,
        link: Optional[str] = None
    ) -> Notification:
        
        recipient = User.objects.get(id=recipient_id)
        
        notification = Notification.objects.create(
            recipient=recipient,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link
        )
        
        # Integration point for Celery to send Email/SMS in background
        # send_email_task.delay(recipient.email, title, message)
        
        return notification

    @staticmethod
    def mark_as_read(notification_id: str) -> bool:
        notification = Notification.objects.get(id=notification_id)
        notification.is_read = True
        notification.save()
        return True
