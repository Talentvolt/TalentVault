"""
Django Management Command: python manage.py seed_taxonomy
Instant seeder for TalentVault Universal Recruitment Taxonomy (TV-URT).
"""
from django.core.management.base import BaseCommand
from apps.taxonomy.services.taxonomy_seeder import TaxonomySeeder
from apps.taxonomy.services.taxonomy_importer import TaxonomyImporter


class Command(BaseCommand):
    help = "Seeds pre-built universal recruitment taxonomy across 50+ employment domains."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing taxonomy before seeding'
        )

    def handle(self, *args, **options):
        self.stdout.write("[*] Seeding TalentVault Universal Recruitment Taxonomy (TV-URT)...")
        stats = TaxonomySeeder.seed_all(clear_existing=options.get('clear', False))
        self.stdout.write(self.style.SUCCESS(f"[+] Successfully seeded TV-URT! Total entities and relations created: {sum(stats.values())}"))
