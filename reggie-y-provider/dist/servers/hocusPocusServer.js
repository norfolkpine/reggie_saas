var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
var __rest = (this && this.__rest) || function (s, e) {
    var t = {};
    for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p) && e.indexOf(p) < 0)
        t[p] = s[p];
    if (s != null && typeof Object.getOwnPropertySymbols === "function")
        for (var i = 0, p = Object.getOwnPropertySymbols(s); i < p.length; i++) {
            if (e.indexOf(p[i]) < 0 && Object.prototype.propertyIsEnumerable.call(s, p[i]))
                t[p[i]] = s[p[i]];
        }
    return t;
};
import { Server } from '@hocuspocus/server';
import { validate as uuidValidate, version as uuidVersion } from 'uuid';
import { fetchDocument } from '../api/getDoc.js';
import { getMe } from '../api/getMe.js';
import { logger } from '../utils.js';
// Startup check: warn if not in production mode
if (process.env.NODE_ENV !== 'production') {
    logger('[SECURITY WARNING] Authentication is bypassed because NODE_ENV is not set to "production". Do not use this mode in production!');
}
var corsOrigin = process.env.CORS_ORIGIN || "*";
export var hocusPocusServer = Server.configure({
    name: 'docs-collaboration',
    timeout: 30000,
    quiet: true,
    onConnect: function (_a) {
        return __awaiter(this, arguments, void 0, function (_b) {
            var authorization, cookie, safeHeaders, roomParam, user, err_1, can_edit, document_1, error_1, user, err_2;
            var _c, _d;
            var requestHeaders = _b.requestHeaders, connection = _b.connection, documentName = _b.documentName, requestParameters = _b.requestParameters, context = _b.context, request = _b.request;
            return __generator(this, function (_e) {
                switch (_e.label) {
                    case 0:
                        authorization = requestHeaders.authorization, cookie = requestHeaders.cookie, safeHeaders = __rest(requestHeaders, ["authorization", "cookie"]);
                        logger('Attempted connection:', {
                            documentName: documentName,
                            headers: safeHeaders,
                            url: request === null || request === void 0 ? void 0 : request.url,
                            remoteAddress: (_c = request === null || request === void 0 ? void 0 : request.socket) === null || _c === void 0 ? void 0 : _c.remoteAddress,
                        });
                        roomParam = requestParameters.get('room');
                        // Allow all connections in local development (no cookie required)
                        if (process.env.NODE_ENV !== "production") {
                            logger("Bypass hit! Local dev: allowing anonymous connection to room:", documentName);
                            connection.readOnly = false;
                            context.userId = "dev-user";
                            return [2 /*return*/, Promise.resolve()];
                        }
                        if (!(process.env.NODE_ENV === "production")) return [3 /*break*/, 5];
                        _e.label = 1;
                    case 1:
                        _e.trys.push([1, 3, , 4]);
                        return [4 /*yield*/, getMe(requestHeaders)];
                    case 2:
                        user = _e.sent();
                        context.userId = user.id;
                        return [3 /*break*/, 4];
                    case 3:
                        err_1 = _e.sent();
                        logger('onConnect: backend error', err_1);
                        return [2 /*return*/, Promise.reject(new Error('Backend error: Unauthorized'))];
                    case 4: return [3 /*break*/, 6];
                    case 5:
                        // For extra safety, allow in dev
                        context.userId = "dev-user";
                        _e.label = 6;
                    case 6:
                        if (documentName !== roomParam) {
                            logger('Invalid room name - Probable hacking attempt:', documentName, requestParameters.get('room'));
                            logger('UA:', request.headers['user-agent']);
                            logger('URL:', request.url);
                            return [2 /*return*/, Promise.reject(new Error('Wrong room name: Unauthorized'))];
                        }
                        if (!uuidValidate(documentName) || uuidVersion(documentName) !== 4) {
                            logger('Room name is not a valid uuid:', documentName);
                            return [2 /*return*/, Promise.reject(new Error('Wrong room name: Unauthorized'))];
                        }
                        can_edit = false;
                        _e.label = 7;
                    case 7:
                        _e.trys.push([7, 9, , 10]);
                        return [4 /*yield*/, fetchDocument(documentName, requestHeaders)];
                    case 8:
                        document_1 = _e.sent();
                        if (!document_1.abilities.retrieve) {
                            logger('onConnect: Unauthorized to retrieve this document', documentName);
                            return [2 /*return*/, Promise.reject(new Error('Wrong abilities:Unauthorized'))];
                        }
                        can_edit = document_1.abilities.update;
                        return [3 /*break*/, 10];
                    case 9:
                        error_1 = _e.sent();
                        if (error_1 instanceof Error) {
                            logger('onConnect: backend error', error_1.message);
                        }
                        return [2 /*return*/, Promise.reject(new Error('Backend error: Unauthorized'))];
                    case 10:
                        connection.readOnly = !can_edit;
                        _e.label = 11;
                    case 11:
                        _e.trys.push([11, 13, , 14]);
                        return [4 /*yield*/, getMe(requestHeaders)];
                    case 12:
                        user = _e.sent();
                        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
                        context.userId = user.id;
                        return [3 /*break*/, 14];
                    case 13:
                        err_2 = _e.sent();
                        logger('onConnect: silent getMe error', err_2 instanceof Error ? err_2.message : err_2);
                        return [3 /*break*/, 14];
                    case 14:
                        logger('Connection established', {
                            room: documentName,
                            userId: context.userId,
                            canEdit: can_edit,
                            remoteAddress: (_d = request === null || request === void 0 ? void 0 : request.socket) === null || _d === void 0 ? void 0 : _d.remoteAddress,
                        });
                        return [2 /*return*/, Promise.resolve()];
                }
            });
        });
    },
});
