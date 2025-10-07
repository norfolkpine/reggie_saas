Comprehensive list of environment variables for Nango:

**Server & URLs:**
- `NANGO_SERVER_URL` - Instance URL
- `SERVER_PORT` - Port number
- `NANGO_PUBLIC_CONNECT_URL` - Custom domain for Connect UI
- `NANGO_HOSTPORT` - For self-hosting (default: https://api.nango.dev)

**Database:**
- `NANGO_DB_USER`, `NANGO_DB_PASSWORD`, `NANGO_DB_HOST`, `NANGO_DB_PORT`, `NANGO_DB_NAME`, `NANGO_DB_SSL`
- `NANGO_DATABASE_URL` - Alternative connection string format
- `RECORDS_DATABASE_URL` - Separate database for sync records

**Security:**
- `NANGO_ENCRYPTION_KEY` - 256-bit base64 key for encrypting sensitive data
- `FLAG_AUTH_ENABLED` - Disable regular login/signup
- `NANGO_DASHBOARD_USERNAME`, `NANGO_DASHBOARD_PASSWORD` - Basic Auth for dashboard

**Connect UI:**
- `FLAG_SERVE_CONNECT_UI` - Enable Connect UI (default: true)
- `NANGO_CONNECT_UI_PORT` - Port for Connect UI (default: 3009)

**Logs:**
- `NANGO_LOGS_ENABLED` - Enable Elasticsearch logs
- `NANGO_LOGS_ES_*` - Elasticsearch configuration

**Other:**
- `NANGO_SERVER_WEBSOCKETS_PATH` - Custom websockets path
- `TELEMETRY` - Enable/disable telemetry (default: true)
- `NANGO_CLI_UPGRADE_MODE` - CLI upgrade handling
- `NANGO_DEPLOY_AUTO_CONFIRM` - Auto-confirm deployments
- `NANGO_SECRET_KEY_DEV`, `NANGO_SECRET_KEY_PROD` - CLI authentication

Want to learn more? This page may help:
```suggestions
(Free self-hosting - Configuration)[/guides/self-hosting/free-self-hosting/configuration]
```