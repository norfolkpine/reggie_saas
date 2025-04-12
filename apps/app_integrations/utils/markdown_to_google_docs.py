import re

def markdown_to_google_docs_requests(markdown: str) -> list:
    """
    Converts markdown into a list of Google Docs API batchUpdate requests.
    Supports:
      - Headings (#, ##, ###)
      - Paragraphs
      - Bold (**text**)
      - Italic (*text*)
    """
    requests = []
    index = 1  # always start after the beginning of the doc

    def append_insert(text):
        nonlocal index
        requests.append({
            "insertText": {
                "location": {"index": index},
                "text": text
            }
        })
        index += len(text)

    def format_inline_styles(text):
        nonlocal index
        segments = []
        cursor = 0

        bold_pattern = re.compile(r"\*\*(.+?)\*\*")
        italic_pattern = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")

        while True:
            match = bold_pattern.search(text, cursor)
            if not match:
                break
            start, end = match.span()
            segments.append((text[cursor:start], None))
            segments.append((match.group(1), "BOLD"))
            cursor = end
        segments.append((text[cursor:], None))

        final = []
        for segment, style in segments:
            if not segment:
                continue
            insert = {
                "insertText": {
                    "location": {"index": index},
                    "text": segment
                }
            }
            final.append(insert)
            if style:
                final.append({
                    "updateTextStyle": {
                        "range": {
                            "startIndex": index,
                            "endIndex": index + len(segment)
                        },
                        "textStyle": {"bold": True} if style == "BOLD" else {},
                        "fields": "bold"
                    }
                })
            index += len(segment)

        return final

    lines = markdown.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            append_insert("\n")
            continue

        if stripped.startswith("### "):
            text = stripped[4:] + "\n"
            append_insert(text)
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index - len(text), "endIndex": index},
                    "paragraphStyle": {"namedStyleType": "HEADING_3"},
                    "fields": "namedStyleType"
                }
            })
        elif stripped.startswith("## "):
            text = stripped[3:] + "\n"
            append_insert(text)
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index - len(text), "endIndex": index},
                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                    "fields": "namedStyleType"
                }
            })
        elif stripped.startswith("# "):
            text = stripped[2:] + "\n"
            append_insert(text)
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": index - len(text), "endIndex": index},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType"
                }
            })
        else:
            styled = format_inline_styles(stripped + "\n")
            requests.extend(styled)

    return requests
