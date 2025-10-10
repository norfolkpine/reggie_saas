from django.core.management.base import BaseCommand
from apps.opie.models import ChunkingStrategy

class Command(BaseCommand):
    def handle(self, *args, **options):
        strategies = [
            {
                "name": "Default",
                "strategy_id": "default",
                "description": "default chunking strategy.",
                "strategy_config": {"chunk_size": 1000, "chunk_overlap": 200},
            },
            {
                "name": "Paper",
                "strategy_id": "paper",
                "description": "paper chunking strategy.",
                "strategy_config": {},
            },
            {
                "name": "QA",
                "strategy_id": "qa",
                "description": "qa chunking strategy.",
                "strategy_config": {},
            },
            {
                "name": "Presentation",
                "strategy_id": "presentation",
                "description": "presentation chunking strategy.",
                "strategy_config": {},
            },
            {
                "name": "Custom",
                "strategy_id": "custom",
                "description": "custom chunking strategy.",
                "strategy_config": {"chunk_size": 1000, "chunk_overlap": 200},
            }
        ]

        created, updated = 0, 0

        for strategy in strategies:
            obj, was_created = ChunkingStrategy.objects.update_or_create(
                name=strategy["name"],
                defaults={
                    "strategy_id": strategy["strategy_id"],
                    "description": strategy["description"],
                    "strategy_config": strategy["strategy_config"],
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(f"✅ Insert complete. Created: {created}, Updated: {updated}")