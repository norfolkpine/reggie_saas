from django.core.management.base import BaseCommand
from apps.reggie.models import ChunkingStrategy


class Command(BaseCommand):
    help = 'Create default chunking strategies'

    def handle(self, *args, **options):
        strategies = [
            {
                'name': 'Legal Documents - Standard',
                'description': 'Optimized for legal documents with section awareness',
                'strategy_type': 'legal',
                'document_type': 'legal',
                'chunk_size': 300,
                'chunk_overlap': 150,
                'advanced_parameters': {
                    'preserve_sections': True,
                    'table_as_chunk': True,
                    'guide_as_chunk': True,
                    'similarity_cutoff': 0.7
                },
                'is_default': True
            },
            {
                'name': 'Legal Documents - Large Sections',
                'description': 'For legal documents with large sections that need to stay together',
                'strategy_type': 'legal',
                'document_type': 'legal',
                'chunk_size': 500,
                'chunk_overlap': 200,
                'advanced_parameters': {
                    'preserve_sections': True,
                    'table_as_chunk': True,
                    'guide_as_chunk': True,
                    'similarity_cutoff': 0.8
                }
            },
            {
                'name': 'Vault Documents - Mixed Content',
                'description': 'Auto-detects document type and applies appropriate chunking',
                'strategy_type': 'vault',
                'document_type': 'mixed',
                'chunk_size': 500,
                'chunk_overlap': 100,
                'advanced_parameters': {
                    'auto_detect_type': True,
                    'fallback_strategy': 'token',
                    'similarity_cutoff': 0.6
                }
            },
            {
                'name': 'Vault Documents - Legal Focus',
                'description': 'For vault files that are primarily legal documents',
                'strategy_type': 'vault',
                'document_type': 'legal',
                'chunk_size': 400,
                'chunk_overlap': 150,
                'advanced_parameters': {
                    'legal_patterns': True,
                    'preserve_sections': True,
                    'similarity_cutoff': 0.7
                }
            },
            {
                'name': 'Semantic Chunking - High Precision',
                'description': 'Uses embedding similarity for precise chunk boundaries',
                'strategy_type': 'semantic',
                'document_type': 'general',
                'chunk_size': 400,
                'chunk_overlap': 100,
                'advanced_parameters': {
                    'buffer_size': 1,
                    'breakpoint_percentile_threshold': 95,
                    'include_metadata': True,
                    'include_prev_next_rel': True
                }
            },
            {
                'name': 'Hierarchical Chunking - Multi-level',
                'description': 'Creates parent-child chunk relationships',
                'strategy_type': 'hierarchical',
                'document_type': 'general',
                'chunk_size': 600,
                'chunk_overlap': 150,
                'advanced_parameters': {
                    'parent_chunk_size': 600,
                    'child_chunk_size': 300,
                    'include_metadata': True,
                    'include_prev_next_rel': True
                }
            },
            {
                'name': 'Token-based - Simple',
                'description': 'Simple token-based chunking for basic documents',
                'strategy_type': 'token',
                'document_type': 'general',
                'chunk_size': 1000,
                'chunk_overlap': 200,
                'advanced_parameters': {
                    'separator': '\\n\\n',
                    'secondary_chunking_regex': '[.!?]\\s+',
                    'chunk_overlap_ratio': 0.2
                }
            },
            {
                'name': 'Agentic Chunking - AI-Powered',
                'description': 'Uses AI to identify optimal chunk boundaries',
                'strategy_type': 'agentic',
                'document_type': 'mixed',
                'chunk_size': 400,
                'chunk_overlap': 120,
                'advanced_parameters': {
                    'ai_boundary_detection': True,
                    'context_preservation': True,
                    'similarity_cutoff': 0.7,
                    'smart_overlap': True
                }
            }
        ]

        created_count = 0
        for strategy_data in strategies:
            strategy, created = ChunkingStrategy.objects.get_or_create(
                name=strategy_data['name'],
                defaults=strategy_data
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created strategy: {strategy.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Strategy already exists: {strategy.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} new chunking strategies')
        )
