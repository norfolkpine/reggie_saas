"use strict";
/*
 * ATTENTION: An "eval-source-map" devtool has been used.
 * This devtool is neither made for production nor for readable output files.
 * It uses "eval()" calls to create a separate source file with attached SourceMaps in the browser devtools.
 * If you are trying to read the output file, select a different devtool (https://webpack.js.org/configuration/devtool/)
 * or disable the default devtool with "devtool: false".
 * If you are looking for production-ready output files, see mode: "production" (https://webpack.js.org/configuration/mode/).
 */
exports.id = "vendor-chunks/trim-trailing-lines";
exports.ids = ["vendor-chunks/trim-trailing-lines"];
exports.modules = {

/***/ "(ssr)/./node_modules/trim-trailing-lines/index.js":
/*!***************************************************!*\
  !*** ./node_modules/trim-trailing-lines/index.js ***!
  \***************************************************/
/***/ ((__unused_webpack___webpack_module__, __webpack_exports__, __webpack_require__) => {

eval("__webpack_require__.r(__webpack_exports__);\n/* harmony export */ __webpack_require__.d(__webpack_exports__, {\n/* harmony export */   trimTrailingLines: () => (/* binding */ trimTrailingLines)\n/* harmony export */ });\n/**\n * Remove final line endings from `value`\n *\n * @param {unknown} value\n *   Value with trailing line endings, coerced to string.\n * @return {string}\n *   Value without trailing line endings.\n */\nfunction trimTrailingLines(value) {\n  const input = String(value)\n  let end = input.length\n\n  while (end > 0) {\n    const code = input.codePointAt(end - 1)\n    if (code !== undefined && (code === 10 || code === 13)) {\n      end--\n    } else {\n      break\n    }\n  }\n\n  return input.slice(0, end)\n}\n//# sourceURL=[module]\n//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiKHNzcikvLi9ub2RlX21vZHVsZXMvdHJpbS10cmFpbGluZy1saW5lcy9pbmRleC5qcyIsIm1hcHBpbmdzIjoiOzs7O0FBQUE7QUFDQTtBQUNBO0FBQ0EsV0FBVyxTQUFTO0FBQ3BCO0FBQ0EsWUFBWTtBQUNaO0FBQ0E7QUFDTztBQUNQO0FBQ0E7O0FBRUE7QUFDQTtBQUNBO0FBQ0E7QUFDQSxNQUFNO0FBQ047QUFDQTtBQUNBOztBQUVBO0FBQ0EiLCJzb3VyY2VzIjpbIndlYnBhY2s6Ly9AbGl2ZWJsb2Nrcy1leGFtcGxlcy9uZXh0anMteWpzLWJsb2Nrbm90ZS1hZHZhbmNlZC8uL25vZGVfbW9kdWxlcy90cmltLXRyYWlsaW5nLWxpbmVzL2luZGV4LmpzPzlkNzciXSwic291cmNlc0NvbnRlbnQiOlsiLyoqXG4gKiBSZW1vdmUgZmluYWwgbGluZSBlbmRpbmdzIGZyb20gYHZhbHVlYFxuICpcbiAqIEBwYXJhbSB7dW5rbm93bn0gdmFsdWVcbiAqICAgVmFsdWUgd2l0aCB0cmFpbGluZyBsaW5lIGVuZGluZ3MsIGNvZXJjZWQgdG8gc3RyaW5nLlxuICogQHJldHVybiB7c3RyaW5nfVxuICogICBWYWx1ZSB3aXRob3V0IHRyYWlsaW5nIGxpbmUgZW5kaW5ncy5cbiAqL1xuZXhwb3J0IGZ1bmN0aW9uIHRyaW1UcmFpbGluZ0xpbmVzKHZhbHVlKSB7XG4gIGNvbnN0IGlucHV0ID0gU3RyaW5nKHZhbHVlKVxuICBsZXQgZW5kID0gaW5wdXQubGVuZ3RoXG5cbiAgd2hpbGUgKGVuZCA+IDApIHtcbiAgICBjb25zdCBjb2RlID0gaW5wdXQuY29kZVBvaW50QXQoZW5kIC0gMSlcbiAgICBpZiAoY29kZSAhPT0gdW5kZWZpbmVkICYmIChjb2RlID09PSAxMCB8fCBjb2RlID09PSAxMykpIHtcbiAgICAgIGVuZC0tXG4gICAgfSBlbHNlIHtcbiAgICAgIGJyZWFrXG4gICAgfVxuICB9XG5cbiAgcmV0dXJuIGlucHV0LnNsaWNlKDAsIGVuZClcbn1cbiJdLCJuYW1lcyI6W10sInNvdXJjZVJvb3QiOiIifQ==\n//# sourceURL=webpack-internal:///(ssr)/./node_modules/trim-trailing-lines/index.js\n");

/***/ })

};
;