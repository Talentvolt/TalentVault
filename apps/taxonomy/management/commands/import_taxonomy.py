"""
Django Management Command: python manage.py import_taxonomy
Imports, validates, and indexes TalentVault Universal Recruitment Taxonomy (TV-URT).
"""
from django.core.management.base import BaseCommand
from apps.taxonomy.services.taxonomy_importer import TaxonomyImporter


class Command(BaseCommand):
    help = "Imports and indexes TalentVault Universal Recruitment Taxonomy (TV-URT) from open/public datasets."

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            type=str,
            default='all',
            help='Taxonomy source to import: tv_urt, esco, onet, all'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Import full pre-built universal taxonomy across all 50+ domains'
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Display live summary statistics of the current taxonomy'
        )
        parser.add_argument(
            '--file',
            type=str,
            help='Optional custom JSON or CSV file path to import'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate import without committing to database'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))
        self.stdout.write(self.style.MIGRATE_HEADING("  TALENTVAULT UNIVERSAL RECRUITMENT TAXONOMY (TV-URT) IMPORTER    "))
        self.stdout.write(self.style.MIGRATE_HEADING("=================================================================="))

        if options.get('stats'):
            self._display_stats()
            return

        source = 'all' if options.get('all') else options.get('source', 'all')
        file_path = options.get('file')
        dry_run = options.get('dry_run', False)

        self.stdout.write(f"[*] Starting taxonomy ingestion for source: '{source}' (dry-run: {dry_run})...")

        stats = TaxonomyImporter.import_source(
            source=source,
            file_path=file_path,
            dry_run=dry_run
        )

        self.stdout.write(self.style.SUCCESS("[+] Taxonomy import completed successfully!"))
        self.stdout.write(f"    - Industries Created:   {stats.get('industries_created', 0)}")
        self.stdout.write(f"    - Departments Created:  {stats.get('departments_created', 0)}")
        self.stdout.write(f"    - Job Roles Created:    {stats.get('roles_created', 0)}")
        self.stdout.write(f"    - Skills Created:       {stats.get('skills_created', 0)}")
        self.stdout.write(f"    - Technologies Created: {stats.get('technologies_created', 0)}")
        self.stdout.write(f"    - Tools Created:        {stats.get('tools_created', 0)}")
        self.stdout.write(f"    - Aliases Created:      {stats.get('aliases_created', 0)}")
        self.stdout.write(f"    - Relations Created:    {stats.get('relations_created', 0)}")
        if stats.get('duplicates_skipped', 0) > 0:
            self.stdout.write(f"    - Duplicates Skipped:   {stats.get('duplicates_skipped')}")

        self.stdout.write("")
        self._display_stats()

    def _display_stats(self):
        summary = TaxonomyImporter.get_summary_statistics()

        self.stdout.write(self.style.HTTP_INFO("------------------------------------------------------------------"))
        self.stdout.write(self.style.HTTP_INFO("  LIVE TAXONOMY ENTITY STATISTICS (TV-URT)                        "))
        self.stdout.write(self.style.HTTP_INFO("------------------------------------------------------------------"))
        self.stdout.write(f"  TOTAL INDUSTRIES:       {summary['total_industries']:>6}")
        self.stdout.write(f"  TOTAL DEPARTMENTS:      {summary['total_departments']:>6}")
        self.stdout.write(f"  TOTAL JOB FUNCTIONS:    {summary['total_job_functions']:>6}")
        self.stdout.write(f"  TOTAL JOB ROLES:        {summary['total_job_roles']:>6}")
        self.stdout.write(f"  TOTAL SKILLS:           {summary['total_skills']:>6}")
        self.stdout.write(f"  TOTAL TECHNOLOGIES:     {summary['total_technologies']:>6}")
        self.stdout.write(f"  TOTAL TOOLS:            {summary['total_tools']:>6}")
        self.stdout.write(f"  TOTAL CERTIFICATIONS:   {summary['total_certifications']:>6}")
        self.stdout.write(f"  TOTAL QUALIFICATIONS:   {summary['total_qualifications']:>6}")
        self.stdout.write(f"  TOTAL ALIASES:          {summary['total_aliases']:>6}")
        self.stdout.write(f"  TOTAL ROLE SKILLS:      {summary['total_role_skills']:>6}")
        self.stdout.write(f"  TOTAL ROLE RELATIONS:   {summary['total_role_relations']:>6}")
        self.stdout.write(self.style.HTTP_INFO("------------------------------------------------------------------"))
        self.stdout.write("  DATASET SOURCES & LICENSING:")
        for src in summary.get("sources", []):
            self.stdout.write(f"  * {src['name']}")
            self.stdout.write(f"    License: {src['license']}")
        self.stdout.write(self.style.HTTP_INFO("=================================================================="))
