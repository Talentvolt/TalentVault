import base64
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views import View
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.conf import settings
from apps.notifications.models import EmailLog, EmailTemplate, RecruiterEmailAccount
from apps.notifications.services import seed_default_email_templates, render_email_content

# 1x1 transparent GIF bytes
TRANSPARENT_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

class TrackOpenView(View):
    """
    Tracks email opens via a 1x1 transparent tracking pixel.
    """
    def get(self, request, uuid, *args, **kwargs):
        log = EmailLog.objects.filter(tracking_uuid=uuid).first()
        if log:
            log.open_count += 1
            log.last_opened_at = timezone.now()
            if log.status == 'SENT':
                log.status = 'OPENED'
            log.save(update_fields=['open_count', 'last_opened_at', 'status'])
        return HttpResponse(TRANSPARENT_GIF, content_type="image/gif")


class TrackClickView(View):
    """
    Tracks email link clicks and redirects to target URL.
    """
    def get(self, request, uuid, *args, **kwargs):
        target_url = request.GET.get('url', 'https://talentvault.in')
        log = EmailLog.objects.filter(tracking_uuid=uuid).first()
        if log:
            log.click_count += 1
            log.last_clicked_at = timezone.now()
            log.status = 'CLICKED'
            log.save(update_fields=['click_count', 'last_clicked_at', 'status'])
        return HttpResponseRedirect(target_url)


class RecruiterEmailAccountAPIView(View):
    """
    API view for recruiters to connect Gmail/Outlook/SMTP email accounts, set default, verify, and delete.
    """
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role == 'CANDIDATE':
            return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)
            
        action = request.POST.get('action', 'connect')
        
        if action == 'connect_smtp':
            email_address = request.POST.get('email_address')
            host = request.POST.get('smtp_host')
            port = request.POST.get('smtp_port', 587)
            username = request.POST.get('smtp_username')
            password = request.POST.get('smtp_password')
            use_tls = str(request.POST.get('use_tls', 'true')).lower() in ('true', '1', 'yes')
            
            if not email_address or not host:
                return JsonResponse({"success": False, "message": "Email address and SMTP host are required."}, status=400)
                
            is_default = not RecruiterEmailAccount.objects.filter(recruiter=request.user).exists()
            
            account = RecruiterEmailAccount.objects.create(
                recruiter=request.user,
                account_type='SMTP',
                provider='SMTP',
                email_address=email_address,
                smtp_host=host,
                smtp_port=int(port) if port else 587,
                smtp_username=username or email_address,
                smtp_password=password,
                use_tls=use_tls,
                is_verified=True,
                is_default=is_default
            )
            return JsonResponse({"success": True, "message": f"SMTP account {email_address} connected and verified successfully."})
            
        elif action == 'connect_oauth':
            provider = request.POST.get('provider', 'GMAIL')
            email_address = request.POST.get('email_address') or request.user.email
            
            if not email_address:
                return JsonResponse({"success": False, "message": "Email address is required."}, status=400)
                
            # Verify recruiter email ownership
            if email_address.lower() != request.user.email.lower() and not request.user.is_verified:
                return JsonResponse({"success": False, "message": "Email address ownership verification failed."}, status=400)
                
            access_token = request.POST.get('oauth_access_token')
            refresh_token = request.POST.get('oauth_refresh_token')
            expires_at = request.POST.get('token_expires_at')
            
            existing_account = RecruiterEmailAccount.objects.filter(recruiter=request.user, email_address=email_address).first()
            final_refresh_token = refresh_token if refresh_token else (existing_account.oauth_refresh_token if existing_account else None)
            final_access_token = access_token if access_token else (existing_account.oauth_access_token if existing_account else None)

            # Fallback to SocialToken if available
            if not final_access_token:
                try:
                    from allauth.socialaccount.models import SocialToken
                    social_token = SocialToken.objects.filter(account__user=request.user, account__provider='google').first()
                    if social_token:
                        final_access_token = social_token.token
                        final_refresh_token = social_token.token_secret or getattr(social_token, 'token_secret', None)
                        if social_token.expires_at:
                            expires_at = social_token.expires_at
                except Exception:
                    pass
            
            is_default = not RecruiterEmailAccount.objects.filter(recruiter=request.user).exists()
            if existing_account and existing_account.is_default:
                is_default = True
                
            account, created = RecruiterEmailAccount.objects.update_or_create(
                recruiter=request.user,
                email_address=email_address,
                defaults={
                    'account_type': 'OAUTH',
                    'provider': provider,
                    'oauth_access_token': final_access_token,
                    'oauth_refresh_token': final_refresh_token,
                    'token_expires_at': expires_at,
                    'is_verified': True,
                    'is_default': is_default
                }
            )
            return JsonResponse({"success": True, "message": f"Successfully connected {provider} mailbox: {email_address}"})
            
        elif action == 'verify_alias':
            account_id = request.POST.get('account_id')
            account = get_object_or_404(RecruiterEmailAccount, id=account_id, recruiter=request.user)
            alias_email = getattr(settings, 'RECRUITER_CLIENT_ALIAS_EMAIL', 'profiles@2020technologies.in')
            is_valid, err_msg = account.verify_sendas_alias(alias_email)
            if is_valid:
                return JsonResponse({"success": True, "message": f"Alias '{alias_email}' verified successfully."})
            else:
                return JsonResponse({"success": False, "message": err_msg}, status=400)
            
        elif action == 'set_default':
            account_id = request.POST.get('account_id')
            account = get_object_or_404(RecruiterEmailAccount, id=account_id, recruiter=request.user)
            RecruiterEmailAccount.objects.filter(recruiter=request.user).update(is_default=False)
            account.is_default = True
            account.save(update_fields=['is_default'])
            return JsonResponse({"success": True, "message": "Default email account updated."})
            
        elif action == 'delete':
            account_id = request.POST.get('account_id')
            account = get_object_or_404(RecruiterEmailAccount, id=account_id, recruiter=request.user)
            was_default = account.is_default
            account.delete()
            if was_default:
                next_acc = RecruiterEmailAccount.objects.filter(recruiter=request.user).first()
                if next_acc:
                    next_acc.is_default = True
                    next_acc.save(update_fields=['is_default'])
            return JsonResponse({"success": True, "message": "Email account disconnected successfully."})
            
        return JsonResponse({"success": False, "message": "Invalid action."}, status=400)


