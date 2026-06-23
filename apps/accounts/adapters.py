import traceback
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from allauth.socialaccount.models import SocialAccount
from allauth.account.models import EmailAddress

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user_profile(self, user, sociallogin):
        try:
            extra_data = sociallogin.account.extra_data
            
            # Update first and last name from Google extra_data
            if 'name' in extra_data:
                user.first_name = extra_data.get('given_name', '')
                user.last_name = extra_data.get('family_name', '')
                if not user.first_name and not user.last_name:
                    user.first_name = extra_data.get('name', '')
            if 'picture' in extra_data:
                user.profile_picture = extra_data.get('picture', '')
                
            # Ensure user role is RECRUITER
            user.role = User.Role.RECRUITER
            user.save()
            
            # Ensure default company association exists for dashboard integrity
            try:
                company, _ = Company.objects.get_or_create(
                    name="TalentVault Technologies",
                    defaults={
                        'slug': 'talentvault-technologies',
                        'industry': 'Software Product',
                        'description': 'Default organization created during Google Sign-In.',
                        'location': 'Remote'
                    }
                )
                # Associate user to this company as Admin / Recruiter
                CompanyMember.objects.get_or_create(
                    company=company,
                    user=user,
                    defaults={
                        'designation': 'Recruiter',
                        'role': CompanyMember.MemberRole.ADMIN
                    }
                )
            except Exception as company_err:
                print(f"Error associating default company: {company_err}")
                traceback.print_exc()
        except Exception as profile_err:
            print(f"Error in populate_user_profile: {profile_err}")
            traceback.print_exc()
            raise profile_err

    def pre_social_login(self, request, sociallogin):
        try:
            # If the account is already associated with a user, proceed with profile updates
            if sociallogin.is_existing:
                self.populate_user_profile(sociallogin.user, sociallogin)
                return
                
            email = sociallogin.user.email
            if not email:
                return
                
            try:
                user = User.objects.get(email=email)
                # Manually link the SocialAccount record to the existing user in DB
                SocialAccount.objects.get_or_create(
                    user=user,
                    provider=sociallogin.account.provider,
                    uid=sociallogin.account.uid,
                    defaults={
                        'extra_data': sociallogin.account.extra_data
                    }
                )
                
                # Ensure EmailAddress record exists and is marked primary & verified
                EmailAddress.objects.get_or_create(
                    user=user,
                    email=email,
                    defaults={'verified': True, 'primary': True}
                )
                
                # Link the current social login session to this existing user
                sociallogin.user = user
                
                # Populate profile and company settings
                self.populate_user_profile(user, sociallogin)
                
            except User.DoesNotExist:
                pass
        except Exception as pre_login_err:
            print(f"Error in pre_social_login: {pre_login_err}")
            traceback.print_exc()
            raise pre_login_err

    def save_user(self, request, sociallogin, form=None):
        try:
            # Let allauth save the user model first
            user = super().save_user(request, sociallogin, form)
            self.populate_user_profile(user, sociallogin)
            return user
        except Exception as save_user_err:
            print(f"Error in save_user: {save_user_err}")
            traceback.print_exc()
            raise save_user_err

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        print("="*40 + " GOOGLE OAUTH AUTHENTICATION ERROR " + "="*40)
        print(f"Provider: {provider}")
        print(f"Error: {error}")
        print(f"Exception: {exception}")
        if exception:
            traceback.print_exception(type(exception), exception, exception.__traceback__)
        else:
            traceback.print_exc()
        print("="*110)
        super().on_authentication_error(request, provider, error, exception, extra_context)

