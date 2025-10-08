You get the **Atlassian client ID and client secret** from the [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/). Here’s the step-by-step:

1. **Go to the Developer Console**
   Log in with the Atlassian account you’ll use for development:
   👉 [https://developer.atlassian.com/console/myapps/](https://developer.atlassian.com/console/myapps/)

2. **Create a new app**

   * Click **Create** → **OAuth 2.0 integration** (for cloud apps that need API access).
   * Give it a name and select the product scopes (e.g., Jira, Confluence, etc.) you want to use.

3. **Find the credentials**

   * Once created, open the app.
   * Under **Authorization** → **OAuth 2.0 (3LO)**, you’ll see:

     * **Client ID** (public identifier for your app)
     * **Client Secret** (keep this private — used when exchanging auth codes for tokens).

4. **Redirect URI setup**

   * You’ll need to add your app’s redirect/callback URL in the configuration.
   * Example for local dev: `http://localhost:8000/callback`
   * For production: `https://yourapp.com/oauth/callback`

5. **Use in your app**

   * In your Django or other backend, set `CLIENT_ID` and `CLIENT_SECRET` as environment variables.
   * Use them in your OAuth flow when exchanging the authorization code for an access token.

⚠️ Note: If you're building a **Forge app**, the process is different — Forge apps don't expose a client secret since they run inside Atlassian's infrastructure.

## Scopes

When setting up your OAuth 2.0 integration, you'll need to configure the appropriate scopes for the Atlassian APIs you want to use.

### Confluence Scopes

For Confluence integration, use these scopes:
- `write:confluence-content` - Write Confluence content
- `read:confluence-space.summary` - Read Confluence space summaries
- `write:confluence-file` - Write Confluence files
- `write:confluence-space` - Write Confluence spaces
- `read:confluence-props` - Read Confluence properties
- `write:confluence-props` - Write Confluence properties
- `read:confluence-content.all` - Read all Confluence content
- `read:confluence-content.summary` - Read Confluence content summaries
- `readonly:content.attachment:confluence` - Read Confluence attachments
- `read:confluence-user` - Read Confluence user information
- `search:confluence` - Search Confluence content

```
write:confluence-content,read:confluence-space.summary,write:confluence-file,write:confluence-space,read:confluence-props,write:confluence-props,read:confluence-content.all,read:confluence-content.summary,readonly:content.attachment:confluence,read:confluence-user,search:confluence
```

**Example Confluence OAuth URL:**
```
https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id=YOUR_CLIENT_ID&scope=write%3Aconfluence-content%20read%3Aconfluence-space.summary%20write%3Aconfluence-file%20write%3Aconfluence-space%20read%3Aconfluence-props%20write%3Aconfluence-props%20read%3Aconfluence-content.all%20read%3Aconfluence-content.summary%20readonly%3Acontent.attachment%3Aconfluence%20read%3Aconfluence-user%20search%3Aconfluence&redirect_uri=https%3A%2F%2Fnango.opie.sh%2Foauth%2Fcallback&state=${YOUR_USER_BOUND_VALUE}&response_type=code&prompt=consent
```

### Jira Scopes

For Jira integration, use these scopes:
- `read:jira-work` - Read Jira issues and work items
- `manage:jira-project` - Manage Jira projects
- `read:jira-user` - Read Jira user information
- `write:jira-work` - Create and update Jira issues

```
read:jira-work,manage:jira-project,read:jira-user,write:jira-work
```

**Example Jira OAuth URL:**
```
https://auth.atlassian.com/authorize?audience=api.atlassian.com&client_id=YOUR_CLIENT_ID&scope=read%3Ajira-work%20manage%3Ajira-project%20read%3Ajira-user%20write%3Ajira-work&redirect_uri=https%3A%2F%2Fnango.opie.sh%2Foauth%2Fcallback&state=${YOUR_USER_BOUND_VALUE}&response_type=code&prompt=consent
```

### Ready-to-use Django settings snippet

```python
# Add to your settings.py or environment configuration
ATLASSIAN_CLIENT_ID = "your_client_id_from_atlassian_console"
ATLASSIAN_CLIENT_SECRET = "your_client_secret_from_atlassian_console"
ATLASSIAN_REDIRECT_URI = "https://nango.opie.sh/oauth/callback"

# For direct Jira API access (alternative to OAuth)
JIRA_SERVER_URL = "https://your-domain.atlassian.net"
JIRA_USERNAME = "your-email@domain.com"
JIRA_API_TOKEN = "your_jira_api_token"  # Generate from https://id.atlassian.com/manage-profile/security/api-tokens
```
