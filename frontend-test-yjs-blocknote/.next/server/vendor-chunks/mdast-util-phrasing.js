"use strict";
/*
 * ATTENTION: An "eval-source-map" devtool has been used.
 * This devtool is neither made for production nor for readable output files.
 * It uses "eval()" calls to create a separate source file with attached SourceMaps in the browser devtools.
 * If you are trying to read the output file, select a different devtool (https://webpack.js.org/configuration/devtool/)
 * or disable the default devtool with "devtool: false".
 * If you are looking for production-ready output files, see mode: "production" (https://webpack.js.org/configuration/mode/).
 */
exports.id = "vendor-chunks/mdast-util-phrasing";
exports.ids = ["vendor-chunks/mdast-util-phrasing"];
exports.modules = {

/***/ "(ssr)/./node_modules/mdast-util-phrasing/lib/index.js":
/*!*******************************************************!*\
  !*** ./node_modules/mdast-util-phrasing/lib/index.js ***!
  \*******************************************************/
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {

eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   phrasing: () => (/* binding */ phrasing)\n/* harmony export */ });\n/* harmony import */ var unist_util_is__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! unist-util-is */ \"(ssr)/./node_modules/unist-util-is/lib/index.js\");\n/**\n * @typedef {import('mdast').PhrasingContent} PhrasingContent\n * @typedef {import('unist-util-is').AssertPredicate<PhrasingContent>} AssertPredicatePhrasing\n */\n\n\n\n/**\n * Check if the given value is *phrasing content*.\n *\n * @param\n *   Thing to check, typically `Node`.\n * @returns\n *   Whether `value` is phrasing content.\n */\nconst phrasing = /** @type {AssertPredicatePhrasing} */ (\n  (0,unist_util_is__WEBPACK_IMPORTED_MODULE_0__.convert)([\n    'break',\n    'delete',\n    'emphasis',\n    'footnote',\n    'footnoteReference',\n    'image',\n    'imageReference',\n    'inlineCode',\n    'link',\n    'linkReference',\n    'strong',\n    'text'\n  ])\n)\n//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHNzcikvLi9ub2RlX21vZHVsZXMvbWRhc3QtdXRpbC1waHJhc2luZy9saWIvaW5kZXguanMiLCJtYXBwaW5ncyI6Ijs7Ozs7QUFBQTtBQUNBLGFBQWEsaUNBQWlDO0FBQzlDLGFBQWEsMERBQTBEO0FBQ3ZFOztBQUVxQzs7QUFFckM7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNPLDRCQUE0Qix5QkFBeUI7QUFDNUQsRUFBRSxzREFBTztBQUNUO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0EiLCJzb3VyY2VzIjpbIndlYnBhY2s6Ly9AbGl2ZWJsb2Nrcy1leGFtcGxlcy9uZXh0anMteWpzLWJsb2Nrbm90ZS1hZHZhbmNlZC8uL25vZGVfbW9kdWxlcy9tZGFzdC11dGlsLXBocmFzaW5nL2xpYi9pbmRleC5qcz8zNmEyIl0sInNvdXJjZXNDb250ZW50IjpbIi8qKlxuICogQHR5cGVkZWYge2ltcG9ydCgnbWRhc3QnKS5QaHJhc2luZ0NvbnRlbnR9IFBocmFzaW5nQ29udGVudFxuICogQHR5cGVkZWYge2ltcG9ydCgndW5pc3QtdXRpbC1pcycpLkFzc2VydFByZWRpY2F0ZTxQaHJhc2luZ0NvbnRlbnQ+fSBBc3NlcnRQcmVkaWNhdGVQaHJhc2luZ1xuICovXG5cbmltcG9ydCB7Y29udmVydH0gZnJvbSAndW5pc3QtdXRpbC1pcydcblxuLyoqXG4gKiBDaGVjayBpZiB0aGUgZ2l2ZW4gdmFsdWUgaXMgKnBocmFzaW5nIGNvbnRlbnQqLlxuICpcbiAqIEBwYXJhbVxuICogICBUaGluZyB0byBjaGVjaywgdHlwaWNhbGx5IGBOb2RlYC5cbiAqIEByZXR1cm5zXG4gKiAgIFdoZXRoZXIgYHZhbHVlYCBpcyBwaHJhc2luZyBjb250ZW50LlxuICovXG5leHBvcnQgY29uc3QgcGhyYXNpbmcgPSAvKiogQHR5cGUge0Fzc2VydFByZWRpY2F0ZVBocmFzaW5nfSAqLyAoXG4gIGNvbnZlcnQoW1xuICAgICdicmVhaycsXG4gICAgJ2RlbGV0ZScsXG4gICAgJ2VtcGhhc2lzJyxcbiAgICAnZm9vdG5vdGUnLFxuICAgICdmb290bm90ZVJlZmVyZW5jZScsXG4gICAgJ2ltYWdlJyxcbiAgICAnaW1hZ2VSZWZlcmVuY2UnLFxuICAgICdpbmxpbmVDb2RlJyxcbiAgICAnbGluaycsXG4gICAgJ2xpbmtSZWZlcmVuY2UnLFxuICAgICdzdHJvbmcnLFxuICAgICd0ZXh0J1xuICBdKVxuKVxuIl0sIm5hbWVzIjpbXSwic291cmNlUm9vdCI6IiJ9\n//# sourceURL=webpack-internal:///(ssr)/./node_modules/mdast-util-phrasing/lib/index.js\n");

/***/ })

};
;