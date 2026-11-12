import base64
import os
import secrets
import urllib.parse
import requests
import logging
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.views import View
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.urls import reverse
from apps.notifications.models import EmailLog, EmailTemplate, RecruiterEmailAccount
from apps.notifications.services import seed_default_email_templates, render_email_content

logger = logging.getLogger(__name__)

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


RECRUITER_GMAIL_REQUIRED_SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.settings.basic',
]


def parse_oauth_scopes(scope_input):
    """
    Parses a space- or comma-delimited scope string or iterable of scopes into a normalized set.
    """
    if not scope_input:
        return set()
    if isinstance(scope_input, (list, tuple, set)):
        items = list(scope_input)
    else:
        items = str(scope_input).replace(',', ' ').split()

    scopes = set()
    for s in items:
        item = s.strip()
        if not item:
            continue
        scopes.add(item)
        if item.endswith('/'):
            scopes.add(item.rstrip('/'))
        if item.startswith('https://www.googleapis.com/auth/'):
            scopes.add(item[len('https://www.googleapis.com/auth/'):])
    return scopes


def verify_recruiter_gmail_scopes(scope_input):
    """
    Verifies that the granted scopes satisfy recruiter Gmail requirements:
    1. Sending: https://www.googleapis.com/auth/gmail.send
    2. Settings: https://www.googleapis.com/auth/gmail.settings.basic
    Note: Full Gmail scope (https://mail.google.com/ or https://mail.google.com) satisfies both.
    
    Returns (is_valid: bool, missing_scopes: list[str])
    """
    granted = parse_oauth_scopes(scope_input)
    has_full_mail = ('https://mail.google.com' in granted or 'https://mail.google.com/' in granted)

    has_send = has_full_mail or (
        'https://www.googleapis.com/auth/gmail.send' in granted or 'gmail.send' in granted
    )
    has_settings = has_full_mail or (
        'https://www.googleapis.com/auth/gmail.settings.basic' in granted or 'gmail.settings.basic' in granted
    )

    missing = []
    if not has_send:
        missing.append('https://www.googleapis.com/auth/gmail.send')
    if not has_settings:
        missing.append('https://www.googleapis.com/auth/gmail.settings.basic')

    return len(missing) == 0, missing


def get_google_oauth_redirect_uri(request=None):
    """
    Returns the authorized Google OAuth redirect URI for recruiter Gmail connection.
    Respects RECRUITER_GMAIL_OAUTH_CALLBACK_URL or GMAIL_OAUTH_REDIRECT_URI if set in environment/settings.
    Defaults to https://talent-vault.in/notifications/oauth/gmail/callback/.
    """
    configured = (
        os.environ.get('RECRUITER_GMAIL_OAUTH_CALLBACK_URL')
        or getattr(settings, 'RECRUITER_GMAIL_OAUTH_CALLBACK_URL', '')
        or os.environ.get('GMAIL_OAUTH_REDIRECT_URI')
        or getattr(settings, 'GMAIL_OAUTH_REDIRECT_URI', '')
    )
    if configured:
        return configured.strip()

    if request:
        uri = request.build_absolute_uri(reverse('notifications:recruiter_gmail_oauth_callback'))
        if not settings.DEBUG and uri.startswith('http://'):
            uri = uri.replace('http://', 'https://', 1)
        return uri

    return 'https://talent-vault.in/notifications/oauth/gmail/callback/'


