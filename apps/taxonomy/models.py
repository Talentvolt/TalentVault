import re
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from apps.core.models import BaseAppModel


class TaxonomyStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', _('Active')
    INACTIVE = 'INACTIVE', _('Inactive (Soft-Deleted)')
    DEPRECATED = 'DEPRECATED', _('Deprecated')


class TaxonomySource(models.TextChoices):
    TV_URT = 'TV_URT', _('TalentVault Universal Recruitment Taxonomy (Core)')
    ESCO = 'ESCO', _('European Skills/Competences and Occupations (ESCO)')
    ONET = 'ONET', _('O*NET Occupational Information Network')
    OPEN_DATA = 'OPEN_DATA', _('Open Classification / Public Standards')
    MANUAL = 'MANUAL', _('Recruiter / Admin Defined')


class BaseTaxonomyEntity(BaseAppModel):
    """
    Abstract base entity for all TalentVault Universal Recruitment Taxonomy (TV-URT) components.
    Guarantees standard auditability, normalization, slugging, source tracking, and soft-delete behavior.
    """
    name = models.CharField(max_length=200, db_index=True)
    normalized_name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=220, blank=True, db_index=True)
    code = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=TaxonomyStatus.choices, default=TaxonomyStatus.ACTIVE, db_index=True)
    
    # Provenance & Open Dataset Licensing
    source = models.CharField(max_length=50, choices=TaxonomySource.choices, default=TaxonomySource.TV_URT, db_index=True)
    source_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    source_version = models.CharField(max_length=50, blank=True, default="1.0.0")
    license = models.CharField(max_length=100, blank=True, default="ODbL / CC BY 4.0 / TV-URT Open")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.normalized_name:
            self.normalized_name = re.sub(r'\s+', ' ', self.name.strip().lower())
        if not self.slug:
            self.slug = slugify(self.name)[:220]
        super().save(*args, **kwargs)


