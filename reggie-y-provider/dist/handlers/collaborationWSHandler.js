import { hocusPocusServer } from '../servers/hocusPocusServer.js';
export var collaborationWSHandler = function (ws, req) {
    try {
        hocusPocusServer.handleConnection(ws, req);
    }
    catch (error) {
        console.error('Failed to handle WebSocket connection:', error);
        ws.close();
    }
};
