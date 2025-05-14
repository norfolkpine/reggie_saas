"use strict";
/*
 * ATTENTION: An "eval-source-map" devtool has been used.
 * This devtool is neither made for production nor for readable output files.
 * It uses "eval()" calls to create a separate source file with attached SourceMaps in the browser devtools.
 * If you are trying to read the output file, select a different devtool (https://webpack.js.org/configuration/devtool/)
 * or disable the default devtool with "devtool: false".
 * If you are looking for production-ready output files, see mode: "production" (https://webpack.js.org/configuration/mode/).
 */
exports.id = "vendor-chunks/rehype-stringify";
exports.ids = ["vendor-chunks/rehype-stringify"];
exports.modules = {

/***/ "(ssr)/./node_modules/rehype-stringify/lib/index.js":
/*!****************************************************!*\
  !*** ./node_modules/rehype-stringify/lib/index.js ***!
  \****************************************************/
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {

eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   \"default\": () => (/* binding */ rehypeStringify)\n/* harmony export */ });\n/* harmony import */ var hast_util_to_html__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! hast-util-to-html */ \"(ssr)/./node_modules/hast-util-to-html/lib/index.js\");\n/**\n * @typedef {import('hast').Root} Root\n * @typedef {Root|Root['children'][number]} Node\n * @typedef {import('hast-util-to-html').Options} Options\n */\n\n\n\n/**\n * @this {import('unified').Processor}\n * @type {import('unified').Plugin<[Options?]|Array<void>, Node, string>}\n */\nfunction rehypeStringify(config) {\n  const processorSettings = /** @type {Options} */ (this.data('settings'))\n  const settings = Object.assign({}, processorSettings, config)\n\n  Object.assign(this, {Compiler: compiler})\n\n  /**\n   * @type {import('unified').CompilerFunction<Node, string>}\n   */\n  function compiler(tree) {\n    return (0,hast_util_to_html__WEBPACK_IMPORTED_MODULE_0__.toHtml)(tree, settings)\n  }\n}\n//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHNzcikvLi9ub2RlX21vZHVsZXMvcmVoeXBlLXN0cmluZ2lmeS9saWIvaW5kZXguanMiLCJtYXBwaW5ncyI6Ijs7Ozs7QUFBQTtBQUNBLGFBQWEscUJBQXFCO0FBQ2xDLGFBQWEsK0JBQStCO0FBQzVDLGFBQWEscUNBQXFDO0FBQ2xEOztBQUV3Qzs7QUFFeEM7QUFDQSxVQUFVO0FBQ1YsVUFBVTtBQUNWO0FBQ2U7QUFDZix1Q0FBdUMsU0FBUztBQUNoRCxtQ0FBbUM7O0FBRW5DLHVCQUF1QixtQkFBbUI7O0FBRTFDO0FBQ0EsWUFBWTtBQUNaO0FBQ0E7QUFDQSxXQUFXLHlEQUFNO0FBQ2pCO0FBQ0EiLCJzb3VyY2VzIjpbIndlYnBhY2s6Ly9AbGl2ZWJsb2Nrcy1leGFtcGxlcy9uZXh0anMteWpzLWJsb2Nrbm90ZS1hZHZhbmNlZC8uL25vZGVfbW9kdWxlcy9yZWh5cGUtc3RyaW5naWZ5L2xpYi9pbmRleC5qcz85OGVkIl0sInNvdXJjZXNDb250ZW50IjpbIi8qKlxuICogQHR5cGVkZWYge2ltcG9ydCgnaGFzdCcpLlJvb3R9IFJvb3RcbiAqIEB0eXBlZGVmIHtSb290fFJvb3RbJ2NoaWxkcmVuJ11bbnVtYmVyXX0gTm9kZVxuICogQHR5cGVkZWYge2ltcG9ydCgnaGFzdC11dGlsLXRvLWh0bWwnKS5PcHRpb25zfSBPcHRpb25zXG4gKi9cblxuaW1wb3J0IHt0b0h0bWx9IGZyb20gJ2hhc3QtdXRpbC10by1odG1sJ1xuXG4vKipcbiAqIEB0aGlzIHtpbXBvcnQoJ3VuaWZpZWQnKS5Qcm9jZXNzb3J9XG4gKiBAdHlwZSB7aW1wb3J0KCd1bmlmaWVkJykuUGx1Z2luPFtPcHRpb25zP118QXJyYXk8dm9pZD4sIE5vZGUsIHN0cmluZz59XG4gKi9cbmV4cG9ydCBkZWZhdWx0IGZ1bmN0aW9uIHJlaHlwZVN0cmluZ2lmeShjb25maWcpIHtcbiAgY29uc3QgcHJvY2Vzc29yU2V0dGluZ3MgPSAvKiogQHR5cGUge09wdGlvbnN9ICovICh0aGlzLmRhdGEoJ3NldHRpbmdzJykpXG4gIGNvbnN0IHNldHRpbmdzID0gT2JqZWN0LmFzc2lnbih7fSwgcHJvY2Vzc29yU2V0dGluZ3MsIGNvbmZpZylcblxuICBPYmplY3QuYXNzaWduKHRoaXMsIHtDb21waWxlcjogY29tcGlsZXJ9KVxuXG4gIC8qKlxuICAgKiBAdHlwZSB7aW1wb3J0KCd1bmlmaWVkJykuQ29tcGlsZXJGdW5jdGlvbjxOb2RlLCBzdHJpbmc+fVxuICAgKi9cbiAgZnVuY3Rpb24gY29tcGlsZXIodHJlZSkge1xuICAgIHJldHVybiB0b0h0bWwodHJlZSwgc2V0dGluZ3MpXG4gIH1cbn1cbiJdLCJuYW1lcyI6W10sInNvdXJjZVJvb3QiOiIifQ==\n//# sourceURL=webpack-internal:///(ssr)/./node_modules/rehype-stringify/lib/index.js\n");

/***/ })

};
;