class Industry(BaseTaxonomyEntity):
    """
    Universal Employment Industry / Sector (50+ sectors: IT, Healthcare, Automotive, FMCG, Banking, etc.)
    """
    class Meta:
        ordering = ['name']
        verbose_name = _('industry')
        verbose_name_plural = _('industries')
        indexes = [
            models.Index(fields=['normalized_name', 'status']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.name


class Department(BaseTaxonomyEntity):
    """
    Standard Corporate Department / Functional Division (e.g. Engineering, Sales, HR, Finance, Operations)
    """
    class Meta:
        ordering = ['name']
        verbose_name = _('department')
        verbose_name_plural = _('departments')
        indexes = [
            models.Index(fields=['normalized_name', 'status']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.name


class JobFunction(BaseTaxonomyEntity):
    """
    Specific Job Function within a Department (e.g. Software Development, Field Sales, Talent Acquisition)
    """
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='job_functions')

    class Meta:
        ordering = ['name']
        verbose_name = _('job function')
        verbose_name_plural = _('job functions')
        indexes = [
            models.Index(fields=['normalized_name', 'status']),
            models.Index(fields=['department', 'status']),
        ]

    def __str__(self):
        dept_str = f" ({self.department.name})" if self.department else ""
        return f"{self.name}{dept_str}"


class JobRole(BaseTaxonomyEntity):
    """
    Universal Standardized Job Designation / Role across all seniorities and domains.
    """
    class SeniorityLevel(models.TextChoices):
        ENTRY = 'ENTRY', _('Entry-Level / Fresher')
        JUNIOR = 'JUNIOR', _('Junior / Associate / Officer')
        MID = 'MID', _('Mid-Level / Specialist / Executive')
        SENIOR = 'SENIOR', _('Senior / Lead / Principal')
        MANAGER = 'MANAGER', _('Manager / Assistant Manager / Deputy Manager')
        DIRECTOR = 'DIRECTOR', _('Director / Head / VP / AVP')
        EXECUTIVE = 'EXECUTIVE', _('CXO / President / Executive')

    class ExperienceLevel(models.TextChoices):
        FRESHER = 'FRESHER', _('0 - 1 Years')
        EARLY_CAREER = 'EARLY_CAREER', _('1 - 3 Years')
        MID_CAREER = 'MID_CAREER', _('3 - 6 Years')
        SENIOR_CAREER = 'SENIOR_CAREER', _('6 - 10 Years')
        LEADERSHIP = 'LEADERSHIP', _('10+ Years')

    canonical_name = models.CharField(max_length=200, db_index=True)
    industry = models.ForeignKey(Industry, on_delete=models.SET_NULL, null=True, blank=True, related_name='job_roles')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='job_roles')
    job_function = models.ForeignKey(JobFunction, on_delete=models.SET_NULL, null=True, blank=True, related_name='job_roles')
    seniority = models.CharField(max_length=30, choices=SeniorityLevel.choices, default=SeniorityLevel.MID, db_index=True)
    typical_experience = models.CharField(max_length=30, choices=ExperienceLevel.choices, default=ExperienceLevel.MID_CAREER, db_index=True)
    weight = models.FloatField(default=1.0, help_text="Search ranking importance weight (0.1 - 2.0)")

    class Meta:
        ordering = ['canonical_name']
        verbose_name = _('job role')
        verbose_name_plural = _('job roles')
        indexes = [
            models.Index(fields=['normalized_name', 'status']),
            models.Index(fields=['canonical_name', 'status']),
            models.Index(fields=['seniority', 'status']),
            models.Index(fields=['industry', 'department']),
        ]

    def save(self, *args, **kwargs):
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.canonical_name} ({self.get_seniority_display()})"


class Specialization(BaseTaxonomyEntity):
    """
    Sub-domain specialization for roles (e.g. Full Stack, Cloud Security, Direct Taxation, Clinical Research)
    """
    job_role = models.ForeignKey(JobRole, on_delete=models.SET_NULL, null=True, blank=True, related_name='specializations')
    job_function = models.ForeignKey(JobFunction, on_delete=models.SET_NULL, null=True, blank=True, related_name='specializations')

    class Meta:
        ordering = ['name']
        verbose_name = _('specialization')
        verbose_name_plural = _('specializations')

    def __str__(self):
        return self.name


class SkillCategory(BaseTaxonomyEntity):
    """
    Universal Category for Skills (e.g. Technical, Functional, Soft, Managerial, Domain, Tool, Platform)
    """
    class CategoryType(models.TextChoices):
        TECHNICAL = 'TECHNICAL', _('Technical / Hard Skill')
        FUNCTIONAL = 'FUNCTIONAL', _('Functional / Business Skill')
        DOMAIN = 'DOMAIN', _('Domain / Industry Knowledge')
        SOFT_SKILL = 'SOFT_SKILL', _('Soft / Interpersonal Skill')
        MANAGERIAL = 'MANAGERIAL', _('Management & Leadership')
        TOOL = 'TOOL', _('Tool / Software')
        LANGUAGE = 'LANGUAGE', _('Language / Communication')

    category_type = models.CharField(max_length=30, choices=CategoryType.choices, default=CategoryType.TECHNICAL, db_index=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('skill category')
        verbose_name_plural = _('skill categories')

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"


class Skill(BaseTaxonomyEntity):
    """
    Standardized Universal Skill across technical, business, trade, and domain specializations.
    """
    class SkillType(models.TextChoices):
        HARD_SKILL = 'HARD_SKILL', _('Hard / Functional Skill')
        SOFT_SKILL = 'SOFT_SKILL', _('Soft / Cognitive Skill')
        DOMAIN_KNOWLEDGE = 'DOMAIN_KNOWLEDGE', _('Domain Knowledge')
        METHODOLOGY = 'METHODOLOGY', _('Methodology / Framework')

    canonical_name = models.CharField(max_length=200, db_index=True)
    category = models.ForeignKey(SkillCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='skills')
    skill_type = models.CharField(max_length=30, choices=SkillType.choices, default=SkillType.HARD_SKILL, db_index=True)
    is_popular = models.BooleanField(default=False, db_index=True)
    weight = models.FloatField(default=1.0)

    class Meta:
        ordering = ['canonical_name']
        verbose_name = _('skill')
        verbose_name_plural = _('skills')
        indexes = [
            models.Index(fields=['normalized_name', 'status']),
            models.Index(fields=['canonical_name', 'status']),
            models.Index(fields=['category', 'status']),
        ]

    def save(self, *args, **kwargs):
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        cat_str = f" [{self.category.name}]" if self.category else ""
        return f"{self.canonical_name}{cat_str}"


class Technology(BaseTaxonomyEntity):
    """
    Technology Stacks, Programming Languages, Frameworks, Cloud Services, and Databases.
    """
    class TechCategory(models.TextChoices):
        PROGRAMMING_LANGUAGE = 'PROGRAMMING_LANGUAGE', _('Programming Language')
        FRAMEWORK = 'FRAMEWORK', _('Framework / Library')
        DATABASE = 'DATABASE', _('Database / Data Store')
        CLOUD_PLATFORM = 'CLOUD_PLATFORM', _('Cloud Platform / Infrastructure')
        DEVOPS_TOOL = 'DEVOPS_TOOL', _('DevOps / CI/CD Tool')
        OPERATING_SYSTEM = 'OPERATING_SYSTEM', _('Operating System')
        AI_FRAMEWORK = 'AI_FRAMEWORK', _('AI / ML / Data Science Stack')

    canonical_name = models.CharField(max_length=200, db_index=True)
    tech_category = models.CharField(max_length=40, choices=TechCategory.choices, default=TechCategory.FRAMEWORK, db_index=True)
    vendor = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        ordering = ['canonical_name']
        verbose_name = _('technology')
        verbose_name_plural = _('technologies')
        indexes = [
            models.Index(fields=['normalized_name', 'status']),
            models.Index(fields=['canonical_name', 'status']),
            models.Index(fields=['tech_category', 'status']),
        ]

    def save(self, *args, **kwargs):
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.canonical_name} ({self.get_tech_category_display()})"


class Tool(BaseTaxonomyEntity):
    """
    Software Applications, SaaS Tools, ERPs, CRMs, IDEs, and Diagnostic Hardware.
    """
    class ToolType(models.TextChoices):
        CRM = 'CRM', _('CRM Platform (Salesforce, HubSpot, Zoho)')
        ERP = 'ERP', _('ERP Platform (SAP, Oracle, Tally)')
        ANALYTICS = 'ANALYTICS', _('BI & Analytics (Tableau, PowerBI, Excel)')
        DESIGN = 'DESIGN', _('Design & CAD (AutoCAD, Figma, SolidWorks)')
        COLLABORATION = 'COLLABORATION', _('Productivity & Collaboration (Jira, Slack)')
        DIAGNOSTIC = 'DIAGNOSTIC', _('Industrial / Diagnostic Tool (OBD, Multimeter)')
        MEDICAL = 'MEDICAL', _('Medical / Lab Equipment')

    canonical_name = models.CharField(max_length=200, db_index=True)
    tool_type = models.CharField(max_length=30, choices=ToolType.choices, default=ToolType.ANALYTICS, db_index=True)
    vendor = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        ordering = ['canonical_name']
        verbose_name = _('tool')
        verbose_name_plural = _('tools')
        indexes = [
            models.Index(fields=['normalized_name', 'status']),
            models.Index(fields=['canonical_name', 'status']),
        ]

    def save(self, *args, **kwargs):
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.canonical_name} ({self.get_tool_type_display()})"


