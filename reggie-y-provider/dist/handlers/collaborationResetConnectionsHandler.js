import { hocusPocusServer } from '../servers/hocusPocusServer.js';
import { logger } from '../utils.js';
export var collaborationResetConnectionsHandler = function (req, res) {
    var room = req.query.room;
    var userId = req.headers['x-user-id'];
    logger('Resetting connections in room:', room, 'for user:', userId);
    if (!room) {
        res.status(400).json({ error: 'Room name not provided' });
        return;
    }
    /**
     * If no user ID is provided, close all connections in the room
     */
    if (!userId) {
        hocusPocusServer.closeConnections(room);
    }
    else {
        /**
         * Close connections for the user in the room
         */
        hocusPocusServer.documents.forEach(function (doc) {
            if (doc.name !== room) {
                return;
            }
            doc.getConnections().forEach(function (connection) {
                // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                if (connection.context.userId === userId) {
                    connection.close();
                }
            });
        });
    }
    res.status(200).json({ message: 'Connections reset' });
};
