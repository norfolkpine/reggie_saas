import cors from 'cors';
import * as Sentry from '@sentry/node';
import { COLLABORATION_SERVER_ORIGIN, COLLABORATION_SERVER_SECRET, Y_PROVIDER_API_KEY, } from './env.js';
import { logger } from './utils.js';
var VALID_API_KEYS = [COLLABORATION_SERVER_SECRET, Y_PROVIDER_API_KEY];
var allowedOrigins = COLLABORATION_SERVER_ORIGIN.split(',');
export var corsMiddleware = cors({
    origin: allowedOrigins,
    methods: ['GET', 'POST'],
    credentials: true,
});
export var httpSecurity = function (req, res, next) {
    var _a;
    // Secret API Key check
    // Note: Changing this header to Bearer token format will break backend compatibility with this microservice.
    var apiKey = req.headers['authorization'];
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
                remoteAddress: (_a = req.socket) === null || _a === void 0 ? void 0 : _a.remoteAddress,
                userAgent: req.headers['user-agent'],
                url: req.url,
                method: req.method
            }
        });
        return;
    }
    next();
};
export var wsSecurity = function (ws, req, next) {
    var _a, _b;
    // Origin check
    var origin = req.headers['origin'];
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
                origin: origin,
                allowedOrigins: allowedOrigins,
                remoteAddress: (_a = req.socket) === null || _a === void 0 ? void 0 : _a.remoteAddress,
                userAgent: req.headers['user-agent'],
                url: req.url
            }
        });
        return;
    }
    var cookies = req.headers['cookie'];
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
                origin: origin,
                remoteAddress: (_b = req.socket) === null || _b === void 0 ? void 0 : _b.remoteAddress,
                userAgent: req.headers['user-agent'],
                url: req.url
            }
        });
        return;
    }
    next();
};