class Certification(BaseTaxonomyEntity):
    """
    Professional Certifications & Accreditations (e.g. AWS Solutions Architect, PMP, Chartered Accountant, Six Sigma)
    """
    canonical_name = models.CharField(max_length=200, db_index=True)
    issuing_organization = models.CharField(max_length=200, blank=True, default="")
    industry = models.ForeignKey(Industry, on_delete=models.SET_NULL, null=True, blank=True, related_name='certifications')
    validity_years = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['canonical_name']
        verbose_name = _('certification')
        verbose_name_plural = _('certifications')

    def save(self, *args, **kwargs):
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        org = f" - {self.issuing_organization}" if self.issuing_organization else ""
        return f"{self.canonical_name}{org}"


class Qualification(BaseTaxonomyEntity):
    """
    Educational Degrees & Qualifications (e.g. B.Tech, M.S, MBA, MBBS, B.Pharm, CA, Diploma)
    """
    class DegreeLevel(models.TextChoices):
        DIPLOMA = 'DIPLOMA', _('Diploma / Vocational')
        BACHELORS = 'BACHELORS', _('Bachelor\'s Degree')
        MASTERS = 'MASTERS', _('Master\'s Degree / Postgraduate')
        DOCTORATE = 'DOCTORATE', _('Doctorate / Ph.D')
        PROFESSIONAL = 'PROFESSIONAL', _('Professional Qualification (CA/CS/CMA)')

    canonical_name = models.CharField(max_length=200, db_index=True)
    degree_level = models.CharField(max_length=30, choices=DegreeLevel.choices, default=DegreeLevel.BACHELORS, db_index=True)
    discipline = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        ordering = ['canonical_name']
        verbose_name = _('qualification')
        verbose_name_plural = _('qualifications')

    def save(self, *args, **kwargs):
        if not self.canonical_name:
            self.canonical_name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.canonical_name} ({self.get_degree_level_display()})"