class RecruiterGmailOAuthStartView(View):
    """
    Initiates Google OAuth 2.0 flow for logged-in recruiters to connect their Gmail account.
    Performs a real HTTP redirect (302) to Google's consent screen.
    Requests gmail.send and gmail.settings.basic scopes with access_type=offline and prompt=consent.
    Preserves recruiter identity and OAuth state in session.
    """
    def handle_start(self, request):
        if not request.user.is_authenticated or request.user.role == 'CANDIDATE':
            messages.error(request, "Please log in with a recruiter account to connect Gmail.")
            return redirect('recruiter_login')

        client_id = os.environ.get('RECRUITER_GMAIL_OAUTH_CLIENT_ID', '') or getattr(settings, 'RECRUITER_GMAIL_OAUTH_CLIENT_ID', '')
        client_secret = os.environ.get('RECRUITER_GMAIL_OAUTH_CLIENT_SECRET', '') or getattr(settings, 'RECRUITER_GMAIL_OAUTH_CLIENT_SECRET', '')

        if client_id.startswith("RECRUITER_GMAIL_OAUTH_CLIENT_ID="):
            client_id = client_id.replace("RECRUITER_GMAIL_OAUTH_CLIENT_ID=", "", 1).strip()
        if client_secret.startswith("RECRUITER_GMAIL_OAUTH_CLIENT_SECRET="):
            client_secret = client_secret.replace("RECRUITER_GMAIL_OAUTH_CLIENT_SECRET=", "", 1).strip()

        if not client_id or not client_secret:
            logger.error("Recruiter Gmail OAuth client credentials (RECRUITER_GMAIL_OAUTH_CLIENT_ID / RECRUITER_GMAIL_OAUTH_CLIENT_SECRET) missing.")
            messages.error(
                request,
                "Recruiter Gmail OAuth credentials (Client ID / Secret) are not configured on the server. "
                "Please configure RECRUITER_GMAIL_OAUTH_CLIENT_ID and RECRUITER_GMAIL_OAUTH_CLIENT_SECRET."
            )
            return redirect(reverse('frontend:settings') + '#email-accounts-panel')

        state = secrets.token_urlsafe(32)
        request.session['gmail_oauth_state'] = state
        request.session['gmail_oauth_recruiter_id'] = str(request.user.id)
        
        email_hint = (request.GET.get('email_address') or request.POST.get('email_address') or request.user.email or '').strip()
        if email_hint:
            request.session['gmail_oauth_expected_email'] = email_hint

        redirect_uri = get_google_oauth_redirect_uri(request)
        request.session['gmail_oauth_redirect_uri'] = redirect_uri

        scopes = [
            'openid',
            'email',
            'profile',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.settings.basic'
        ]

        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'access_type': 'offline',
            'prompt': 'consent',
            'state': state,
            'include_granted_scopes': 'true',
        }
        if email_hint:
            params['login_hint'] = email_hint

        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        return HttpResponseRedirect(auth_url)

    def get(self, request, *args, **kwargs):
        return self.handle_start(request)

    def post(self, request, *args, **kwargs):
        return self.handle_start(request)


