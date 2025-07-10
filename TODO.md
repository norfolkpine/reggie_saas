- [ ] Review `agno.agent.Agent` reference attachment logic to ensure only correct and relevant references are included in responses. If necessary, add a post-processing step in the consumer to filter out irrelevant references before sending to the frontend. 
- [ ] Add a `.jira/config.yml` file to the repository with the necessary Jira credentials/configuration for the `atlassian/gajira-find-issue-key` GitHub Action to work. Ensure the file contains your Jira site URL, email, and API token (use GitHub secrets for sensitive values). Example:
  ```yaml
  site: https://your-domain.atlassian.net
  email: ${{ secrets.JIRA_EMAIL }}
  apiToken: ${{ secrets.JIRA_API_TOKEN }}
  ```
  Also, add the required secrets (`JIRA_EMAIL`, `JIRA_API_TOKEN`) to your GitHub repository. 