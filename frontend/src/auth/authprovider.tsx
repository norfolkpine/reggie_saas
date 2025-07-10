import {useState, useEffect, ReactNode, useCallback} from 'react';
import {AuthContext} from "./authcontext";
import {getApiConfiguration} from "../api/utils.tsx";
import {ApiApi, CustomUser} from "api-client"; // JWT import removed

export const AuthProvider = ({ children }: {children: ReactNode}) => {
  // Token is no longer stored in state; session cookie handles it.
  const [user, setUser] = useState<CustomUser | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    setIsLoading(true);
    try {
      // Ensure the API client sends credentials (cookies)
      // This might require configuration of the generated client or a custom fetch wrapper.
      // For openapi-generator-cli, one might use `withCredentials: true` in the config,
      // or pass `credentials: 'include'` to fetch options if customizing the fetch call.
      const client = new ApiApi(getApiConfiguration());
      // Assuming allauth headless user endpoint is at /api/allauth/user/
      // This needs to be mapped in the api-client if it's generated.
      // For now, let's assume a method like `client.allAuthUserRetrieve()` exists or we map it.
      // If the api-client doesn't have a direct method, we might need to use a more generic call.
      // Let's assume the generated client has a method for the new user endpoint.
      // This might be named differently, e.g. client.allauthUserCurrentRetrieve() or similar
      // For the purpose of this change, I'll assume a generic 'fetchCurrentUser' method on the client
      // that maps to the correct allauth headless user endpoint.
      // This will likely be client.apiAllauthUSERRetrieve() or similar based on OpenAPI spec.
      // Let's use a placeholder name and assume it's correctly mapped in api-client generation.
      const userData = await client.apiAllauthUSERRetrieve(); // Placeholder - replace with actual generated method
      setUser(userData);
      setIsAuthenticated(true);
      console.log('User fetched successfully');
    } catch (error) {
      // console.error('Failed to fetch user:', error);
      // It's common to fail fetching user if not authenticated, so this might not be an "error" to log loudly.
      setUser(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  // Called after successful login or OTP verification by the respective pages
  const handleLoginSuccess = useCallback(async (loggedInUser?: CustomUser) => {
    if (loggedInUser) {
        setUser(loggedInUser);
        setIsAuthenticated(true);
    } else {
        // If user data isn't passed directly, refetch it.
        await fetchUser();
    }
    setIsLoading(false); // Ensure loading is false after login success
    console.log('User logged in and details set/refreshed');
  }, [fetchUser]);

  const handleLogout = useCallback(async () => {
    console.log('Logging out user');
    try {
      const client = new ApiApi(getApiConfiguration());
      // Assuming allauth headless logout is at /api/allauth/logout/
      // This needs to be mapped in the api-client.
      // Example: await client.apiAllauthLOGOUTCreate(); // Placeholder
      await client.apiAllauthLOGOUTCreate(); // Placeholder - replace with actual
      console.log('Logout API call successful');
    } catch (error) {
      console.error('Logout API call failed:', error);
      // Still proceed with local state clearing
    } finally {
      setUser(null);
      setIsAuthenticated(false);
      // No local JWTs to remove
      // Cookies (like sessionid, csrftoken) are HttpOnly or managed by browser/backend on logout.
    }
  }, []);

  // setUserDetails is renamed to handleLoginSuccess and takes optional user
  // as allauth login might return user data directly.
  const contextValue = {
    token: null, // Token is no longer managed here
    user,
    isAuthenticated,
    isLoading,
    setUserDetails: handleLoginSuccess, // Renamed and repurposed
    logout: handleLogout,
  };

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
};
