# How y-provider Connects to the Django Backend

## 1. Backend URL Configuration
- The environment variable `COLLABORATION_BACKEND_BASE_URL` (e.g. `http://localhost:8000`) tells y-provider where your Django backend API is located.

## 2. How y-provider Makes Requests to Django
- y-provider uses the `axios` library to make HTTP requests to Django endpoints.
- Example endpoints it calls on Django:
  - `/api/v1.0/users/me/` (to get user info)
  - `/api/v1.0/documents/<documentName>/` (to get document data)

**Example from the code:**
```typescript
const response = await axios.get<User>(
  `${COLLABORATION_BACKEND_BASE_URL}/api/v1.0/users/me/`,
  {
    headers: {
      Cookie: requestHeaders['cookie'],
      Origin: requestHeaders['origin'],
    },
  }
);
```
- This forwards the user's cookies and origin, so Django can authenticate and authorize the request as if it came from the user.

## 3. When Does This Happen?
- When a client connects to y-provider (e.g. via WebSocket for collaboration), y-provider:
  - Extracts the user's cookies and origin from the incoming request.
  - Calls the Django backend to fetch user and document info, using those headers for authentication.
  - Uses the results to decide if the user can access or edit the document.

## 4. What Do You Need to Configure?
- Make sure `COLLABORATION_BACKEND_BASE_URL` is set correctly in y-provider’s `.env`.
- Ensure Django is running and accessible at that URL.
- CORS and CSRF settings in Django must allow requests from y-provider’s origin.
- The user's session (cookie) must be valid—y-provider just forwards it.

## 5. How to Test the Connection
- Connect to y-provider as a client (e.g. via your frontend app).
- Attempt to open a collaborative document.
- y-provider will log errors if it cannot reach Django or if authentication fails.

---

### Summary Table

| y-provider action            | Django endpoint called                       | Purpose              |
|------------------------------|----------------------------------------------|----------------------|
| Fetch user info              | `/api/v1.0/users/me/`                        | Auth & permissions   |
| Fetch document info          | `/api/v1.0/documents/<docName>/`             | Document data        |

---

If you want to test this manually:
You can use `curl` to simulate what y-provider does, but usually you’ll test this by connecting with your frontend and watching the logs in both y-provider and Django.
