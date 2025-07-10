import { Configuration, ConfigurationParameters } from "api-client";

// Function to get CSRF token from cookies
function getCsrfToken(): string | null {
  const name = 'csrftoken=';
  const decodedCookie = decodeURIComponent(document.cookie);
  const ca = decodedCookie.split(';');
  for (let i = 0; i < ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) === ' ') {
      c = c.substring(1);
    }
    if (c.indexOf(name) === 0) {
      return c.substring(name.length, c.length);
    }
  }
  return null;
}

export function getApiConfiguration(): Configuration {
  const params: ConfigurationParameters = {
    basePath: import.meta.env.VITE_APP_BASE_URL,
    credentials: 'omit', // Default, but we'll override for specific calls if needed or rely on global fetch config
    headers: {},
  };

  // For session-based authentication, CSRF token is needed for mutating requests (POST, PUT, DELETE, PATCH)
  // The generated api-client might handle this automatically if configured,
  // or individual requests might need to include it.
  // For now, we'll add it to default headers if found.
  // Note: GET/HEAD requests typically don't need CSRF.
  const csrfToken = getCsrfToken();
  if (csrfToken) {
    if (params.headers) { // params.headers is initialized as {}
        (params.headers as Record<string, string>)['X-CSRFToken'] = csrfToken;
    }
  }

  // The `api-client` should be configured to send credentials (cookies) with each request.
  // This might be a global setting in the generator or a per-request option.
  // For fetch API, it would be `credentials: 'include'`.
  // We assume the generated client will handle cookies appropriately or we'll adjust specific calls.
  // Forcing it here if the generated client doesn't have a global option:
  // params.fetchApi = (url, init) => fetch(url, { ...init, credentials: 'include' });


  return new Configuration(params);
}

// refreshAccessToken is no longer needed with session-based auth managed by http-only cookies.
// export async function refreshAccessToken(): Promise<string | null> { ... }