class TaxonomyAlias(BaseAppModel):
    """
    Universal Alias / Synonym Engine mapping abbreviations, alternate titles, and spelling variants to canonical entities.
    Examples:
      - 'SDE' -> 'Software Engineer' (ABBREVIATION)
      - 'BDE' -> 'Business Development Executive' (ABBREVIATION)
      - 'ASM' -> 'Area Sales Manager' (ACRONYM)
      - 'ReactJS' -> 'React' (SYNONYM)
    """
    class EntityType(models.TextChoices):
        JOB_ROLE = 'JOB_ROLE', _('Job Role / Designation')
        SKILL = 'SKILL', _('Skill')
        TECHNOLOGY = 'TECHNOLOGY', _('Technology')
        TOOL = 'TOOL', _('Tool')
        CERTIFICATION = 'CERTIFICATION', _('Certification')
        QUALIFICATION = 'QUALIFICATION', _('Qualification')

    class AliasType(models.TextChoices):
        ABBREVIATION = 'ABBREVIATION', _('Abbreviation / Short Form (e.g. SDE, BDE)')
        SYNONYM = 'SYNONYM', _('Synonym / Equivalent Term')
        ACRONYM = 'ACRONYM', _('Acronym (e.g. ASM, BDM, MR)')
        SPELLING_VARIANT = 'SPELLING_VARIANT', _('Spelling Variant (e.g. React.js, ReactJS)')
        SLANG = 'SLANG', _('Industry Slang / Informal Term')

    alias = models.CharField(max_length=200, db_index=True)
    normalized_alias = models.CharField(max_length=200, db_index=True)
    entity_type = models.CharField(max_length=30, choices=EntityType.choices, default=EntityType.JOB_ROLE, db_index=True)
    alias_type = models.CharField(max_length=30, choices=AliasType.choices, default=AliasType.SYNONYM, db_index=True)
    canonical_name = models.CharField(max_length=200, db_index=True)
    
    # Optional Foreign Keys to Canonical Entities
    job_role = models.ForeignKey(JobRole, on_delete=models.CASCADE, null=True, blank=True, related_name='aliases')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, null=True, blank=True, related_name='aliases')
    technology = models.ForeignKey(Technology, on_delete=models.CASCADE, null=True, blank=True, related_name='aliases')
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, null=True, blank=True, related_name='aliases')
    
    status = models.CharField(max_length=20, choices=TaxonomyStatus.choices, default=TaxonomyStatus.ACTIVE, db_index=True)
    confidence = models.FloatField(default=0.95)
    source = models.CharField(max_length=50, choices=TaxonomySource.choices, default=TaxonomySource.TV_URT)

    class Meta:
        unique_together = ('normalized_alias', 'entity_type', 'canonical_name')
        verbose_name = _('taxonomy alias')
        verbose_name_plural = _('taxonomy aliases')
        indexes = [
            models.Index(fields=['normalized_alias', 'entity_type', 'status']),
            models.Index(fields=['canonical_name', 'status']),
        ]

    def save(self, *args, **kwargs):
        if not self.normalized_alias:
            self.normalized_alias = re.sub(r'\s+', ' ', self.alias.strip().lower())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"'{self.alias}' -> {self.canonical_name} ({self.get_alias_type_display()})"


