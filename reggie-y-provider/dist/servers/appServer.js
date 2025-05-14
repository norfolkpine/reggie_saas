// eslint-disable-next-line import/order
import '../services/sentry.js';
import * as Sentry from '@sentry/node';
import express from 'express';
import expressWebsockets from 'express-ws';
import { PORT } from '../env.js';
import { collaborationResetConnectionsHandler, collaborationWSHandler, convertMarkdownHandler, } from '../handlers/index.js';
import { corsMiddleware, httpSecurity, wsSecurity } from '../middlewares.js';
import { routes } from '../routes.js';
import { logger } from '../utils.js';
/**
 * init the collaboration server.
 *
 * @param port - The port on which the server listens.
 * @param serverSecret - The secret key for API authentication.
 * @returns An object containing the Express app, Hocuspocus server, and HTTP server instance.
 */
export var initServer = function () {
    var app = expressWebsockets(express()).app;
    app.use(express.json());
    app.use(corsMiddleware);
    /**
     * Route to handle WebSocket connections
     */
    app.ws(routes.COLLABORATION_WS, wsSecurity, collaborationWSHandler);
    /**
     * Route to reset connections in a room:
     *  - If no user ID is provided, close all connections in the room
     *  - If a user ID is provided, close connections for the user in the room
     */
    app.post(routes.COLLABORATION_RESET_CONNECTIONS, httpSecurity, collaborationResetConnectionsHandler);
    /**
     * Route to convert markdown
     */
    app.post(routes.CONVERT_MARKDOWN, httpSecurity, convertMarkdownHandler);
    Sentry.setupExpressErrorHandler(app);
    app.get('/ping', function (req, res) {
        res.status(200).json({ message: 'pong' });
    });
    app.use(function (req, res) {
        logger('Invalid route:', req.url);
        res.status(403).json({ error: 'Forbidden' });
    });
    var server = app.listen(PORT, function () {
        return console.log('App listening on port :', PORT);
    });
    return { app: app, server: server };
};
