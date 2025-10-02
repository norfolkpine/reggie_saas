import cors from 'cors';
import { NextFunction, Request, Response } from 'express';
import * as ws from 'ws';
import * as Sentry from '@sentry/node';

import {
  COLLABORATION_SERVER_ORIGIN,
  COLLABORATION_SERVER_SECRET,
  Y_PROVIDER_API_KEY,
} from '@/env';

import { logger } from './utils';

const VALID_API_KEYS = [COLLABORATION_SERVER_SECRET, Y_PROVIDER_API_KEY];
const allowedOrigins = COLLABORATION_SERVER_ORIGIN.split(',');

export const corsMiddleware = cors({
  origin: allowedOrigins,
  methods: ['GET', 'POST'],
  credentials: true,
});

export const httpSecurity = (
  req: Request,
  res: Response,
  next: NextFunction,
): void => {
  // Secret API Key check
  // Note: Changing this header to Bearer token format will break backend compatibility with this microservice.
  const apiKey = req.headers['authorization'];
  if (!apiKey || !VALID_API_KEYS.includes(apiKey)) {
    res.status(403).json({ error: 'Forbidden: Invalid API Key' });
    
    // Capture invalid API key attempt in Sentry
    Sentry.captureMessage('HTTP API security violation: Invalid API key', {
      level: 'warning',
      tags: {
        event_type: 'security_violation',
        reason: 'invalid_api_key'
      },
      extra: {
        providedKey: apiKey ? 'present' : 'missing',
        remoteAddress: req.socket?.remoteAddress,
        userAgent: req.headers['user-agent'],
        url: req.url,
        method: req.method
      }
    });
    
    return;
  }

  next();
};

export const wsSecurity = (
  ws: ws.WebSocket,
  req: Request,
  next: NextFunction,
): void => {
  // Origin check
  const origin = req.headers['origin'];
  if (!origin || !allowedOrigins.includes(origin)) {
    ws.close(4001, 'Origin not allowed');
    logger('CORS policy violation: Invalid Origin', origin);
    
    // Capture CORS violation in Sentry
    Sentry.captureMessage('WebSocket CORS violation: Invalid origin', {
      level: 'warning',
      tags: {
        event_type: 'security_violation',
        reason: 'invalid_origin'
      },
      extra: {
        origin,
        allowedOrigins,
        remoteAddress: req.socket?.remoteAddress,
        userAgent: req.headers['user-agent'],
        url: req.url
      }
    });
    
    return;
  }

  const cookies = req.headers['cookie'];
  if (!cookies) {
    ws.close(4001, 'No cookies');
    logger('CORS policy violation: No cookies');
    logger('UA:', req.headers['user-agent']);
    logger('URL:', req.url);
    
    // Capture missing cookies in Sentry
    Sentry.captureMessage('WebSocket CORS violation: No cookies provided', {
      level: 'warning',
      tags: {
        event_type: 'security_violation',
        reason: 'no_cookies'
      },
      extra: {
        origin,
        remoteAddress: req.socket?.remoteAddress,
        userAgent: req.headers['user-agent'],
        url: req.url
      }
    });
    
    return;
  }

  next();
};
