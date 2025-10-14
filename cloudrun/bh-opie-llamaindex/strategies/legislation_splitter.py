from llama_index.core.node_parser import NodeParser
from typing import Any, Dict
import re
import json
from .base import BaseStrategy


class LegislationSplitter(BaseStrategy):
    """
    Legislation-based splitter for Australian Acts.
    Extracts rich metadata including definitions, sections, thresholds, and structured elements.
    """

    def _extract_act_metadata(self, text: str) -> dict:
        """Extract Act-level metadata from document header."""
        metadata = {}

        # Extract Act name
        act_match = re.search(r'(?:^|\n)([A-Z][A-Za-z\s&\(\)]+(?:Act|Regulations?)\s+\d{4})', text, re.MULTILINE)
        if act_match:
            metadata['act'] = act_match.group(1).strip()

        # Extract compilation number
        comp_no_match = re.search(r'Compilation\s+No\.?\s*(\d+)', text, re.IGNORECASE)
        if comp_no_match:
            metadata['compilation_no'] = int(comp_no_match.group(1))

        # Extract compilation date
        comp_date_match = re.search(r'Compilation\s+date:\s*(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})', text, re.IGNORECASE)
        if comp_date_match:
            metadata['compilation_date'] = self._normalize_date(comp_date_match.group(1))

        # Extract authorised version
        auth_match = re.search(r'(C\d{4}C\d{5})', text)
        if auth_match:
            metadata['authorised_version'] = auth_match.group(1)

        # Extract registered date
        reg_date_match = re.search(r'Registered:\s*(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})', text, re.IGNORECASE)
        if reg_date_match:
            metadata['registered_date'] = self._normalize_date(reg_date_match.group(1))

        return metadata

    def _normalize_date(self, date_str: str) -> str:
        """Convert various date formats to YYYY-MM-DD."""
        # If already in YYYY-MM-DD format
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            return date_str

        # Convert "17 March 2025" to "2025-03-17"
        months = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }

        match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_str, re.IGNORECASE)
        if match:
            day, month, year = match.groups()
            month_num = months.get(month.lower(), '01')
            return f"{year}-{month_num}-{day.zfill(2)}"

        return date_str

    def _extract_section_reference(self, text: str) -> str:
        """Extract section/part/division reference."""
        # Try to match "Part X / Division Y / Section Z" or "Dictionary / s9"
        ref_match = re.search(r'(?:Part\s+\d+[A-Z]?|Dictionary)\s*/\s*(?:Division\s+\d+|s\d+[A-Z]?)', text, re.IGNORECASE)
        if ref_match:
            return ref_match.group(0).strip()

        # Try single section reference
        sec_match = re.search(r'(?:Section|s\.?)\s*(\d+[A-Z]?)', text, re.IGNORECASE)
        if sec_match:
            return f"s{sec_match.group(1)}"

        return ""

    def _identify_term_type(self, text: str) -> str:
        """Identify if chunk is a definition, section, subsection, etc."""
        text_lower = text.lower()

        if 'means' in text_lower or 'definition' in text_lower:
            return 'definition'
        elif re.search(r'\(\d+\)', text):
            return 'subsection'
        elif re.search(r'section\s+\d+', text_lower):
            return 'section'

        return 'content'

    def _extract_term_from_definition(self, text: str) -> str:
        """Extract the term being defined from definition text."""
        # Pattern: "professional investor means" or "**professional investor** means"
        term_match = re.search(r'^\*{0,2}([a-z\s]+?)\*{0,2}\s+means\b', text, re.IGNORECASE | re.MULTILINE)
        if term_match:
            return term_match.group(1).strip()

        return ""

    def _extract_list_letters(self, text: str) -> list[str]:
        """Extract list markers like (a), (b), (c), etc."""
        letters = re.findall(r'\(([a-z])\)', text.lower())
        return sorted(list(set(letters)))

    def _extract_thresholds(self, text: str) -> dict:
        """Extract numerical thresholds and financial amounts from text."""
        thresholds = {}

        # Extract dollar amounts
        dollar_pattern = r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:million|m)?'
        dollar_matches = re.finditer(dollar_pattern, text, re.IGNORECASE)

        for match in dollar_matches:
            amount_str = match.group(1).replace(',', '')
            amount = float(amount_str)

            # Check if it's millions
            if 'million' in match.group(0).lower() or 'm' in match.group(0).lower():
                amount *= 1_000_000

            # Determine context
            context_before = text[max(0, match.start()-50):match.start()].lower()

            if 'net asset' in context_before:
                thresholds['net_assets_aud'] = int(amount)
            elif 'control' in context_before or 'fund' in context_before:
                thresholds['controls_funds_aud'] = int(amount)
            elif 'gross' in context_before:
                thresholds['gross_income_aud'] = int(amount)
            else:
                # Generic threshold
                key = f'amount_{len(thresholds) + 1}_aud'
                thresholds[key] = int(amount)

        # Add currency if any thresholds found
        if thresholds:
            thresholds['currency'] = 'AUD'

        return thresholds

    def _generate_chunk_id(self, act: str, compilation_no: int, term: str, section: str) -> str:
        """Generate a unique ID for the chunk."""
        # Convert act name to abbreviation (e.g., "Corporations Act 2001" -> "corp")
        act_abbrev = ''.join([word[0] for word in act.split() if word[0].isupper()]).lower()

        # Create ID components
        comp = str(compilation_no)

        # Clean term for ID
        term_clean = term.lower().replace(' ', '-') if term else 'section'

        # Clean section reference
        section_clean = section.lower().replace('/', '-').replace(' ', '-') if section else 'unknown'

        return f"{act_abbrev}-{comp}-{section_clean}-{term_clean}"

    def create_splitter(self) -> NodeParser:
        """
        Create and return a NodeParser for legislation text.
        
        Returns:
            A NodeParser instance configured for legislation chunking
        """
        from llama_index.core.node_parser import SimpleNodeParser
        
        # Create a custom node parser that uses our split_text method
        class LegislationNodeParser(SimpleNodeParser):
            def __init__(self, splitter_instance):
                super().__init__()
                self.splitter = splitter_instance
            
            def _split_text(self, text: str) -> list[str]:
                chunks = self.splitter.split_text(text)
                return [chunk['text'] for chunk in chunks]
        
        return LegislationNodeParser(self)

    def split_text(self, text: str) -> list[dict]:
        """
        Splits legislation text into structured chunks with rich metadata.
        Returns list of dictionaries with 'id', 'text', and 'metadata' keys.
        """
        if not text or not text.strip():
            return []

        chunks = []

        # Extract document-level metadata
        doc_metadata = self._extract_act_metadata(text)

        # Split by major sections (definitions, sections, subsections)
        # Pattern for section breaks
        section_pattern = re.compile(
            r'(?:^|\n)(?:'
            r'(?:Section|s\.?)\s*(\d+[A-Z]?)|'  # Section markers
            r'(\([a-z]\))|'  # List items (a), (b), etc.
            r'(?:Part\s+\d+|Dictionary|Schedule\s+\d+)'  # Parts, Dictionary, Schedules
            r')',
            re.MULTILINE | re.IGNORECASE
        )

        # For now, create chunks based on definitions (look for "means" keyword)
        definition_pattern = re.compile(
            r'([a-z\s]+?)\s+means\s+(.+?)(?=\n[a-z\s]+?\s+means|\Z)',
            re.IGNORECASE | re.DOTALL
        )

        for match in definition_pattern.finditer(text):
            term = match.group(1).strip()
            definition_text = match.group(2).strip()

            # Extract metadata for this chunk
            chunk_metadata = doc_metadata.copy()

            # Add chunk-specific metadata
            chunk_metadata['part_division'] = self._extract_section_reference(text[:match.start()])
            chunk_metadata['term'] = term
            chunk_metadata['term_type'] = 'definition'

            # Extract list letters
            letters = self._extract_list_letters(definition_text)
            if letters:
                chunk_metadata['letters'] = letters

            # Extract thresholds
            thresholds = self._extract_thresholds(definition_text)
            if thresholds:
                chunk_metadata['thresholds'] = thresholds

            # Generate chunk ID
            chunk_id = self._generate_chunk_id(
                chunk_metadata.get('act', 'unknown'),
                chunk_metadata.get('compilation_no', 0),
                term,
                chunk_metadata.get('part_division', '')
            )

            # Construct full text for chunk
            full_text = f"{term} means {definition_text}"

            chunks.append({
                'id': chunk_id,
                'text': full_text,
                'metadata': chunk_metadata
            })

        # If no definitions found, create single chunk with all text
        if not chunks:
            chunk_metadata = doc_metadata.copy()
            chunk_metadata['term_type'] = 'content'

            chunks.append({
                'id': f"{doc_metadata.get('act', 'unknown').lower().replace(' ', '-')}-content",
                'text': text.strip(),
                'metadata': chunk_metadata
            })

        return chunks
