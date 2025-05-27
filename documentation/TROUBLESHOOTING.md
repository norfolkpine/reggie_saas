# Troubleshooting

## Django API Key Validation Failed: All connection attempts failed

**Symptom:**
```
WARNING: ⚠️ Django API key validation failed: All connection attempts failed
```

This warning means the ingester container could not connect to your Django backend at the address specified by `DJANGO_API_URL`.

### Causes
- The ingester is running in Docker and cannot reach Django at `localhost:8000` because `localhost` refers to the container itself, not your host machine.
- Django is not running, or is not accessible at the expected address/port.

### Solutions

#### If Django is running on your host machine (not in Docker):
- Change `DJANGO_API_URL` in your `.env` to:
  ```
  DJANGO_API_URL=http://host.docker.internal:8000
  ```
  This special hostname allows Docker containers to access services running on your host (works on Mac and Windows).
- Restart your ingester container after updating the `.env`.

#### If Django is running in Docker Compose:
- Use the service name as the host (e.g., `django` if your service is named `django` in your Compose file):
  ```
  DJANGO_API_URL=http://django:8000
  ```
- Make sure both containers are on the same Docker network (default in Compose).

#### Double-check
- Ensure Django is actually running and accessible at the expected address/port.
- Make sure your `.env` does not have extra quotes around the API key (use `DJANGO_API_KEY=your-key`, not `"your-key"`, unless your code requires it).

---

If you continue to see this error after following these steps, verify your network settings and that there are no firewall or port conflicts blocking access between the ingester and Django backend.
