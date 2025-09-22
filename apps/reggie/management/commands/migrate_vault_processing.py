from django.core.management.base import BaseCommand

from apps.reggie.utils.vault_utils import migrate_vault_schema


class Command(BaseCommand):
    help = "Migrate Vault AI processing from LangExtract to unified LlamaIndex service"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🔄 Starting Vault AI processing migration..."))

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
            self.stdout.write("Would perform the following actions:")
            self.stdout.write("1. Backup existing vault_embeddings table")
            self.stdout.write("2. Drop old table with custom schema")
            self.stdout.write("3. Create new table with LlamaIndex-compatible schema")
            self.stdout.write("4. All existing vault file embeddings will need to be re-processed")
            return

        try:
            # Migrate the vault vector table schema
            result = migrate_vault_schema()

            if result.get("success"):
                self.stdout.write(self.style.SUCCESS("✅ Successfully migrated vault vector table schema"))
                self.stdout.write(
                    self.style.WARNING(
                        "⚠️  All vault files will need to be re-embedded using the new processing pipeline"
                    )
                )
                self.stdout.write("Next steps:")
                self.stdout.write("1. Vault files will now be processed via the unified LlamaIndex service")
                self.stdout.write("2. No more LangExtract/Unstructured dependencies for vault processing")
                self.stdout.write("3. Consistent embedding model (text-embedding-3-small) for all vault files")
                self.stdout.write("4. Vector cleanup works automatically when files are deleted")

            else:
                self.stdout.write(self.style.ERROR(f"❌ Migration failed: {result.get('error', 'Unknown error')}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Migration failed with exception: {str(e)}"))
            raise
