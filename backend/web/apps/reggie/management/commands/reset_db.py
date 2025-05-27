import sys

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Resets the database - drops all tables and recreates them. USE WITH CAUTION!"

    def add_arguments(self, parser):
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            help="Tells Django to NOT prompt the user for input of any kind.",
        )
        parser.add_argument(
            "--delete-migrations",
            action="store_true",
            help="Delete all migration files before running migrations",
        )
        parser.add_argument("--superuser-email", help="Email for the superuser account", default="admin@example.com")
        parser.add_argument("--superuser-password", help="Password for the superuser account", default="admin")

    def _run_load_commands(self):
        """Run all data loading commands"""
        load_commands = [
            "load_model_providers",
            "load_agent_instructions",
            "load_agent_outputs",
        ]

        for command in load_commands:
            try:
                self.stdout.write(f"Running {command}...")
                call_command(command)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Failed to run {command}: {e}"))

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stdout.write(self.style.ERROR("This command can only be run in DEBUG mode for safety reasons."))
            sys.exit(1)

        if not options["noinput"]:
            confirm = input("""You have requested a database reset.
This will IRREVERSIBLY DESTROY all data currently in the database,
and return each table to an empty state.
Are you sure you want to do this?

    Type 'yes' to continue, or 'no' to cancel: """)

            if confirm != "yes":
                self.stdout.write(self.style.ERROR("Reset cancelled."))
                return

        # Delete migrations if requested
        if options["delete_migrations"]:
            self._delete_migrations()

        # Get all tables
        with connection.cursor() as cursor:
            # Drop all tables
            self.stdout.write("Dropping all tables...")
            cursor.execute("""
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    -- Drop all tables in public schema
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """)

            # Drop all sequences
            self.stdout.write("Dropping all sequences...")
            cursor.execute("""
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    -- Drop all sequences in public schema
                    FOR r IN (SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public') LOOP
                        EXECUTE 'DROP SEQUENCE IF EXISTS public.' || quote_ident(r.sequence_name) || ' CASCADE';
                    END LOOP;
                END $$;
            """)

        if options["delete_migrations"]:
            # Create initial migrations
            self.stdout.write("Creating initial migrations...")
            call_command("makemigrations")

        # Run migrations
        self.stdout.write("Running migrations...")
        call_command("migrate")

        # Create superuser
        self.stdout.write("Creating superuser...")
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if not User.objects.filter(email=options["superuser_email"]).exists():
            User.objects.create_superuser(email=options["superuser_email"], password=options["superuser_password"])

        # Create default storage bucket
        self.stdout.write("Creating default storage bucket...")
        from apps.reggie.models import StorageBucket, StorageProvider

        StorageBucket.objects.get_or_create(
            name="Default Storage",
            bucket_name="bh-reggie-media",
            provider=StorageProvider.GCS,
            is_system=True,
            defaults={
                "region": None,
                "credentials": None,
            },
        )

        # Load all initial data
        self._run_load_commands()

        self.stdout.write(
            self.style.SUCCESS(
                """
Database reset complete! 
Created superuser with:
 - Email: {email}
 - Password: {password}
""".format(email=options["superuser_email"], password=options["superuser_password"])
            )
        )
