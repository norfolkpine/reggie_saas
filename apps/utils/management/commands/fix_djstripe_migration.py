# apps/utils/management/commands/fix_djstripe_migration.py
from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Fix djstripe_bankaccount table for migration'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Check if the table exists
            cursor.execute(
                """
                    ALTER TABLE djstripe_bankaccount ADD COLUMN djstripe_id_new varchar;

                    UPDATE djstripe_bankaccount SET djstripe_id_new = djstripe_id::varchar;

                    SELECT con.conname, pg_get_constraintdef(con.oid)
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                    WHERE rel.relname = 'djstripe_bankaccount'
                    AND con.contype = 'p';

                    ALTER TABLE djstripe_bankaccount DROP COLUMN djstripe_id;
                    ALTER TABLE djstripe_bankaccount RENAME COLUMN djstripe_id_new TO djstripe_id;
                """
            )

        self.stdout.write(self.style.SUCCESS("Fix completed"))