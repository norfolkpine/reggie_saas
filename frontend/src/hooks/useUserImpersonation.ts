import { useState, useEffect, useCallback } from 'react';

interface User {
  id: number;
  email: string;
  full_name: string;
}

interface ImpersonationState {
  isImpersonating: boolean;
  impersonatedUser: User | null;
  originalUser: User | null;
}

export const useUserImpersonation = () => {
  const [state, setState] = useState<ImpersonationState>({
    isImpersonating: false,
    impersonatedUser: null,
    originalUser: null,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  // Get CSRF token from cookies
  const getCSRFToken = useCallback((): string => {
    const name = 'csrftoken';
    let cookieValue = '';
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }, []);

  // Start impersonating a user using django-hijack
  const startImpersonation = useCallback(async (userId: number): Promise<boolean> => {
    setLoading(true);
    setError('');

    try {
      // Create a form and submit it to django-hijack acquire endpoint
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/hijack/acquire/';
      form.style.display = 'none';

      // Add CSRF token
      const csrfInput = document.createElement('input');
      csrfInput.type = 'hidden';
      csrfInput.name = 'csrfmiddlewaretoken';
      csrfInput.value = getCSRFToken();
      form.appendChild(csrfInput);

      // Add user ID
      const userInput = document.createElement('input');
      userInput.type = 'hidden';
      userInput.name = 'user_pk';
      userInput.value = userId.toString();
      form.appendChild(userInput);

      // Add redirect URL
      const redirectInput = document.createElement('input');
      redirectInput.type = 'hidden';
      redirectInput.name = 'next';
      redirectInput.value = window.location.pathname;
      form.appendChild(redirectInput);

      // Submit the form
      document.body.appendChild(form);
      form.submit();
      
      return true;
    } catch (err) {
      setError('Error starting impersonation');
      console.error('Error starting impersonation:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [getCSRFToken]);

  // Stop impersonating using django-hijack
  const stopImpersonation = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    setError('');

    try {
      // Create a form and submit it to django-hijack release endpoint
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/hijack/release/';
      form.style.display = 'none';

      // Add CSRF token
      const csrfInput = document.createElement('input');
      csrfInput.type = 'hidden';
      csrfInput.name = 'csrfmiddlewaretoken';
      csrfInput.value = getCSRFToken();
      form.appendChild(csrfInput);

      // Add redirect URL
      const redirectInput = document.createElement('input');
      redirectInput.type = 'hidden';
      redirectInput.name = 'next';
      redirectInput.value = window.location.pathname;
      form.appendChild(redirectInput);

      // Submit the form
      document.body.appendChild(form);
      form.submit();
      
      return true;
    } catch (err) {
      setError('Error stopping impersonation');
      console.error('Error stopping impersonation:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [getCSRFToken]);

  // Clear error
  const clearError = useCallback(() => {
    setError('');
  }, []);

  // Check current impersonation status using django-hijack
  const checkImpersonationStatus = useCallback(async () => {
    try {
      const response = await fetch('/hijack/status/', {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        const data = await response.json();
        setState({
          isImpersonating: data.is_hijacked,
          impersonatedUser: data.is_hijacked ? {
            id: data.user_id,
            email: data.user_email,
            full_name: data.user_name || data.user_email,
          } : null,
          originalUser: null, // django-hijack doesn't provide original user info
        });
      }
    } catch (err) {
      console.error('Error checking impersonation status:', err);
    }
  }, []);

  useEffect(() => {
    checkImpersonationStatus();
  }, [checkImpersonationStatus]);

  return {
    ...state,
    loading,
    error,
    startImpersonation,
    stopImpersonation,
    clearError,
  };
};
