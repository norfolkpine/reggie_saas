/**
 * Frontend integration example for Nango OAuth flows
 * 
 * This example shows how to integrate Nango in your React/Next.js frontend
 */

import { useState, useEffect } from 'react';
import axios from 'axios';

// Nango configuration
const NANGO_PUBLIC_KEY = process.env.NEXT_PUBLIC_NANGO_PUBLIC_KEY;
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

interface Connection {
  id: number;
  provider: string;
  provider_name: string;
  connection_id: string;
  created_at: string;
  status: string;
  metadata: any;
}

// Hook to manage Nango integrations
export const useNangoIntegrations = () => {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch existing connections
  const fetchConnections = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/integrations/nango/connections/`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
        }
      });
      setConnections(response.data);
    } catch (err) {
      setError('Failed to fetch connections');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Initiate OAuth flow
  const connectIntegration = async (provider: string) => {
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/integrations/nango/auth/`,
        { 
          provider,
          redirect_uri: `${window.location.origin}/integrations/callback`
        },
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
          }
        }
      );

      // Redirect to Nango auth URL
      window.location.href = response.data.auth_url;
    } catch (err) {
      setError('Failed to initiate connection');
      console.error(err);
    }
  };

  // Disconnect integration
  const disconnectIntegration = async (connectionId: number) => {
    try {
      await axios.delete(
        `${API_BASE_URL}/api/integrations/nango/connections/${connectionId}/disconnect/`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
          }
        }
      );
      // Refresh connections
      await fetchConnections();
    } catch (err) {
      setError('Failed to disconnect integration');
      console.error(err);
    }
  };

  // Make API request through Nango proxy
  const makeApiRequest = async (
    connectionId: number,
    method: string,
    endpoint: string,
    data?: any
  ) => {
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/integrations/nango/proxy/`,
        {
          connection_id: connectionId,
          method,
          endpoint,
          data
        },
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
          }
        }
      );
      return response.data;
    } catch (err) {
      setError('API request failed');
      console.error(err);
      throw err;
    }
  };

  useEffect(() => {
    fetchConnections();
  }, []);

  return {
    connections,
    loading,
    error,
    connectIntegration,
    disconnectIntegration,
    makeApiRequest,
    refreshConnections: fetchConnections
  };
};

// Component to display integrations
export const IntegrationsManager: React.FC = () => {
  const {
    connections,
    loading,
    error,
    connectIntegration,
    disconnectIntegration,
    makeApiRequest
  } = useNangoIntegrations();

  const supportedProviders = [
    { key: 'google-drive', name: 'Google Drive', icon: '📁' },
    { key: 'slack', name: 'Slack', icon: '💬' },
    { key: 'notion', name: 'Notion', icon: '📝' },
    { key: 'github', name: 'GitHub', icon: '🐙' },
  ];

  const testGoogleDriveApi = async (connectionId: number) => {
    try {
      const files = await makeApiRequest(
        connectionId,
        'GET',
        'https://www.googleapis.com/drive/v3/files',
        { params: { pageSize: 10 } }
      );
      console.log('Google Drive files:', files);
      alert(`Found ${files.files?.length || 0} files in Google Drive`);
    } catch (err) {
      alert('Failed to fetch Google Drive files');
    }
  };

  if (loading) return <div>Loading connections...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div className="integrations-manager">
      <h2>Manage Integrations</h2>
      
      {/* Available Providers */}
      <div className="providers-grid">
        <h3>Connect New Integration</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {supportedProviders.map(provider => {
            const isConnected = connections.some(c => c.provider === provider.key);
            return (
              <div key={provider.key} className="provider-card">
                <div className="text-4xl">{provider.icon}</div>
                <h4>{provider.name}</h4>
                {isConnected ? (
                  <span className="status connected">✓ Connected</span>
                ) : (
                  <button
                    onClick={() => connectIntegration(provider.key)}
                    className="btn btn-primary"
                  >
                    Connect
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Connected Integrations */}
      <div className="connections-list mt-8">
        <h3>Active Connections</h3>
        {connections.length === 0 ? (
          <p>No active connections</p>
        ) : (
          <div className="space-y-4">
            {connections.map(connection => (
              <div key={connection.id} className="connection-item border p-4 rounded">
                <div className="flex justify-between items-center">
                  <div>
                    <h4 className="font-semibold">{connection.provider_name}</h4>
                    <p className="text-sm text-gray-600">
                      Connected: {new Date(connection.created_at).toLocaleDateString()}
                    </p>
                    <p className="text-sm">
                      Status: <span className={`status-${connection.status}`}>
                        {connection.status}
                      </span>
                    </p>
                  </div>
                  <div className="actions">
                    {connection.provider === 'google-drive' && (
                      <button
                        onClick={() => testGoogleDriveApi(connection.id)}
                        className="btn btn-sm mr-2"
                      >
                        Test API
                      </button>
                    )}
                    <button
                      onClick={() => disconnectIntegration(connection.id)}
                      className="btn btn-danger btn-sm"
                    >
                      Disconnect
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// Callback handler component
export const NangoCallbackHandler: React.FC = () => {
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');

  useEffect(() => {
    // Handle the callback from Nango
    const params = new URLSearchParams(window.location.search);
    const connectionId = params.get('connectionId');
    const providerConfigKey = params.get('providerConfigKey');
    const error = params.get('error');

    if (error) {
      setStatus('error');
      console.error('OAuth error:', error);
    } else if (connectionId && providerConfigKey) {
      // Connection successful
      setStatus('success');
      // Redirect to integrations page after 2 seconds
      setTimeout(() => {
        window.location.href = '/integrations';
      }, 2000);
    }
  }, []);

  return (
    <div className="callback-handler">
      {status === 'processing' && <p>Processing OAuth callback...</p>}
      {status === 'success' && (
        <div>
          <p>✅ Integration connected successfully!</p>
          <p>Redirecting to integrations page...</p>
        </div>
      )}
      {status === 'error' && (
        <div>
          <p>❌ Failed to connect integration</p>
          <a href="/integrations">Return to integrations</a>
        </div>
      )}
    </div>
  );
};

// Example usage in a page
export default function IntegrationsPage() {
  return (
    <div className="container mx-auto p-4">
      <IntegrationsManager />
    </div>
  );
}