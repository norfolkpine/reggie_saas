from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.reggie.models import KnowledgeBase  # Assuming your KnowledgeBase model is here


class Command(BaseCommand):
    help = (
        "Identifies and optionally drops orphaned vector tables in the database "
        "that are no longer associated with any KnowledgeBase. "
        'Vector tables are assumed to follow the naming convention "kb%".'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,  # Default behavior is dry run
            help="If True (default), only lists orphaned tables. Overridden by --execute or --generate-sql if they are set to False explicitly by user (though store_true makes them default to False if not present).",
        )
        parser.add_argument(
            "--generate-sql",
            action="store_true",
            help="If True, prints DROP TABLE SQL statements instead of just listing table names. Does not execute.",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="If True, actually executes DROP TABLE commands. Requires confirmation. USE WITH EXTREME CAUTION.",
        )
        # To make --dry-run truly default unless --generate-sql or --execute is given:
        # We'll check the combination of flags in the handle method.
        # If neither --generate-sql nor --execute is specified, --dry-run behavior will proceed.

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        generate_sql = options["generate_sql"]
        execute = options["execute"]

        # Determine operational mode:
        # If --execute is given, dry_run and generate_sql are implicitly False for action.
        # If --generate-sql is given (and not --execute), dry_run is implicitly False for action.
        # If only --dry-run is given or no operational flags, it's a dry run.
        if execute:
            operational_mode = "execute"
            self.stdout.write(self.style.WARNING("EXECUTE MODE: Orphaned tables will be dropped after confirmation."))
        elif generate_sql:
            operational_mode = "generate_sql"
            self.stdout.write(self.style.NOTICE("GENERATE SQL MODE: SQL for dropping tables will be shown."))
        else:  # This includes explicit --dry-run or default behavior
            operational_mode = "dry_run"
            self.stdout.write(self.style.NOTICE("DRY RUN MODE: Listing orphaned tables."))

        # 1. Get all table names from the database matching the pattern 'kb%'
        # The KnowledgeBase model creates tables like: kb<provider_initial>-<short_code>-<slug>
        # e.g. kbo-1a2b3c-my-kb-name
        # So, 'kb%' seems like a reasonable pattern.
        with connection.cursor() as cursor:
            # Querying information_schema is standard SQL for metadata
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name LIKE 'kb%';
            """)
            db_vector_tables = {row[0] for row in cursor.fetchall()}

        if not db_vector_tables:
            self.stdout.write(self.style.SUCCESS('No tables matching the pattern "kb%" found in the public schema.'))
            return

        # 2. Get all active vector_table_name values from KnowledgeBase model
        active_kb_table_names = set(KnowledgeBase.objects.values_list("vector_table_name", flat=True))

        # 3. Identify orphaned tables
        orphaned_tables = sorted(list(db_vector_tables - active_kb_table_names))

        if not orphaned_tables:
            self.stdout.write(self.style.SUCCESS("No orphaned vector tables found."))
            return

        # 4. Perform action based on options
        if operational_mode == "dry_run":
            self.stdout.write(self.style.NOTICE(f"\nFound {len(orphaned_tables)} orphaned vector table(s):"))
            for table_name in orphaned_tables:
                self.stdout.write(table_name)
            self.stdout.write(
                self.style.WARNING("\nTo generate SQL for dropping these tables, run with --generate-sql.")
            )
            self.stdout.write(self.style.WARNING("To drop these tables, run with --execute (USE WITH CAUTION)."))

        elif operational_mode == "generate_sql":
            self.stdout.write(self.style.NOTICE(f"\nSQL to drop {len(orphaned_tables)} orphaned vector table(s):"))
            for table_name in orphaned_tables:
                self.stdout.write(f'DROP TABLE IF EXISTS public."{table_name}";')  # Ensure table name is quoted
            self.stdout.write(self.style.WARNING("\nTo execute these commands, run with --execute (USE WITH CAUTION)."))
            self.stdout.write(self.style.WARNING("Ensure you have a database backup before running with --execute."))

        elif operational_mode == "execute":
            self.stdout.write(
                self.style.WARNING(f"\nFound {len(orphaned_tables)} orphaned vector table(s) to be DROPPED:")
            )
            for table_name in orphaned_tables:
                self.stdout.write(self.style.WARNING(f"- {table_name}"))

            self.stdout.write(self.style.ERROR("\nTHIS OPERATION IS PERMANENT AND CANNOT BE UNDONE."))
            self.stdout.write(self.style.WARNING("Ensure you have a database backup."))

            confirmation = input("Are you absolutely sure you want to drop these tables? (yes/no): ")
            if confirmation.lower() == "yes":
                try:
                    with connection.cursor() as cursor:
                        for table_name in orphaned_tables:
                            sql = f'DROP TABLE IF EXISTS public."{table_name}";'  # Ensure table name is quoted
                            self.stdout.write(f"Executing: {sql}")
                            cursor.execute(sql)
                            self.stdout.write(self.style.SUCCESS(f'Successfully dropped table: "{table_name}"'))
                    self.stdout.write(self.style.SUCCESS("\nOrphaned table cleanup process completed."))
                except Exception as e:
                    raise CommandError(f"An error occurred during table deletion: {str(e)}")
            else:
                self.stdout.write(self.style.ERROR("Operation cancelled by user."))

        else:  # Should not happen due to logic above
            raise CommandError("Invalid operational mode. This is a bug in the command.")
