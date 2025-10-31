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


def add_tag_groups(result, generator, request, public):
    """
    Postprocessing hook to add x-tagGroups for better grouping in GitBook.
    Does not change per-operation tags; only adds grouping metadata.
    """
    tag_groups = [
        {
            "name": "Core",
            "tags": [
                "auth",
                "users",
                "teams",
                "Health",
            ],
        },
        {
            "name": "Content",
            "tags": [
                "Files",
                "Collections",
                "Documents",
                "File Tags",
                "Tags",
                "Knowledge Bases",
                "Projects",
            ],
        },
        {
            "name": "Agents",
            "tags": [
                "Agents",
                "Agent Templates",
                "Agent Instructions",
                "Agent Expected Output",
                "Agent Model Providers",
                "Token Usage",
                "User Feedback",
                "Categories",
                "Chat Sessions",
                "Opie AI",
            ],
        },
        {
            "name": "Integrations",
            "tags": [
                "integrations",
                "App Integrations",
                "Google Drive",
                "subscriptions",
            ],
        },
    ]

    # Inject x-tagGroups (GitBook understands this vendor extension)
    result.setdefault("x-tagGroups", tag_groups)
    return result
