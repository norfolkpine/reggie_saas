import React, { useState, useEffect } from 'react';
import { useUserImpersonation } from '../hooks/useUserImpersonation';

interface User {
  id: number;
  email: string;
  full_name: string;
}

const UserImpersonation: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>('');
  const [error, setError] = useState<string>('');
  
  const {
    isImpersonating,
    impersonatedUser,
    loading,
    startImpersonation,
    stopImpersonation,
    clearError,
  } = useUserImpersonation();

  // Fetch available users for impersonation
  const fetchUsers = async () => {
    try {
      const response = await fetch('/api/v1/users/', {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        setUsers(data.results || data);
      } else {
        setError('Failed to fetch users');
      }
    } catch (err) {
      setError('Error fetching users');
      console.error('Error fetching users:', err);
    }
  };

  // Start impersonating a user
  const handleStartImpersonation = async () => {
    if (!selectedUserId) {
      setError('Please select a user to impersonate');
      return;
    }

    setError('');
    const success = await startImpersonation(parseInt(selectedUserId));
    
    if (!success) {
      setError('Failed to start impersonation');
    }
  };

  // Stop impersonating and return to original user
  const handleStopImpersonation = async () => {
    setError('');
    const success = await stopImpersonation();
    
    if (!success) {
      setError('Failed to stop impersonation');
    }
  };

  // Check current impersonation status on component mount
  useEffect(() => {
    fetchUsers();
  }, []);

  if (isImpersonating) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-yellow-800">
                <strong>Impersonating:</strong> {impersonatedUser?.email}
              </p>
            </div>
          </div>
          <button
            onClick={handleStopImpersonation}
            disabled={loading}
            className="bg-yellow-100 hover:bg-yellow-200 text-yellow-800 px-3 py-1 rounded-md text-sm font-medium disabled:opacity-50"
          >
            {loading ? 'Stopping...' : 'Stop Impersonation'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-lg font-medium text-gray-900 mb-4">User Impersonation</h3>
      
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-3 mb-4">
          <p className="text-sm text-red-800">{error}</p>
          <button
            onClick={() => setError('')}
            className="mt-2 text-red-600 hover:text-red-800 text-sm underline"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <label htmlFor="user-select" className="block text-sm font-medium text-gray-700 mb-2">
            Select User to Impersonate
          </label>
          <select
            id="user-select"
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
            className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
          >
            <option value="">Choose a user...</option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name || user.email} ({user.email})
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleStartImpersonation}
          disabled={!selectedUserId || loading}
          className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white px-4 py-2 rounded-md font-medium disabled:cursor-not-allowed"
        >
          {loading ? 'Starting Impersonation...' : 'Start Impersonation'}
        </button>
      </div>

      <div className="mt-4 text-xs text-gray-500">
        <p>⚠️ Only superusers can impersonate other users. Use this feature responsibly!</p>
      </div>
    </div>
  );
};

export default UserImpersonation;
