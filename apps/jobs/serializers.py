from rest_framework import serializers
from apps.jobs.models import Job, JobSkill
from apps.companies.serializers import CompanySerializer

class JobSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobSkill
        fields = ('id', 'skill_name', 'is_mandatory')

class JobSerializer(serializers.ModelSerializer):
    skills = JobSkillSerializer(many=True, required=False)
    company_details = CompanySerializer(source='company', read_only=True)

    class Meta:
        model = Job
        fields = (
            'id', 'company', 'company_details', 'title', 'description', 'location', 
            'job_type', 'experience_level', 'min_experience', 'max_experience', 
            'min_salary', 'max_salary', 'currency', 'status', 'is_remote', 
            'application_deadline', 'skills', 'created_at'
        )
        read_only_fields = ('id', 'created_at')

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.min_salary is not None:
            ret['min_salary'] = instance.min_salary_lpa
        if instance.max_salary is not None:
            ret['max_salary'] = instance.max_salary_lpa
        return ret

    def create(self, validated_data):
        skills_data = validated_data.pop('skills', [])
        job = Job.objects.create(**validated_data)
        
        for skill_data in skills_data:
            JobSkill.objects.create(job=job, **skill_data)
            
        return job

    def update(self, instance, validated_data):
        skills_data = validated_data.pop('skills', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if skills_data is not None:
            instance.skills.all().delete()
            for skill_data in skills_data:
                JobSkill.objects.create(job=instance, **skill_data)

        return instance