class RoleSkill(BaseAppModel):
    """
    Weighted Ontology Relationship between Job Roles and Skills / Technologies / Tools.
    """
    class RelationType(models.TextChoices):
        PRIMARY_SKILL = 'PRIMARY_SKILL', _('Primary / Core Skill (High Match Priority)')
        SECONDARY_SKILL = 'SECONDARY_SKILL', _('Secondary / Supporting Skill')
        MANDATORY = 'MANDATORY', _('Mandatory Required Skill')
        DOMAIN_SKILL = 'DOMAIN_SKILL', _('Domain / Functional Competency')
        TOOL = 'TOOL', _('Tool / Technology')

    role = models.ForeignKey(JobRole, on_delete=models.CASCADE, related_name='role_skills')
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, null=True, blank=True, related_name='skill_roles')
    technology = models.ForeignKey(Technology, on_delete=models.CASCADE, null=True, blank=True, related_name='tech_roles')
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE, null=True, blank=True, related_name='tool_roles')
    
    relation_type = models.CharField(max_length=30, choices=RelationType.choices, default=RelationType.PRIMARY_SKILL, db_index=True)
    weight = models.FloatField(default=0.90, db_index=True, help_text="Relationship relevance strength (0.0 to 1.0)")
    status = models.CharField(max_length=20, choices=TaxonomyStatus.choices, default=TaxonomyStatus.ACTIVE)
    source = models.CharField(max_length=50, choices=TaxonomySource.choices, default=TaxonomySource.TV_URT)

    class Meta:
        verbose_name = _('role skill mapping')
        verbose_name_plural = _('role skill mappings')
        indexes = [
            models.Index(fields=['role', 'relation_type', 'weight']),
            models.Index(fields=['skill', 'weight']),
        ]

    def __str__(self):
        target = self.skill.canonical_name if self.skill else (self.technology.canonical_name if self.technology else (self.tool.canonical_name if self.tool else "N/A"))
        return f"{self.role.canonical_name} <-> {target} ({self.get_relation_type_display()}: {self.weight})"


class RoleRelation(BaseAppModel):
    """
    Multi-Directional Semantic & Career Graph Relationships between Roles.
    """
    class RelationType(models.TextChoices):
        PARENT_ROLE = 'PARENT_ROLE', _('Parent / Senior Hierarchy Role (e.g. Sales Manager -> ASM)')
        CHILD_ROLE = 'CHILD_ROLE', _('Child / Subordinate Role')
        SENIORITY_VARIANT = 'SENIORITY_VARIANT', _('Seniority Variant (e.g. Senior Software Engineer -> Software Engineer)')
        RELATED_ROLE = 'RELATED_ROLE', _('Related Functional Role (e.g. Sales Manager -> BD Manager)')
        FUNCTIONAL_EQUIVALENT = 'FUNCTIONAL_EQUIVALENT', _('Functional Equivalent (e.g. Sales Executive <-> Sales Officer)')
        ADJACENT_ROLE = 'ADJACENT_ROLE', _('Adjacent Lateral Role (e.g. Service Advisor <-> Automobile Technician)')
        CROSS_INDUSTRY = 'CROSS_INDUSTRY', _('Cross-Industry Transferable Role')

    source_role = models.ForeignKey(JobRole, on_delete=models.CASCADE, related_name='outgoing_role_relations')
    target_role = models.ForeignKey(JobRole, on_delete=models.CASCADE, related_name='incoming_role_relations')
    relation_type = models.CharField(max_length=30, choices=RelationType.choices, default=RelationType.RELATED_ROLE, db_index=True)
    weight = models.FloatField(default=0.85, db_index=True)
    is_bidirectional = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=TaxonomyStatus.choices, default=TaxonomyStatus.ACTIVE)
    source = models.CharField(max_length=50, choices=TaxonomySource.choices, default=TaxonomySource.TV_URT)

    class Meta:
        unique_together = ('source_role', 'target_role', 'relation_type')
        verbose_name = _('role relationship')
        verbose_name_plural = _('role relationships')
        indexes = [
            models.Index(fields=['relation_type', 'weight']),
        ]

    def __str__(self):
        return f"{self.source_role.canonical_name} -> {self.target_role.canonical_name} ({self.get_relation_type_display()}: {self.weight})"


