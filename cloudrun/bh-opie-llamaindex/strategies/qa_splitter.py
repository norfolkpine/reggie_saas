from llama_index.core.node_parser import TokenTextSplitter, NodeParser
from typing import Any
import re

class QASplitter:
    """
    Splits text based on a Question/Answer format. Each Q&A pair becomes a chunk.
    """
    def split_text(self, text: str) -> list[str]:
        """
        Uses regex to find questions (e.g., starting with "Q:") and splits the
        text so that each chunk contains one question and its corresponding answer.
        """

        # Regex to find question prefixes at the beginning of a line.
        q_pattern = re.compile(r"^\s*(Q:|Question:|\d+\.\s*Q\.)", re.IGNORECASE | re.MULTILINE)

        matches = list(q_pattern.finditer(text))

        if not matches:
            return [text.strip()] if text and text.strip() else []

        chunks = []
        for i in range(len(matches)):
            start_pos = matches[i].start()
            # The end of the chunk is the start of the next question, or the end of the text.
            end_pos = matches[i+1].start() if i + 1 < len(matches) else len(text)
            chunk = text[start_pos:end_pos].strip()
            if chunk:
                chunks.append(chunk)

        return chunks if chunks else [text.strip()]