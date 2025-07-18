import {useState, useEffect, ReactNode} from 'react';
import {AuthContext} from "./authcontext";
import {getApiConfiguration} from "../api/utils.tsx";
import {ApiApi, CustomUser, JWT} from "api-client";

export const AuthProvider = ({ children }: {children: ReactNode}) => {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<CustomUser | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Function to check if token is expired
  const isTokenExpired = (token: string): boolean => {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const expiryTime = payload.exp * 1000; // Convert to milliseconds
      const currentTime = Date.now();
      // Consider token expired if it expires within the next 5 minutes
      return currentTime >= (expiryTime - 5 * 60 * 1000);
    } catch (error) {
      console.error('Error parsing token:', error);
      return true; // Consider expired if we can't parse it
    }
  };

  // Function to refresh token
  const refreshToken = async (refreshTokenValue: string): Promise<string | null> => {
    try {
      const client = new ApiApi(getApiConfiguration());
      const refreshData = await client.apiAuthTokenRefreshCreate({
        tokenRefresh: { refresh: refreshTokenValue }
      });
      localStorage.setItem('accessToken', refreshData.access);
      return refreshData.access;
    } catch (error) {
      console.error('Token refresh failed:', error);
      localStorage.removeItem('refreshToken');
      return null;
    }
  };

  useEffect(() => {
    const initializeAuth = async () => {
      const storedToken = localStorage.getItem('accessToken');
      const refreshTokenValue = localStorage.getItem('refreshToken');

      if (storedToken) {
        // Check if current token is expired or about to expire
        if (isTokenExpired(storedToken)) {
          console.log('Access token expired, attempting refresh...');
          if (refreshTokenValue) {
            const newToken = await refreshToken(refreshTokenValue);
            if (newToken) {
              await validateTokenAndSetUser(newToken);
            } else {
              setIsAuthenticated(false);
            }
          } else {
            setIsAuthenticated(false);
          }
        } else {
          // Token is still valid
          await validateTokenAndSetUser(storedToken);
        }
      } else if (refreshTokenValue) {
        // No access token but have refresh token
        console.log('No access token, attempting refresh...');
        const newToken = await refreshToken(refreshTokenValue);
        if (newToken) {
          await validateTokenAndSetUser(newToken);
        } else {
          setIsAuthenticated(false);
        }
      } else {
        setIsAuthenticated(false);
      }
      
      setIsLoading(false);
    };

    const validateTokenAndSetUser = async (tokenValue: string) => {
      try {
        const client = new ApiApi(getApiConfiguration(tokenValue));
        const userBack = await client.apiAuthUserRetrieve();
        setToken(tokenValue);
        setIsAuthenticated(true);
        setUser(userBack);
        console.log('Authentication successful');
      } catch (error) {
        console.error('Token validation failed:', error);
        // Token didn't work, try refresh
        localStorage.removeItem('accessToken');
        const refreshTokenValue = localStorage.getItem('refreshToken');
        if (refreshTokenValue) {
          const newToken = await refreshToken(refreshTokenValue);
          if (newToken) {
            await validateTokenAndSetUser(newToken);
          } else {
            setIsAuthenticated(false);
          }
        } else {
          setIsAuthenticated(false);
        }
      }
    };

    initializeAuth();
  }, []);

  const handleSetUserDetails = (jwtResponse: JWT) => {
    localStorage.setItem('refreshToken', jwtResponse.refresh);
    setToken(jwtResponse.access);
    localStorage.setItem('accessToken', jwtResponse.access);
    setUser(jwtResponse.user)
    setIsLoading(false);
    setIsAuthenticated(true);
    console.log('User details set successfully');
  };

  const handleLogout = () => {
    console.log('Logging out user');
    setToken(null);
    setUser(null);
    setIsAuthenticated(false);
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
  };

  const contextValue = {
    token,
    user,
    isAuthenticated,
    isLoading,
    setUserDetails: handleSetUserDetails,
    logout: handleLogout,
  };

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
};