class EmailTemplateAPIView(View):
    """
    API endpoint for fetching, creating, editing, duplicating, and deleting email templates.
    """
    def get(self, request, *args, **kwargs):
        seed_default_email_templates()
        templates = EmailTemplate.objects.all()
        category = request.GET.get('category')
        if category:
            templates = templates.filter(category=category.upper())
        
        data = []
        for t in templates:
            data.append({
                "id": str(t.id),
                "name": t.name,
                "category": t.category,
                "subject": t.subject,
                "body": t.body,
                "is_system": t.is_system
            })
        return JsonResponse({"success": True, "templates": data})

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)
        
        action = request.POST.get('action', 'create')
        
        if action == 'create' or action == 'edit':
            template_id = request.POST.get('template_id')
            name = request.POST.get('name')
            category = request.POST.get('category', 'CLIENT')
            subject = request.POST.get('subject')
            body = request.POST.get('body')
            
            if not name or not subject or not body:
                return JsonResponse({"success": False, "message": "Name, subject, and body are required."}, status=400)
                
            if template_id:
                tpl = get_object_or_404(EmailTemplate, id=template_id)
                tpl.name = name
                tpl.category = category
                tpl.subject = subject
                tpl.body = body
                tpl.save()
            else:
                EmailTemplate.objects.create(
                    name=name,
                    category=category,
                    subject=subject,
                    body=body,
                    is_system=False,
                    created_by=request.user
                )
            return JsonResponse({"success": True, "message": "Template saved successfully."})
            
        elif action == 'duplicate':
            template_id = request.POST.get('template_id')
            tpl = get_object_or_404(EmailTemplate, id=template_id)
            new_name = f"{tpl.name} (Copy)"
            counter = 1
            while EmailTemplate.objects.filter(name=new_name).exists():
                counter += 1
                new_name = f"{tpl.name} (Copy {counter})"
                
            EmailTemplate.objects.create(
                name=new_name,
                category=tpl.category,
                subject=tpl.subject,
                body=tpl.body,
                is_system=False,
                created_by=request.user
            )
            return JsonResponse({"success": True, "message": "Template duplicated successfully."})
            
        elif action == 'delete':
            template_id = request.POST.get('template_id')
            tpl = get_object_or_404(EmailTemplate, id=template_id)
            if tpl.is_system:
                return JsonResponse({"success": False, "message": "System templates cannot be deleted."}, status=400)
            tpl.delete()
            return JsonResponse({"success": True, "message": "Template deleted successfully."})
            
        return JsonResponse({"success": False, "message": "Invalid action."}, status=400)
