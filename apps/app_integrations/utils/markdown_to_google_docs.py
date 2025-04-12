def markdown_to_google_docs_requests(markdown: str) -> list:
    """
    Converts markdown into a list of Google Docs API batchUpdate requests.
    Outputs only unformatted plain text paragraphs.
    """
    requests = []
    index = 1  # start after the beginning of the document

    def append_insert(text):
        nonlocal index
        requests.append({
            "insertText": {
                "location": {"index": index},
                "text": text
            }
        })
        index += len(text)

    lines = markdown.splitlines()
    for line in lines:
        stripped = line.strip()
        append_insert(stripped + "\n")

    return requests
