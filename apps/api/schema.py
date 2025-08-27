def filter_schema_apis(endpoints):
    """
    Used to filter out certain API endpoints from the auto-generated docs / clients
    """
    return [e for e in endpoints if include_in_schema(e)]


def include_in_schema(endpoint):
    url_path = endpoint[0]
    return not url_path.startswith("/cms/") and not url_path.startswith(
        "/docs/api/v1/cms/"
    )  # filter out wagtail URLs if present
