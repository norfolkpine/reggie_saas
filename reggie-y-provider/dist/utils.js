var __spreadArray = (this && this.__spreadArray) || function (to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
        if (ar || !(i in from)) {
            if (!ar) ar = Array.prototype.slice.call(from, 0, i);
            ar[i] = from[i];
        }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
};
import { COLLABORATION_LOGGING } from './env.js';
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function logger() {
    var args = [];
    for (var _i = 0; _i < arguments.length; _i++) {
        args[_i] = arguments[_i];
    }
    if (COLLABORATION_LOGGING === 'true') {
        // eslint-disable-next-line @typescript-eslint/no-unsafe-argument
        console.log.apply(console, __spreadArray([new Date().toISOString(), ' --- '], args, false));
    }
}
export var toBase64 = function (str) {
    return Buffer.from(str).toString('base64');
};
