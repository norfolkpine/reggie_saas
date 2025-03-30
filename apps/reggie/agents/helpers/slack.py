from slack_sdk.web import WebClient
from reggie.models import SlackWorkspace

def get_workspace_by_team_id(slack_team_id: str) -> SlackWorkspace | None:
    """
    Fetch the SlackWorkspace instance for a given Slack team ID.
    
    Args:
        slack_team_id (str): The Slack-provided team ID (e.g. 'T123ABC456').
    
    Returns:
        SlackWorkspace or None
    """
    try:
        return SlackWorkspace.objects.get(slack_team_id=slack_team_id)
    except SlackWorkspace.DoesNotExist:
        return None


def get_web_client(slack_team_id: str) -> WebClient | None:
    """
    Get a Slack WebClient initialized with the bot token for a workspace.
    
    Args:
        slack_team_id (str): The Slack-provided team ID.

    Returns:
        slack_sdk.WebClient or None
    """
    workspace = get_workspace_by_team_id(slack_team_id)
    if not workspace:
        return None
    return WebClient(token=workspace.access_token)


def get_saas_team(slack_team_id: str):
    """
    Get the SaaS 'Team' instance linked to the Slack workspace.

    Args:
        slack_team_id (str): The Slack-provided team ID.

    Returns:
        teams.Team or None
    """
    workspace = get_workspace_by_team_id(slack_team_id)
    return workspace.team if workspace else None


def has_valid_subscription(slack_team_id: str) -> bool:
    """
    Check if the Slack workspace is linked to a SaaS tenant with an active subscription.

    Args:
        slack_team_id (str): The Slack-provided team ID.

    Returns:
        bool: True if the linked team has an active subscription.
    """
    workspace = get_workspace_by_team_id(slack_team_id)
    if not workspace:
        return False

    team = workspace.team
    return team.subscriptions.filter(status="active").exists()
