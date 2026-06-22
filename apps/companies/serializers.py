from rest_framework import serializers
from apps.companies.models import Company, CompanyMember
from apps.accounts.serializers import UserSerializer

class CompanyMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = CompanyMember
        fields = ('id', 'company', 'user', 'user_id', 'designation', 'role', 'created_at')
        read_only_fields = ('id', 'company', 'created_at')

class CompanySerializer(serializers.ModelSerializer):
    members = CompanyMemberSerializer(many=True, read_only=True)

    class Meta:
        model = Company
        fields = (
            'id', 'name', 'slug', 'website', 'industry', 'description', 
            'logo', 'address', 'location', 'employee_count', 'is_active',
            'members', 'created_at'
        )
        read_only_fields = ('id', 'slug', 'is_active', 'created_at')