class RoleHierarchy(BaseAppModel):
    """
    Tree-structured Career Progression & Domain Expansion ladder.
    """
    parent_role = models.ForeignKey(JobRole, on_delete=models.CASCADE, related_name='subordinate_hierarchies')
    child_role = models.ForeignKey(JobRole, on_delete=models.CASCADE, related_name='parent_hierarchies')
    depth = models.PositiveIntegerField(default=1)
    ladder_track = models.CharField(max_length=100, blank=True, default="Standard", help_text="e.g. Individual Contributor, Management, Technical")

    class Meta:
        unique_together = ('parent_role', 'child_role', 'ladder_track')
        verbose_name = _('role hierarchy')
        verbose_name_plural = _('role hierarchies')

    def __str__(self):
        return f"{self.parent_role.canonical_name} > {self.child_role.canonical_name} (Track: {self.ladder_track})"


class IndustryRole(BaseAppModel):
    """
    Many-to-Many Bridge between Industries and Standard Roles.
    """
    industry = models.ForeignKey(Industry, on_delete=models.CASCADE, related_name='industry_role_mappings')
    job_role = models.ForeignKey(JobRole, on_delete=models.CASCADE, related_name='role_industry_mappings')
    is_primary = models.BooleanField(default=True)

    class Meta:
        unique_together = ('industry', 'job_role')
        verbose_name = _('industry role mapping')
        verbose_name_plural = _('industry role mappings')

    def __str__(self):
        return f"{self.industry.name} - {self.job_role.canonical_name}"


class TaxonomyImportLog(BaseAppModel):
    """
    Audit Log for Taxonomy Imports from ESCO, O*NET, and TV-URT datasets.
    """
    class ImportStatus(models.TextChoices):
        SUCCESS = 'SUCCESS', _('Success')
        PARTIAL = 'PARTIAL', _('Partial with Warnings')
        FAILED = 'FAILED', _('Failed')

    source_name = models.CharField(max_length=100, db_index=True)
    version = models.CharField(max_length=50, default="1.0.0")
    license = models.CharField(max_length=100, default="Open Data")
    file_name = models.CharField(max_length=255, blank=True, default="")
    records_processed = models.IntegerField(default=0)
    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    duplicates_skipped = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)
    error_details = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=ImportStatus.choices, default=ImportStatus.SUCCESS, db_index=True)
    statistics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('taxonomy import log')
        verbose_name_plural = _('taxonomy import logs')

    def __str__(self):
        return f"{self.source_name} Import v{self.version} ({self.get_status_display()}) at {self.created_at.strftime('%Y-%m-%d %H:%M')}"


# Register pre-save sanitization handler for all taxonomy models to safeguard against NUL bytes
from django.db.models.signals import pre_save
from django.dispatch import receiver

@receiver(pre_save, sender=Industry)
@receiver(pre_save, sender=Department)
@receiver(pre_save, sender=JobFunction)
@receiver(pre_save, sender=JobRole)
@receiver(pre_save, sender=Specialization)
@receiver(pre_save, sender=SkillCategory)
@receiver(pre_save, sender=Skill)
@receiver(pre_save, sender=Technology)
@receiver(pre_save, sender=Tool)
@receiver(pre_save, sender=Certification)
@receiver(pre_save, sender=Qualification)
@receiver(pre_save, sender=TaxonomyAlias)
@receiver(pre_save, sender=RoleSkill)
@receiver(pre_save, sender=RoleRelation)
@receiver(pre_save, sender=RoleHierarchy)
@receiver(pre_save, sender=IndustryRole)
@receiver(pre_save, sender=TaxonomyImportLog)
def pre_save_sanitize_taxonomy_handler(sender, instance, **kwargs):
    from apps.candidates.utils import sanitize_text, sanitize_recursive
    import django.db.models as django_models
    for field in instance._meta.fields:
        if isinstance(field, (django_models.CharField, django_models.TextField)):
            val = getattr(instance, field.name, None)
            if val is not None:
                path = f"{instance.__class__.__name__}.{field.name}"
                sanitized = sanitize_text(val, path, print_on_nul=True)
                setattr(instance, field.name, sanitized)
        elif isinstance(field, django_models.JSONField):
            val = getattr(instance, field.name, None)
            if val is not None:
                path = f"{instance.__class__.__name__}.{field.name}"
                sanitized = sanitize_recursive(val, path)
                setattr(instance, field.name, sanitized)
