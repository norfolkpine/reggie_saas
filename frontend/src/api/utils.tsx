import { Configuration, ConfigurationParameters } from "api-client";

export function getApiConfiguration(accessToken?: string | null): Configuration {
  const params: ConfigurationParameters = {
    basePath: import.meta.env.VITE_APP_BASE_URL,
  };
  
  if (accessToken) {
    params.accessToken = accessToken;
  }
  
  return new Configuration(params);
}

// Helper function to refresh token
export async function refreshAccessToken(): Promise<string | null> {
  try {
    const refreshToken = localStorage.getItem('refreshToken');
    if (!refreshToken) {
      return null;
    }

    const response = await fetch(`${import.meta.env.VITE_APP_BASE_URL}/auth/token/refresh/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh: refreshToken }),
    });

    if (response.ok) {
      const data = await response.json();
      localStorage.setItem('accessToken', data.access);
      return data.access;
    } else {
      localStorage.removeItem('refreshToken');
      localStorage.removeItem('accessToken');
      return null;
    }
  } catch (error) {
    console.error('Token refresh failed:', error);
    localStorage.removeItem('refreshToken');
    localStorage.removeItem('accessToken');
    return null;
  }
}
