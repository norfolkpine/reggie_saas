import * as Sentry from '@sentry/node';
import { nodeProfilingIntegration } from '@sentry/profiling-node';

import { SENTRY_DSN } from '../env';

Sentry.init({
  dsn: SENTRY_DSN,
  integrations: [nodeProfilingIntegration()],
  tracesSampleRate: 0.1,
  profilesSampleRate: 1.0,
  // Simplified configuration for Node.js v18.18.2 ESM compatibility
  debug: false,
});

Sentry.setTag('application', 'y-provider');
