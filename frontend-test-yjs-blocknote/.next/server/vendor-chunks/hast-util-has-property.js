"use strict";
/*
 * ATTENTION: An "eval-source-map" devtool has been used.
 * This devtool is neither made for production nor for readable output files.
 * It uses "eval()" calls to create a separate source file with attached SourceMaps in the browser devtools.
 * If you are trying to read the output file, select a different devtool (https://webpack.js.org/configuration/devtool/)
 * or disable the default devtool with "devtool: false".
 * If you are looking for production-ready output files, see mode: "production" (https://webpack.js.org/configuration/mode/).
 */
exports.id = "vendor-chunks/hast-util-has-property";
exports.ids = ["vendor-chunks/hast-util-has-property"];
exports.modules = {

/***/ "(ssr)/./node_modules/hast-util-has-property/lib/index.js":
/*!**********************************************************!*\
  !*** ./node_modules/hast-util-has-property/lib/index.js ***!
  \**********************************************************/
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {

eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   hasProperty: () => (/* binding */ hasProperty)\n/* harmony export */ });\n/**\n * @typedef {import('hast').Root} Root\n * @typedef {import('hast').Content} Content\n */\n\n/**\n * @typedef {Root | Content} Node\n */\n\nconst own = {}.hasOwnProperty\n\n/**\n * Check if `node`is an element and has a `field` property.\n *\n * @param {unknown} node\n *   Thing to check (typically `Element`).\n * @param {unknown} field\n *   Field name to check (typically `string`).\n * @returns {boolean}\n *   Whether `node` is an element that has a `field` property.\n */\nfunction hasProperty(node, field) {\n  const value =\n    typeof field === 'string' &&\n    isNode(node) &&\n    node.type === 'element' &&\n    node.properties &&\n    own.call(node.properties, field) &&\n    node.properties[field]\n\n  return value !== null && value !== undefined && value !== false\n}\n\n/**\n * @param {unknown} value\n * @returns {value is Node}\n */\nfunction isNode(value) {\n  return Boolean(value && typeof value === 'object' && 'type' in value)\n}\n//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHNzcikvLi9ub2RlX21vZHVsZXMvaGFzdC11dGlsLWhhcy1wcm9wZXJ0eS9saWIvaW5kZXguanMiLCJtYXBwaW5ncyI6Ijs7OztBQUFBO0FBQ0EsYUFBYSxxQkFBcUI7QUFDbEMsYUFBYSx3QkFBd0I7QUFDckM7O0FBRUE7QUFDQSxhQUFhLGdCQUFnQjtBQUM3Qjs7QUFFQSxjQUFjOztBQUVkO0FBQ0E7QUFDQTtBQUNBLFdBQVcsU0FBUztBQUNwQjtBQUNBLFdBQVcsU0FBUztBQUNwQjtBQUNBLGFBQWE7QUFDYjtBQUNBO0FBQ087QUFDUDtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTs7QUFFQTtBQUNBOztBQUVBO0FBQ0EsV0FBVyxTQUFTO0FBQ3BCLGFBQWE7QUFDYjtBQUNBO0FBQ0E7QUFDQSIsInNvdXJjZXMiOlsid2VicGFjazovL0BsaXZlYmxvY2tzLWV4YW1wbGVzL25leHRqcy15anMtYmxvY2tub3RlLWFkdmFuY2VkLy4vbm9kZV9tb2R1bGVzL2hhc3QtdXRpbC1oYXMtcHJvcGVydHkvbGliL2luZGV4LmpzP2ViODAiXSwic291cmNlc0NvbnRlbnQiOlsiLyoqXG4gKiBAdHlwZWRlZiB7aW1wb3J0KCdoYXN0JykuUm9vdH0gUm9vdFxuICogQHR5cGVkZWYge2ltcG9ydCgnaGFzdCcpLkNvbnRlbnR9IENvbnRlbnRcbiAqL1xuXG4vKipcbiAqIEB0eXBlZGVmIHtSb290IHwgQ29udGVudH0gTm9kZVxuICovXG5cbmNvbnN0IG93biA9IHt9Lmhhc093blByb3BlcnR5XG5cbi8qKlxuICogQ2hlY2sgaWYgYG5vZGVgaXMgYW4gZWxlbWVudCBhbmQgaGFzIGEgYGZpZWxkYCBwcm9wZXJ0eS5cbiAqXG4gKiBAcGFyYW0ge3Vua25vd259IG5vZGVcbiAqICAgVGhpbmcgdG8gY2hlY2sgKHR5cGljYWxseSBgRWxlbWVudGApLlxuICogQHBhcmFtIHt1bmtub3dufSBmaWVsZFxuICogICBGaWVsZCBuYW1lIHRvIGNoZWNrICh0eXBpY2FsbHkgYHN0cmluZ2ApLlxuICogQHJldHVybnMge2Jvb2xlYW59XG4gKiAgIFdoZXRoZXIgYG5vZGVgIGlzIGFuIGVsZW1lbnQgdGhhdCBoYXMgYSBgZmllbGRgIHByb3BlcnR5LlxuICovXG5leHBvcnQgZnVuY3Rpb24gaGFzUHJvcGVydHkobm9kZSwgZmllbGQpIHtcbiAgY29uc3QgdmFsdWUgPVxuICAgIHR5cGVvZiBmaWVsZCA9PT0gJ3N0cmluZycgJiZcbiAgICBpc05vZGUobm9kZSkgJiZcbiAgICBub2RlLnR5cGUgPT09ICdlbGVtZW50JyAmJlxuICAgIG5vZGUucHJvcGVydGllcyAmJlxuICAgIG93bi5jYWxsKG5vZGUucHJvcGVydGllcywgZmllbGQpICYmXG4gICAgbm9kZS5wcm9wZXJ0aWVzW2ZpZWxkXVxuXG4gIHJldHVybiB2YWx1ZSAhPT0gbnVsbCAmJiB2YWx1ZSAhPT0gdW5kZWZpbmVkICYmIHZhbHVlICE9PSBmYWxzZVxufVxuXG4vKipcbiAqIEBwYXJhbSB7dW5rbm93bn0gdmFsdWVcbiAqIEByZXR1cm5zIHt2YWx1ZSBpcyBOb2RlfVxuICovXG5mdW5jdGlvbiBpc05vZGUodmFsdWUpIHtcbiAgcmV0dXJuIEJvb2xlYW4odmFsdWUgJiYgdHlwZW9mIHZhbHVlID09PSAnb2JqZWN0JyAmJiAndHlwZScgaW4gdmFsdWUpXG59XG4iXSwibmFtZXMiOltdLCJzb3VyY2VSb290IjoiIn0=\n//# sourceURL=webpack-internal:///(ssr)/./node_modules/hast-util-has-property/lib/index.js\n");

/***/ })

};
;