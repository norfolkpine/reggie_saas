import re


def parse_markdown_text(markdown: str) -> tuple[str, list[tuple[str, int, int, str]]]:
    """
    Parses markdown into plain text and styling actions.
    Supports bold (**text**), italic (*text*), bold+italic (***text***), and headings (# ... \n).
    Returns:
        - plain_text: string with markdown syntax stripped
        - actions: list of tuples (style, start_index, end_index, style_type)
    """
    content = markdown
    actions = []

    # First: parse headings line by line
    lines = content.splitlines()
    plain_lines = []
    index = 0

    for line in lines:
        stripped = line.strip()
        style = None
        if stripped.startswith("### "):
            style = "HEADING_3"
            text = stripped[4:]
        elif stripped.startswith("## "):
            style = "HEADING_2"
            text = stripped[3:]
        elif stripped.startswith("# "):
            style = "HEADING_1"
            text = stripped[2:]
        else:
            text = line

        start = index
        plain_lines.append(text)
        end = start + len(text) + 1  # +1 for newline
        if style:
            actions.append(("heading", start, end, style))
        index = end

    content = "\n".join(plain_lines)

    # Inline formatting (bold, italic, bold_italic)
    pattern = re.compile(
        r"(?P<bold_italic>\*\*\*(?!\s)(.+?)(?<!\s)\*\*\*)|"
        r"(?P<bold>\*\*(?!\s)(.+?)(?<!\s)\*\*)|"
        r"(?P<italic>(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*))"
    )

    offset = 0
    matches = list(pattern.finditer(content))

    for match in matches:
        match_str = match.group(0)
        start = content.find(match_str, offset)
        end = start + len(match_str)

        if match.group("bold_italic"):
            inner = match.group("bold_italic")[3:-3]
            content = content[:start] + inner + content[end:]
            actions.append(("bold", start, start + len(inner), None))
            actions.append(("italic", start, start + len(inner), None))
            offset = start + len(inner)
        elif match.group("bold"):
            inner = match.group("bold")[2:-2]
            content = content[:start] + inner + content[end:]
            actions.append(("bold", start, start + len(inner), None))
            offset = start + len(inner)
        elif match.group("italic"):
            inner = match.group("italic")[1:-1]
            content = content[:start] + inner + content[end:]
            actions.append(("italic", start, start + len(inner), None))
            offset = start + len(inner)

    return content, actions


def text_to_google_docs_requests(text: str, actions: list[tuple[str, int, int, str]]) -> list[dict]:
    """
    Converts parsed markdown into Google Docs batchUpdate requests.
    """
    doc_requests = [{"insertText": {"location": {"index": 1}, "text": text}}]

    for style, start, end, style_type in actions:
        if style == "heading":
            doc_requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": start + 1, "endIndex": end + 1},
                        "paragraphStyle": {"namedStyleType": style_type},
                        "fields": "namedStyleType",
                    }
                }
            )
        elif style in ("bold", "italic"):
            doc_requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": start + 1, "endIndex": end + 1},
                        "textStyle": {style: True},
                        "fields": style,
                    }
                }
            )

    return doc_requests
