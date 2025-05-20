import cors from 'cors';
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
    // Secret API Key check
    // Note: Changing this header to Bearer token format will break backend compatibility with this microservice.
    var apiKey = req.headers['authorization'];
    if (!apiKey || !VALID_API_KEYS.includes(apiKey)) {
        res.status(403).json({ error: 'Forbidden: Invalid API Key' });
        return;
    }
    next();
};
export var wsSecurity = function (ws, req, next) {
    // Origin check
    var origin = req.headers['origin'];
    if (!origin || !allowedOrigins.includes(origin)) {
        ws.close(4001, 'Origin not allowed');
        logger('CORS policy violation: Invalid Origin', origin);
        return;
    }
    var cookies = req.headers['cookie'];
    if (!cookies) {
        ws.close(4001, 'No cookies');
        logger('CORS policy violation: No cookies');
        logger('UA:', req.headers['user-agent']);
        logger('URL:', req.url);
        return;
    }
    next();
};
