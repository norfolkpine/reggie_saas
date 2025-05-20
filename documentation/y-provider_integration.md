# Integrating Django Backend with y-provider Microservice

This guide explains how to securely connect your Django backend to the y-provider microservice for collaborative document features.

---

## 1. Set a Shared Secret

- Choose a secret value (e.g., `my-secret`).
- Add it to both your Django backend and y-provider environments.

**In your `.env` files:**
```env
COLLABORATION_SERVER_SECRET=my-secret
```

---

## 2. Django Backend Setup

- Ensure your `settings.py` loads the secret:
  ```python
  COLLABORATION_SERVER_SECRET = env("COLLABORATION_SERVER_SECRET", default="my-secret")
  ```
- When making requests to y-provider, set the `Authorization` header to this secret.

---

## 3. y-provider Setup

- The y-provider service must also load `COLLABORATION_SERVER_SECRET` from its environment.
- It will check incoming requests for the `Authorization` header and compare it to this value.

---

## 4. CORS & Origins

- Set `COLLABORATION_SERVER_ORIGIN` in both `.env` files to allow requests from your frontend and backend domains.
  ```env
  COLLABORATION_SERVER_ORIGIN=http://localhost:3000
  ```

---

## 5. Restart Services

- After updating secrets, restart both services to apply changes.

---

## 6. Test the Integration

- Make a request from Django to y-provider (e.g., markdown conversion or collaboration endpoint).
- If the connection fails with `403 Forbidden: Invalid API Key`, check that the secrets match and the `Authorization` header is set.

---

## 7. Troubleshooting

- Check logs in both services for errors.
- Make sure both services use the same secret and that the header is not using a Bearer token format (just the raw secret).

---

## Example Table

| Setting                    | Django Backend (.env) | y-provider (.env)      |
|----------------------------|----------------------|------------------------|
| COLLABORATION_SERVER_SECRET| my-secret            | my-secret              |
| COLLABORATION_SERVER_ORIGIN| http://localhost:3000| http://localhost:3000  |

---

## Example Complete .env for y-provider

```env
# Collaboration Settings
COLLABORATION_API_URL=http://localhost:4444/collaboration/api/
COLLABORATION_BACKEND_BASE_URL=http://localhost:8000
COLLABORATION_SERVER_ORIGIN=http://localhost:3000
COLLABORATION_SERVER_SECRET=my-secret
COLLABORATION_WS_URL=ws://localhost:4444/collaboration/ws/
Y_PROVIDER_API_KEY=my-secret

# Optional
PORT=4444
COLLABORATION_LOGGING=true
SENTRY_DSN=
```

---

## Testing y-provider

After starting the y-provider service, you can verify it's working as expected with the following tests:

### 1. Health Check: `/ping` Endpoint

```sh
curl -i http://localhost:4444/ping
```
**Expected response:**
```
HTTP/1.1 200 OK
{"message":"pong"}
```

### 2. Authenticated Endpoint: `/api/convert-markdown/`

```sh
curl -i -X POST http://localhost:4444/api/convert-markdown/ \
  -H 'Authorization: my-secret' \
  -H 'Content-Type: application/json' \
  -d '{"content": "# Hello world"}'
```
**Expected response:**
- `200 OK` with a JSON object containing a `content` field (base64 encoded).

### 3. Invalid API Key

```sh
curl -i -X POST http://localhost:4444/api/convert-markdown/ \
  -H 'Authorization: wrong-key' \
  -H 'Content-Type: application/json' \
  -d '{"content": "# Hello world"}'
```
**Expected response:**
```
HTTP/1.1 403 Forbidden
{"error":"Forbidden: Invalid API Key"}
```

### 4. Check Logs
- If you set `COLLABORATION_LOGGING=true`, check your terminal for log output when you hit the endpoints.

---

For more details or advanced configuration, see the comments in your `settings.py` and y-provider's environment setup.
