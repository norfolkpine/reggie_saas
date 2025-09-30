import logging
import os
from typing import List, Optional, Dict, Any

from agno.tools import Toolkit
import langextract as lx
from django.conf import settings

logger = logging.getLogger(__name__)


class VaultLangExtractTools(Toolkit):

    def __init__(
        self,
        project_id: str,
        user,
        folder_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        model_id: str = "gpt-4o",
        api_key: Optional[str] = None,
        fence_output: bool = False,
        use_schema_constraints: bool = True,
    ):
        super().__init__(name="vault_langextract_tools")

        self.project_id = project_id
        self.user = user
        self.folder_id = folder_id
        self.file_ids = file_ids or []
        self.model_id = model_id
        self.fence_output = fence_output
        self.use_schema_constraints = use_schema_constraints

        self.api_key = (
            api_key
            or getattr(settings, "GOOGLE_API_KEY", None)
            or getattr(settings, "OPENAI_API_KEY", None)
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

        self.register(self.extract_entities_from_vault)
        self.register(self.extract_structured_data_from_vault)
        self.register(self.extract_key_information_from_vault)
        self.register(self.extract_custom_from_vault)

    def _get_vault_file_content(self, file_id: str) -> Optional[str]:

        try:
            from apps.vault.models import VaultFile

            vault_file = VaultFile.objects.get(
                uuid=file_id,
                project__uuid=self.project_id,
                user__uuid=self.user.uuid,
            )

            if hasattr(vault_file, 'file') and vault_file.file:
                content = vault_file.file.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8', errors='replace')
                return content
            elif hasattr(vault_file, 'content'):
                return vault_file.content
            else:
                logger.warning(f"Could not read content from vault file {file_id}")
                return None

        except Exception as e:
            logger.error(f"Error reading vault file {file_id}: {e}")
            return None

    def extract_entities_from_vault(
        self,
        file_id: str,
        entity_types: List[str],
        custom_prompt: Optional[str] = None,
        max_length: int = 50000
    ) -> str:

        try:
            content = self._get_vault_file_content(file_id)
            if not content:
                return f"Error: Could not read vault file {file_id}"

            if len(content) > max_length:
                content = content[:max_length]
                logger.warning(f"Truncated content from {len(content)} to {max_length} chars")

            entity_list = ", ".join(entity_types)
            prompt = custom_prompt or f"""
            Extract {entity_list} from the document.
            Use exact text from the source. Do not paraphrase.
            Provide meaningful attributes when relevant.
            """

            examples = [
                lx.data.ExampleData(
                    text="On January 15, 2024, John Smith from Microsoft announced a partnership.",
                    extractions=[
                        lx.data.Extraction(extraction_class="date", extraction_text="January 15, 2024"),
                        lx.data.Extraction(extraction_class="person", extraction_text="John Smith"),
                        lx.data.Extraction(extraction_class="organization", extraction_text="Microsoft"),
                    ]
                )
            ]

            result = lx.extract(
                text_or_documents=content,
                prompt_description=prompt,
                examples=examples,
                model_id=self.model_id,
                api_key=self.api_key,
                fence_output=self.fence_output,
                use_schema_constraints=self.use_schema_constraints
            )

            grouped = {}
            for extraction in result.extractions:
                entity_type = extraction.extraction_class
                if entity_type not in grouped:
                    grouped[entity_type] = []

                grouped[entity_type].append({
                    "text": extraction.extraction_text,
                    "start": extraction.start_char_offset,
                    "end": extraction.end_char_offset,
                    "attributes": getattr(extraction, 'attributes', {})
                })

            import json
            return json.dumps({
                "file_id": file_id,
                "total_extractions": len(result.extractions),
                "entities_by_type": grouped
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Error extracting entities from vault file {file_id}: {e}")
            return f"Error extracting entities: {str(e)}"

    def extract_structured_data_from_vault(
        self,
        file_id: str,
        data_structure: str,
        example_text: str,
        example_extractions: List[Dict[str, Any]],
        max_length: int = 50000
    ) -> str:

        try:
            content = self._get_vault_file_content(file_id)
            if not content:
                return f"Error: Could not read vault file {file_id}"

            if len(content) > max_length:
                content = content[:max_length]

            examples = [
                lx.data.ExampleData(
                    text=example_text,
                    extractions=[
                        lx.data.Extraction(
                            extraction_class=ex.get("class", "entity"),
                            extraction_text=ex.get("text", ""),
                            attributes=ex.get("attributes", {})
                        )
                        for ex in example_extractions
                    ]
                )
            ]

            result = lx.extract(
                text_or_documents=content,
                prompt_description=data_structure,
                examples=examples,
                model_id=self.model_id,
                api_key=self.api_key,
                fence_output=self.fence_output,
                use_schema_constraints=self.use_schema_constraints
            )

            structured_data = []
            for extraction in result.extractions:
                structured_data.append({
                    "type": extraction.extraction_class,
                    "value": extraction.extraction_text,
                    "position": [extraction.start_char_offset, extraction.end_char_offset],
                    "metadata": getattr(extraction, 'attributes', {})
                })

            import json
            return json.dumps({
                "file_id": file_id,
                "structure": data_structure,
                "total_items": len(structured_data),
                "data": structured_data
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Error extracting structured data: {e}")
            return f"Error: {str(e)}"

    def extract_key_information_from_vault(
        self,
        file_id: str,
        information_types: List[str],
        max_length: int = 50000
    ) -> str:

        try:
            content = self._get_vault_file_content(file_id)
            if not content:
                return f"Error: Could not read vault file {file_id}"

            if len(content) > max_length:
                content = content[:max_length]

            info_list = ", ".join(information_types)
            prompt = f"Extract {info_list} from the document. Use exact text."

            example_extractions = []
            example_text = "On January 15, 2024, John Doe paid $1,500 to ABC Corp in New York."

            type_examples = {
                "date": lx.data.Extraction(extraction_class="date", extraction_text="January 15, 2024"),
                "person": lx.data.Extraction(extraction_class="person", extraction_text="John Doe"),
                "amount": lx.data.Extraction(extraction_class="amount", extraction_text="$1,500"),
                "organization": lx.data.Extraction(extraction_class="organization", extraction_text="ABC Corp"),
                "location": lx.data.Extraction(extraction_class="location", extraction_text="New York"),
            }

            for info_type in information_types:
                if info_type.lower() in type_examples:
                    example_extractions.append(type_examples[info_type.lower()])

            examples = [lx.data.ExampleData(text=example_text, extractions=example_extractions)]

            result = lx.extract(
                text_or_documents=content,
                prompt_description=prompt,
                examples=examples,
                model_id=self.model_id,
                api_key=self.api_key,
                fence_output=self.fence_output,
                use_schema_constraints=self.use_schema_constraints
            )

            by_type = {}
            for extraction in result.extractions:
                info_type = extraction.extraction_class
                if info_type not in by_type:
                    by_type[info_type] = []

                by_type[info_type].append({
                    "text": extraction.extraction_text,
                    "position": [extraction.start_char_offset, extraction.end_char_offset]
                })

            import json
            return json.dumps({
                "file_id": file_id,
                "total_extractions": len(result.extractions),
                "information_by_type": by_type
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Error extracting key information: {e}")
            return f"Error: {str(e)}"

    def extract_custom_from_vault(
        self,
        file_id: str,
        prompt_description: str,
        example_text: str,
        example_extractions: List[Dict[str, Any]],
        max_length: int = 50000
    ) -> str:

        try:
            content = self._get_vault_file_content(file_id)
            if not content:
                return f"Error: Could not read vault file {file_id}"

            if len(content) > max_length:
                content = content[:max_length]

            examples = [
                lx.data.ExampleData(
                    text=example_text,
                    extractions=[
                        lx.data.Extraction(
                            extraction_class=ex.get("class", "entity"),
                            extraction_text=ex.get("text", ""),
                            attributes=ex.get("attributes", {})
                        )
                        for ex in example_extractions
                    ]
                )
            ]

            result = lx.extract(
                text_or_documents=content,
                prompt_description=prompt_description,
                examples=examples,
                model_id=self.model_id,
                api_key=self.api_key,
                fence_output=self.fence_output,
                use_schema_constraints=self.use_schema_constraints
            )

            extractions = []
            for extraction in result.extractions:
                extractions.append({
                    "class": extraction.extraction_class,
                    "text": extraction.extraction_text,
                    "start": extraction.start_char_offset,
                    "end": extraction.end_char_offset,
                    "attributes": getattr(extraction, 'attributes', {})
                })

            import json
            return json.dumps({
                "file_id": file_id,
                "prompt": prompt_description,
                "total_extractions": len(extractions),
                "extractions": extractions
            }, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Error in custom extraction: {e}")
            return f"Error: {str(e)}"