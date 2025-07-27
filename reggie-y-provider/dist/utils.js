import { COLLABORATION_LOGGING } from './env.js';
import * as Sentry from '@sentry/node';
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function logger() {
    var args = [];
    for (var _i = 0; _i < arguments.length; _i++) {
        args[_i] = arguments[_i];
    }
    if (COLLABORATION_LOGGING === 'true') {
        var message = new Date().toISOString() + ' --- ' + args.join(' ');
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
export var toBase64 = function (str) {
    return Buffer.from(str).toString('base64');
};
