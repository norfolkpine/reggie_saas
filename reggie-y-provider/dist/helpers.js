export var promiseDone = function () {
    var done = function () { };
    var promise = new Promise(function (resolve) {
        done = resolve;
    });
    return { done: done, promise: promise };
};
