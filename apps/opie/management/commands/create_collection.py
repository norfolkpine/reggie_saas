from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.opie.models import Collection

User = get_user_model()


class Command(BaseCommand):
    help = "Create collections/folders in the hierarchical structure"

    def add_arguments(self, parser):
        parser.add_argument("--name", type=str, required=True, help="Name of the collection/folder")
        parser.add_argument("--description", type=str, default="", help="Description of the collection/folder")
        parser.add_argument(
            "--type",
            type=str,
            choices=["folder", "regulation", "act", "guideline", "manual"],
            default="folder",
            help="Type of collection (default: folder)",
        )
        parser.add_argument("--parent", type=int, help="ID of the parent collection (leave empty for root)")
        parser.add_argument("--jurisdiction", type=str, help='Jurisdiction (e.g., "Australia", "NSW")')
        parser.add_argument("--regulation-number", type=str, help='Regulation number (e.g., "2001", "No. 123")')
        parser.add_argument("--sort-order", type=int, default=0, help="Sort order within parent (default: 0)")

    def handle(self, *args, **options):
        try:
            # Get parent collection if specified
            parent = None
            if options["parent"]:
                try:
                    parent = Collection.objects.get(id=options["parent"])
                    self.stdout.write(f"📁 Parent: {parent.name}")
                except Collection.DoesNotExist:
                    raise CommandError(f"Parent collection with ID {options['parent']} does not exist")

            # Create the collection
            collection = Collection.objects.create(
                name=options["name"],
                description=options["description"],
                collection_type=options["type"],
                parent=parent,
                jurisdiction=options["jurisdiction"],
                regulation_number=options["regulation_number"],
                sort_order=options["sort_order"],
            )

            # Display the result
            self.stdout.write(self.style.SUCCESS(f"✅ Successfully created collection: {collection.name}"))

            if parent:
                self.stdout.write(f"📂 Full path: {collection.get_full_path()}")
                self.stdout.write(f"📂 Depth: {collection.get_depth()}")
            else:
                self.stdout.write("📂 Root collection created")

        except Exception as e:
            raise CommandError(f"Failed to create collection: {e}")
