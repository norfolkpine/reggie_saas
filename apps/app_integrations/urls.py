# app_integrations/urls.py
from django.urls import path

from .views.google_drive import (
    create_google_doc_from_markdown,
    download_file_from_google_drive,
    google_oauth_callback,
    google_oauth_start,
    list_google_drive_files,
    revoke_google_drive_access,
    upload_file_to_google_drive,
)
from .views.views import list_supported_apps

from .views.nango import (
    get_nango_session,
    save_nango_session,
    list_connected_integrations,
    revoke_nango_connection,
    delete_nango_integration,
    get_nango_integrations,
    test_nango_connection
)

from .views.nango_google_drive import (
    list_google_drive_files,
    download_from_google_drive,
    upload_to_google_drive
)

from .views.nango_gmail import (
    gmail_create_draft,
    gmail_draft_send,
    list_draft_mail,
    get_draft_mail,
    update_draft_mail,
    delete_draft_mail
)

from .views.nango_slack import (
    slack_users_list,
    get_slack_user,
    post_slack_message,
    update_slack_message,
    delete_slack_message
)

from .views.nango_jira import (
    list_jira_user,
    create_jira_issue
)

urlpatterns = [
    path("gdrive/oauth/start/", google_oauth_start, name="google_oauth_start"),
    path("gdrive/oauth/callback/", google_oauth_callback, name="google_oauth_callback"),
    path("gdrive/revoke/", revoke_google_drive_access, name="gdrive_revoke"),
    path("gdrive/files/", list_google_drive_files, name="google_drive_files"),
    path("gdrive/upload/", upload_file_to_google_drive, name="gdrive_upload"),
    path("gdrive/download/<str:file_id>/", download_file_from_google_drive, name="gdrive_download"),
    path("gdrive/docs/markdown/", create_google_doc_from_markdown, name="gdrive_docs_from_markdown"),
    path("apps/", list_supported_apps, name="list-supported-apps"),
    path("connections/", list_connected_integrations, name="list_connected_integrations"),
    path("integrations/", get_nango_integrations, name="get_nango_integrations"),
    path("nangosession/", get_nango_session, name = "get_nango_session"),
    path("test-nango/", test_nango_connection, name = "test_nango_connection"),
    path("connectionsave/", save_nango_session, name = "save_nango_session"),
    path("revokesession/", revoke_nango_connection, name="revoke_nango_connection"),
    path("nango/delete/", delete_nango_integration, name="delete_nango_integration"),
    path("nango/gdrive/files/", list_google_drive_files, name="list_google_drive_files"),
    path("nango/gdrive/downloadfiles/", download_from_google_drive, name="list_google_drive_files"),
    path("nango/gdrive/uploadfiles/", upload_to_google_drive, name="list_google_drive_files"),
    path("nango/gmail/createdraft/", gmail_create_draft, name="gmail_create_draft"),
    path("nango/gmail/draftsend/", gmail_draft_send, name="gmail_draft_send"),
    path("nango/gmail/listdraft/", list_draft_mail, name="list_draft_mail"),
    path("nango/gmail/getonedraft/", get_draft_mail, name="get_draft_mail"),
    path("nango/gmail/updatedraft/", update_draft_mail, name="update_draft_mail"),
    path("nango/gmail/deletedraft/", delete_draft_mail, name="delete_draft_mail"),
    path("nango/slack/userlist/", slack_users_list, name="slack_users_list"),
    path("nango/slack/getuser/", get_slack_user, name="get_slack_user"),
    path("nango/slack/postmessage/", post_slack_message, name="post_slack_message"),
    path("nango/slack/updatemessage/", update_slack_message, name="update_slack_message"),
    path("nango/slack/deletemessage/", delete_slack_message, name="delete_slack_message"),
    path("nango/jira/userlist/", list_jira_user, name="list_jira_user"),
    path("nango/jira/createissue/", create_jira_issue, name="create_jira_issue"),
]