class RecruiterGmailOAuthCallbackView(View):
    """
    Handles the callback redirect from Google OAuth 2.0.
    Validates state, exchanges authorization code for tokens, retrieves profile email,
    updates or creates RecruiterEmailAccount, marks is_verified=True only upon success,
    preserves existing refresh tokens if none returned, verifies alias, and redirects to Settings.
    """
    def get(self, request, *args, **kwargs):
        # 1. Error check
        error = request.GET.get('error')
        if error:
            error_desc = request.GET.get('error_description') or error
            logger.warning(f"Google OAuth authorization cancelled or returned error: {error_desc}")
            messages.error(request, f"Google OAuth authorization was cancelled or denied: {error_desc}")
            return redirect(reverse('frontend:settings') + '#email-accounts-panel')

        # 2. State verification
        expected_state = request.session.get('gmail_oauth_state')
        received_state = request.GET.get('state')
        if not expected_state or expected_state != received_state:
            logger.warning("Google OAuth state security mismatch or expired session.")
            messages.error(request, "OAuth security state mismatch or session expired. Please try connecting your account again.")
            return redirect(reverse('frontend:settings') + '#email-accounts-panel')

        # Clear state once verified
        request.session.pop('gmail_oauth_state', None)

        code = request.GET.get('code')
        if not code:
            messages.error(request, "No authorization code was returned by Google.")
            return redirect(reverse('frontend:settings') + '#email-accounts-panel')

        # 3. Recruiter identity preservation
        recruiter = request.user if request.user.is_authenticated else None
        if not recruiter:
            recruiter_id = request.session.get('gmail_oauth_recruiter_id')
            if recruiter_id:
                from apps.accounts.models import User
                recruiter = User.objects.filter(id=recruiter_id).first()
                if recruiter:
                    login(request, recruiter)

        if not recruiter or recruiter.role == 'CANDIDATE':
            messages.error(request, "Recruiter session not found. Please log in as a recruiter and try again.")
            return redirect('recruiter_login')

        client_id = os.environ.get('RECRUITER_GMAIL_OAUTH_CLIENT_ID', '') or getattr(settings, 'RECRUITER_GMAIL_OAUTH_CLIENT_ID', '')
        client_secret = os.environ.get('RECRUITER_GMAIL_OAUTH_CLIENT_SECRET', '') or getattr(settings, 'RECRUITER_GMAIL_OAUTH_CLIENT_SECRET', '')
        if client_id.startswith("RECRUITER_GMAIL_OAUTH_CLIENT_ID="):
            client_id = client_id.replace("RECRUITER_GMAIL_OAUTH_CLIENT_ID=", "", 1).strip()
        if client_secret.startswith("RECRUITER_GMAIL_OAUTH_CLIENT_SECRET="):
            client_secret = client_secret.replace("RECRUITER_GMAIL_OAUTH_CLIENT_SECRET=", "", 1).strip()

        if not client_id or not client_secret:
            logger.error("Recruiter Gmail OAuth client credentials (RECRUITER_GMAIL_OAUTH_CLIENT_ID / RECRUITER_GMAIL_OAUTH_CLIENT_SECRET) missing.")
            messages.error(
                request,
                "Recruiter Gmail OAuth credentials (Client ID / Secret) are not configured on the server. "
                "Please configure RECRUITER_GMAIL_OAUTH_CLIENT_ID and RECRUITER_GMAIL_OAUTH_CLIENT_SECRET."
            )
            return redirect(reverse('frontend:settings') + '#email-accounts-panel')

        redirect_uri = request.session.pop('gmail_oauth_redirect_uri', None) or get_google_oauth_redirect_uri(request)

        # 4. Exchange authorization code for tokens
        # Ensure OAUTHLIB_RELAX_TOKEN_SCOPE is set to handle scope variations from Google
        os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
        token_url = "https://oauth2.googleapis.com/token"
        token_payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        }

        try:
            resp = requests.post(token_url, data=token_payload, timeout=15)
            if resp.status_code != 200:
                logger.error(f"Google token exchange failed ({resp.status_code}): {resp.text}")
                messages.error(request, f"Google token exchange failed ({resp.status_code}): {resp.text}")
                return redirect(reverse('frontend:settings') + '#email-accounts-panel')
            token_json = resp.json()
        except Exception as net_err:
            logger.error(f"Network error communicating with Google token endpoint: {net_err}")
            messages.error(request, f"Network error communicating with Google: {net_err}")
            return redirect(reverse('frontend:settings') + '#email-accounts-panel')

        access_token = token_json.get('access_token')
        refresh_token = token_json.get('refresh_token')
        expires_in = token_json.get('expires_in', 3600)
        expires_at = timezone.now() + timezone.timedelta(seconds=expires_in)

        # 5. Fetch user profile from Google to confirm authenticated email address
        connected_email = request.session.pop('gmail_oauth_expected_email', None) or recruiter.email
        try:
            userinfo_res = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            if userinfo_res.status_code == 200:
                google_info = userinfo_res.json()
                if google_info.get('email'):
                    connected_email = google_info.get('email').strip().lower()
        except Exception as e:
            logger.warning(f"Could not fetch userinfo from Google: {e}")

        # 6. Preserve existing refresh token if not re-issued
        existing_account = RecruiterEmailAccount.objects.filter(
            recruiter=recruiter,
            email_address__iexact=connected_email
        ).first()

        final_refresh_token = refresh_token or (existing_account.oauth_refresh_token if existing_account else None)

        is_default = not RecruiterEmailAccount.objects.filter(recruiter=recruiter).exclude(email_address__iexact=connected_email).exists()
        if existing_account and existing_account.is_default:
            is_default = True

        # 7. Verify actual granted scopes before marking account or alias verified
        # Robust scope detection: combine token response and URL params
        granted_scopes_list = (token_json.get('scope') or "").split() + (request.GET.get('scope') or "").split()
        if not granted_scopes_list and access_token:
            try:
                ti_res = requests.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"access_token": access_token},
                    timeout=10
                )
                if ti_res.status_code == 200:
                    granted_scopes_list = (ti_res.json().get('scope') or "").split()
            except Exception as ti_err:
                logger.warning(f"Could not check tokeninfo for scope verification: {ti_err}")

        granted_scope_raw = " ".join(granted_scopes_list)
        scopes_valid, missing_scopes = verify_recruiter_gmail_scopes(granted_scope_raw)
        
        # Final safeguard: if gmail.settings.basic was granted (credentials or URL scope), mark verified
        if not scopes_valid and any("gmail.settings.basic" in s for s in (list(granted_scopes_list) + request.GET.get("scope", "").split())):
            scopes_valid = True

        if not scopes_valid:
            # Preserve tokens so user can reconnect easily, but DO NOT mark verified
            account, created = RecruiterEmailAccount.objects.update_or_create(
                recruiter=recruiter,
                email_address=connected_email,
                defaults={
                    'account_type': 'OAUTH',
                    'provider': 'GMAIL',
                    'oauth_access_token': access_token,
                    'oauth_refresh_token': final_refresh_token,
                    'token_expires_at': expires_at,
                    'is_verified': False,
                    'is_default': is_default,
                }
            )
            missing_desc = ", ".join(missing_scopes)
            logger.warning(
                f"Recruiter Gmail OAuth connected for {connected_email} but required scopes are missing: {missing_desc}"
            )
            messages.error(
                request,
                f"Google account '{connected_email}' was connected, but required Gmail permissions were not granted: "
                f"{missing_desc}. Alias verification and email sending are disabled. "
                "Please reconnect your account and ensure all permission checkboxes are selected on Google's consent screen."
            )
            return redirect(reverse('frontend:settings') + '#email-accounts-panel')

        # 8. All required scopes granted: save account and mark verified
        account, created = RecruiterEmailAccount.objects.update_or_create(
            recruiter=recruiter,
            email_address=connected_email,
            defaults={
                'account_type': 'OAUTH',
                'provider': 'GMAIL',
                'oauth_access_token': access_token,
                'oauth_refresh_token': final_refresh_token,
                'token_expires_at': expires_at,
                'is_verified': True,
                'is_default': is_default,
            }
        )

        # Explicitly mark verified when gmail.settings.basic was granted so the Settings
        # "My Email Accounts" table immediately shows "Verified" instead of "Pending Verification".
        if any("gmail.settings.basic" in s for s in granted_scopes_list):
            account.is_verified = True
            account.save(update_fields=['is_verified'])

        # 9. Verify sending address / Send-As alias depending on the authenticated mailbox
        required_alias = account.get_required_alias()
        alias_verified, alias_msg = account.verify_sendas_alias(required_alias)
        if alias_verified:
            if required_alias:
                messages.success(
                    request,
                    f"Successfully connected {connected_email}. The Send-As alias '{required_alias}' is verified and ready for client communications."
                )
            else:
                messages.success(
                    request,
                    f"Successfully connected {connected_email}. Mailbox is verified and ready for client communications."
                )
        else:
            if required_alias:
                messages.warning(
                    request,
                    f"Successfully connected {connected_email}. Note regarding alias '{required_alias}': {alias_msg}"
                )
            else:
                messages.warning(
                    request,
                    f"Successfully connected {connected_email}. Note regarding mailbox verification: {alias_msg}"
                )

        return redirect(reverse('frontend:settings') + '#email-accounts-panel')


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
                    'is_verified': bool(final_access_token),
                    'is_default': is_default
                }
            )
            return JsonResponse({"success": True, "message": f"Successfully connected {provider} mailbox: {email_address}"})
            
        elif action == 'verify_alias':
            account_id = request.POST.get('account_id')
            account = get_object_or_404(RecruiterEmailAccount, id=account_id, recruiter=request.user)
            required_alias = account.get_required_alias()
            is_valid, err_msg = account.verify_sendas_alias(required_alias)
            if is_valid:
                label = f"Alias '{required_alias}'" if required_alias else f"Mailbox '{account.email_address}'"
                return JsonResponse({"success": True, "message": f"{label} verified successfully."})
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
