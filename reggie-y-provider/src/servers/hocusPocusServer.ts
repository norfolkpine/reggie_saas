import { Server } from '@hocuspocus/server';
import { validate as uuidValidate, version as uuidVersion } from 'uuid';
import * as Sentry from '@sentry/node';

import { fetchDocument } from '@/api/getDoc';
import { getMe } from '@/api/getMe';
import { logger } from '@/utils';

// Startup check: warn if not in production mode
if (process.env.NODE_ENV !== 'production') {
  logger('[SECURITY WARNING] Authentication is bypassed because NODE_ENV is not set to "production". Do not use this mode in production!');
}

const corsOrigin = process.env.CORS_ORIGIN || "*";

export const hocusPocusServer = Server.configure({
  name: 'docs-collaboration',
  timeout: 30000,
  quiet: true,

  async onConnect({
    requestHeaders,
    connection,
    documentName,
    requestParameters,
    context,
    request,
  }) {
    // Mask sensitive headers before logging
    const { authorization, cookie, ...safeHeaders } = requestHeaders;
    
    // Add Sentry breadcrumb for connection attempt
    Sentry.addBreadcrumb({
      category: 'websocket',
      message: 'WebSocket connection attempt',
      level: 'info',
      data: {
        documentName,
        url: request?.url,
        remoteAddress: request?.socket?.remoteAddress,
        hasCookie: !!cookie,
        userAgent: request?.headers['user-agent'],
      }
    });

    logger('Attempted connection:', {
      documentName,
      headers: safeHeaders,
      url: request?.url,
      remoteAddress: request?.socket?.remoteAddress,
      hasCookie: !!cookie,
    });
    const roomParam = requestParameters.get('room');

    // Allow all connections in local development (no cookie required)
    if (process.env.NODE_ENV !== "production") {
      logger("Bypass hit! Local dev: allowing anonymous connection to room:", documentName);
      connection.readOnly = false;
      context.userId = "dev-user";
      return Promise.resolve();
    }

    // Only run authentication in production
    if (process.env.NODE_ENV === "production") {
      // Check if cookie is provided before attempting authentication
      if (!requestHeaders.cookie) {
        logger('onConnect: No cookie provided in production mode');
        
        // Capture authentication failure in Sentry
        Sentry.captureMessage('WebSocket authentication failed: No cookie provided', {
          level: 'warning',
          tags: {
            event_type: 'auth_failure',
            reason: 'no_cookie'
          },
          extra: {
            documentName,
            remoteAddress: request?.socket?.remoteAddress,
            userAgent: request?.headers['user-agent'],
            url: request?.url
          }
        });
        
        return Promise.reject(new Error('Authentication required: No cookie provided'));
      }

      try {
        const user = await getMe(requestHeaders);
        context.userId = user.id;
      } catch (err) {
        logger('onConnect: backend error', err);
        
        // Capture backend authentication error in Sentry
        Sentry.captureMessage('WebSocket authentication failed: Backend error', {
          level: 'error',
          tags: {
            event_type: 'auth_failure',
            reason: 'backend_error'
          },
          extra: {
            documentName,
            remoteAddress: request?.socket?.remoteAddress,
            userAgent: request?.headers['user-agent'],
            url: request?.url,
            error: err instanceof Error ? err.message : String(err)
          }
        });
        
        return Promise.reject(new Error('Backend error: Unauthorized'));
      }
    } else {
      // For extra safety, allow in dev
      context.userId = "dev-user";
    }

    if (documentName !== roomParam) {
      logger(
        'Invalid room name - Probable hacking attempt:',
        documentName,
        requestParameters.get('room'),
      );
      logger('UA:', request.headers['user-agent']);
      logger('URL:', request.url);

      // Capture potential security threat in Sentry
      Sentry.captureMessage('WebSocket security threat: Invalid room name', {
        level: 'warning',
        tags: {
          event_type: 'security_threat',
          reason: 'invalid_room_name'
        },
        extra: {
          documentName,
          roomParam,
          remoteAddress: request?.socket?.remoteAddress,
          userAgent: request?.headers['user-agent'],
          url: request?.url
        }
      });

      return Promise.reject(new Error('Wrong room name: Unauthorized'));
    }

    if (!uuidValidate(documentName) || uuidVersion(documentName) !== 4) {
      logger('Room name is not a valid uuid:', documentName);

      // Capture invalid UUID in Sentry
      Sentry.captureMessage('WebSocket security threat: Invalid UUID format', {
        level: 'warning',
        tags: {
          event_type: 'security_threat',
          reason: 'invalid_uuid'
        },
        extra: {
          documentName,
          remoteAddress: request?.socket?.remoteAddress,
          userAgent: request?.headers['user-agent'],
          url: request?.url
        }
      });

      return Promise.reject(new Error('Wrong room name: Unauthorized'));
    }

    let can_edit = false;

    try {
      const document = await fetchDocument(documentName, requestHeaders);

      if (!document.abilities.retrieve) {
        logger(
          'onConnect: Unauthorized to retrieve this document',
          documentName,
        );
        
        // Capture permission denied in Sentry
        Sentry.captureMessage('WebSocket access denied: Insufficient permissions', {
          level: 'warning',
          tags: {
            event_type: 'access_denied',
            reason: 'insufficient_permissions'
          },
          extra: {
            documentName,
            userId: context.userId,
            remoteAddress: request?.socket?.remoteAddress,
            userAgent: request?.headers['user-agent'],
            url: request?.url
          }
        });
        
        return Promise.reject(new Error('Wrong abilities:Unauthorized'));
      }

      can_edit = document.abilities.update;
    } catch (error: unknown) {
      if (error instanceof Error) {
        logger('onConnect: backend error', error.message);
      }

      // Capture document fetch error in Sentry
      Sentry.captureMessage('WebSocket authentication failed: Document fetch error', {
        level: 'error',
        tags: {
          event_type: 'auth_failure',
          reason: 'document_fetch_error'
        },
        extra: {
          documentName,
          userId: context.userId,
          remoteAddress: request?.socket?.remoteAddress,
          userAgent: request?.headers['user-agent'],
          url: request?.url,
          error: error instanceof Error ? error.message : String(error)
        }
      });

      return Promise.reject(new Error('Backend error: Unauthorized'));
    }

    connection.readOnly = !can_edit;

    /*
     * Unauthenticated users can be allowed to connect
     * so we flag only authenticated users
     */
    try {
      const user = await getMe(requestHeaders);
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      context.userId = user.id;
    } catch (err) {
      logger('onConnect: silent getMe error', err instanceof Error ? err.message : err);
    }

    // Add Sentry breadcrumb for successful connection
    Sentry.addBreadcrumb({
      category: 'websocket',
      message: 'WebSocket connection established',
      level: 'info',
      data: {
        documentName,
        userId: context.userId,
        canEdit: can_edit,
        remoteAddress: request?.socket?.remoteAddress,
      }
    });

    logger('Connection established', {
      room: documentName,
      userId: context.userId,
      canEdit: can_edit,
      remoteAddress: request?.socket?.remoteAddress,
    });
    return Promise.resolve();
  },
});
