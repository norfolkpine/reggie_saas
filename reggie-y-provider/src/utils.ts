import { COLLABORATION_LOGGING } from './env';
import * as Sentry from '@sentry/node';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function logger(...args: any[]) {
  if (COLLABORATION_LOGGING === 'true') {
    const message = new Date().toISOString() + ' --- ' + args.join(' ');
    
    // Console for development
    console.log(message);
    
    // Add Sentry breadcrumb for important logs in production
    if (process.env.NODE_ENV === 'production') {
      Sentry.addBreadcrumb({
        category: 'application',
        message: args.join(' '),
        level: 'info',
        data: {
          timestamp: new Date().toISOString(),
          args: args.length > 1 ? args : undefined
        }
      });
    }
  }
}

export const toBase64 = function (str: Uint8Array) {
  return Buffer.from(str).toString('base64');
};
