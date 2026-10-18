var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __commonJS = (cb, mod) => function __require() {
  return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// node_modules/react/cjs/react.production.min.js
var require_react_production_min = __commonJS({
  "node_modules/react/cjs/react.production.min.js"(exports2) {
    "use strict";
    var l = Symbol.for("react.element");
    var n = Symbol.for("react.portal");
    var p = Symbol.for("react.fragment");
    var q = Symbol.for("react.strict_mode");
    var r = Symbol.for("react.profiler");
    var t = Symbol.for("react.provider");
    var u = Symbol.for("react.context");
    var v = Symbol.for("react.forward_ref");
    var w = Symbol.for("react.suspense");
    var x = Symbol.for("react.memo");
    var y = Symbol.for("react.lazy");
    var z = Symbol.iterator;
    function A(a) {
      if (null === a || "object" !== typeof a) return null;
      a = z && a[z] || a["@@iterator"];
      return "function" === typeof a ? a : null;
    }
    var B = { isMounted: function() {
      return false;
    }, enqueueForceUpdate: function() {
    }, enqueueReplaceState: function() {
    }, enqueueSetState: function() {
    } };
    var C = Object.assign;
    var D = {};
    function E(a, b, e) {
      this.props = a;
      this.context = b;
      this.refs = D;
      this.updater = e || B;
    }
    E.prototype.isReactComponent = {};
    E.prototype.setState = function(a, b) {
      if ("object" !== typeof a && "function" !== typeof a && null != a) throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");
      this.updater.enqueueSetState(this, a, b, "setState");
    };
    E.prototype.forceUpdate = function(a) {
      this.updater.enqueueForceUpdate(this, a, "forceUpdate");
    };
    function F() {
    }
    F.prototype = E.prototype;
    function G(a, b, e) {
      this.props = a;
      this.context = b;
      this.refs = D;
      this.updater = e || B;
    }
    var H = G.prototype = new F();
    H.constructor = G;
    C(H, E.prototype);
    H.isPureReactComponent = true;
    var I = Array.isArray;
    var J = Object.prototype.hasOwnProperty;
    var K = { current: null };
    var L = { key: true, ref: true, __self: true, __source: true };
    function M(a, b, e) {
      var d, c = {}, k = null, h = null;
      if (null != b) for (d in void 0 !== b.ref && (h = b.ref), void 0 !== b.key && (k = "" + b.key), b) J.call(b, d) && !L.hasOwnProperty(d) && (c[d] = b[d]);
      var g = arguments.length - 2;
      if (1 === g) c.children = e;
      else if (1 < g) {
        for (var f = Array(g), m = 0; m < g; m++) f[m] = arguments[m + 2];
        c.children = f;
      }
      if (a && a.defaultProps) for (d in g = a.defaultProps, g) void 0 === c[d] && (c[d] = g[d]);
      return { $$typeof: l, type: a, key: k, ref: h, props: c, _owner: K.current };
    }
    function N(a, b) {
      return { $$typeof: l, type: a.type, key: b, ref: a.ref, props: a.props, _owner: a._owner };
    }
    function O(a) {
      return "object" === typeof a && null !== a && a.$$typeof === l;
    }
    function escape(a) {
      var b = { "=": "=0", ":": "=2" };
      return "$" + a.replace(/[=:]/g, function(a2) {
        return b[a2];
      });
    }
    var P = /\/+/g;
    function Q(a, b) {
      return "object" === typeof a && null !== a && null != a.key ? escape("" + a.key) : b.toString(36);
    }
    function R(a, b, e, d, c) {
      var k = typeof a;
      if ("undefined" === k || "boolean" === k) a = null;
      var h = false;
      if (null === a) h = true;
      else switch (k) {
        case "string":
        case "number":
          h = true;
          break;
        case "object":
          switch (a.$$typeof) {
            case l:
            case n:
              h = true;
          }
      }
      if (h) return h = a, c = c(h), a = "" === d ? "." + Q(h, 0) : d, I(c) ? (e = "", null != a && (e = a.replace(P, "$&/") + "/"), R(c, b, e, "", function(a2) {
        return a2;
      })) : null != c && (O(c) && (c = N(c, e + (!c.key || h && h.key === c.key ? "" : ("" + c.key).replace(P, "$&/") + "/") + a)), b.push(c)), 1;
      h = 0;
      d = "" === d ? "." : d + ":";
      if (I(a)) for (var g = 0; g < a.length; g++) {
        k = a[g];
        var f = d + Q(k, g);
        h += R(k, b, e, f, c);
      }
      else if (f = A(a), "function" === typeof f) for (a = f.call(a), g = 0; !(k = a.next()).done; ) k = k.value, f = d + Q(k, g++), h += R(k, b, e, f, c);
      else if ("object" === k) throw b = String(a), Error("Objects are not valid as a React child (found: " + ("[object Object]" === b ? "object with keys {" + Object.keys(a).join(", ") + "}" : b) + "). If you meant to render a collection of children, use an array instead.");
      return h;
    }
    function S(a, b, e) {
      if (null == a) return a;
      var d = [], c = 0;
      R(a, d, "", "", function(a2) {
        return b.call(e, a2, c++);
      });
      return d;
    }
    function T(a) {
      if (-1 === a._status) {
        var b = a._result;
        b = b();
        b.then(function(b2) {
          if (0 === a._status || -1 === a._status) a._status = 1, a._result = b2;
        }, function(b2) {
          if (0 === a._status || -1 === a._status) a._status = 2, a._result = b2;
        });
        -1 === a._status && (a._status = 0, a._result = b);
      }
      if (1 === a._status) return a._result.default;
      throw a._result;
    }
    var U = { current: null };
    var V = { transition: null };
    var W = { ReactCurrentDispatcher: U, ReactCurrentBatchConfig: V, ReactCurrentOwner: K };
    function X() {
      throw Error("act(...) is not supported in production builds of React.");
    }
    exports2.Children = { map: S, forEach: function(a, b, e) {
      S(a, function() {
        b.apply(this, arguments);
      }, e);
    }, count: function(a) {
      var b = 0;
      S(a, function() {
        b++;
      });
      return b;
    }, toArray: function(a) {
      return S(a, function(a2) {
        return a2;
      }) || [];
    }, only: function(a) {
      if (!O(a)) throw Error("React.Children.only expected to receive a single React element child.");
      return a;
    } };
    exports2.Component = E;
    exports2.Fragment = p;
    exports2.Profiler = r;
    exports2.PureComponent = G;
    exports2.StrictMode = q;
    exports2.Suspense = w;
    exports2.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = W;
    exports2.act = X;
    exports2.cloneElement = function(a, b, e) {
      if (null === a || void 0 === a) throw Error("React.cloneElement(...): The argument must be a React element, but you passed " + a + ".");
      var d = C({}, a.props), c = a.key, k = a.ref, h = a._owner;
      if (null != b) {
        void 0 !== b.ref && (k = b.ref, h = K.current);
        void 0 !== b.key && (c = "" + b.key);
        if (a.type && a.type.defaultProps) var g = a.type.defaultProps;
        for (f in b) J.call(b, f) && !L.hasOwnProperty(f) && (d[f] = void 0 === b[f] && void 0 !== g ? g[f] : b[f]);
      }
      var f = arguments.length - 2;
      if (1 === f) d.children = e;
      else if (1 < f) {
        g = Array(f);
        for (var m = 0; m < f; m++) g[m] = arguments[m + 2];
        d.children = g;
      }
      return { $$typeof: l, type: a.type, key: c, ref: k, props: d, _owner: h };
    };
    exports2.createContext = function(a) {
      a = { $$typeof: u, _currentValue: a, _currentValue2: a, _threadCount: 0, Provider: null, Consumer: null, _defaultValue: null, _globalName: null };
      a.Provider = { $$typeof: t, _context: a };
      return a.Consumer = a;
    };
    exports2.createElement = M;
    exports2.createFactory = function(a) {
      var b = M.bind(null, a);
      b.type = a;
      return b;
    };
    exports2.createRef = function() {
      return { current: null };
    };
    exports2.forwardRef = function(a) {
      return { $$typeof: v, render: a };
    };
    exports2.isValidElement = O;
    exports2.lazy = function(a) {
      return { $$typeof: y, _payload: { _status: -1, _result: a }, _init: T };
    };
    exports2.memo = function(a, b) {
      return { $$typeof: x, type: a, compare: void 0 === b ? null : b };
    };
    exports2.startTransition = function(a) {
      var b = V.transition;
      V.transition = {};
      try {
        a();
      } finally {
        V.transition = b;
      }
    };
    exports2.unstable_act = X;
    exports2.useCallback = function(a, b) {
      return U.current.useCallback(a, b);
    };
    exports2.useContext = function(a) {
      return U.current.useContext(a);
    };
    exports2.useDebugValue = function() {
    };
    exports2.useDeferredValue = function(a) {
      return U.current.useDeferredValue(a);
    };
    exports2.useEffect = function(a, b) {
      return U.current.useEffect(a, b);
    };
    exports2.useId = function() {
      return U.current.useId();
    };
    exports2.useImperativeHandle = function(a, b, e) {
      return U.current.useImperativeHandle(a, b, e);
    };
    exports2.useInsertionEffect = function(a, b) {
      return U.current.useInsertionEffect(a, b);
    };
    exports2.useLayoutEffect = function(a, b) {
      return U.current.useLayoutEffect(a, b);
    };
    exports2.useMemo = function(a, b) {
      return U.current.useMemo(a, b);
    };
    exports2.useReducer = function(a, b, e) {
      return U.current.useReducer(a, b, e);
    };
    exports2.useRef = function(a) {
      return U.current.useRef(a);
    };
    exports2.useState = function(a) {
      return U.current.useState(a);
    };
    exports2.useSyncExternalStore = function(a, b, e) {
      return U.current.useSyncExternalStore(a, b, e);
    };
    exports2.useTransition = function() {
      return U.current.useTransition();
    };
    exports2.version = "18.3.1";
  }
});

// node_modules/react/cjs/react.development.js
var require_react_development = __commonJS({
  "node_modules/react/cjs/react.development.js"(exports2, module2) {
    "use strict";
    if (process.env.NODE_ENV !== "production") {
      (function() {
        "use strict";
        if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ !== "undefined" && typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.registerInternalModuleStart === "function") {
          __REACT_DEVTOOLS_GLOBAL_HOOK__.registerInternalModuleStart(new Error());
        }
        var ReactVersion = "18.3.1";
        var REACT_ELEMENT_TYPE = Symbol.for("react.element");
        var REACT_PORTAL_TYPE = Symbol.for("react.portal");
        var REACT_FRAGMENT_TYPE = Symbol.for("react.fragment");
        var REACT_STRICT_MODE_TYPE = Symbol.for("react.strict_mode");
        var REACT_PROFILER_TYPE = Symbol.for("react.profiler");
        var REACT_PROVIDER_TYPE = Symbol.for("react.provider");
        var REACT_CONTEXT_TYPE = Symbol.for("react.context");
        var REACT_FORWARD_REF_TYPE = Symbol.for("react.forward_ref");
        var REACT_SUSPENSE_TYPE = Symbol.for("react.suspense");
        var REACT_SUSPENSE_LIST_TYPE = Symbol.for("react.suspense_list");
        var REACT_MEMO_TYPE = Symbol.for("react.memo");
        var REACT_LAZY_TYPE = Symbol.for("react.lazy");
        var REACT_OFFSCREEN_TYPE = Symbol.for("react.offscreen");
        var MAYBE_ITERATOR_SYMBOL = Symbol.iterator;
        var FAUX_ITERATOR_SYMBOL = "@@iterator";
        function getIteratorFn(maybeIterable) {
          if (maybeIterable === null || typeof maybeIterable !== "object") {
            return null;
          }
          var maybeIterator = MAYBE_ITERATOR_SYMBOL && maybeIterable[MAYBE_ITERATOR_SYMBOL] || maybeIterable[FAUX_ITERATOR_SYMBOL];
          if (typeof maybeIterator === "function") {
            return maybeIterator;
          }
          return null;
        }
        var ReactCurrentDispatcher = {
          /**
           * @internal
           * @type {ReactComponent}
           */
          current: null
        };
        var ReactCurrentBatchConfig = {
          transition: null
        };
        var ReactCurrentActQueue = {
          current: null,
          // Used to reproduce behavior of `batchedUpdates` in legacy mode.
          isBatchingLegacy: false,
          didScheduleLegacyUpdate: false
        };
        var ReactCurrentOwner = {
          /**
           * @internal
           * @type {ReactComponent}
           */
          current: null
        };
        var ReactDebugCurrentFrame = {};
        var currentExtraStackFrame = null;
        function setExtraStackFrame(stack) {
          {
            currentExtraStackFrame = stack;
          }
        }
        {
          ReactDebugCurrentFrame.setExtraStackFrame = function(stack) {
            {
              currentExtraStackFrame = stack;
            }
          };
          ReactDebugCurrentFrame.getCurrentStack = null;
          ReactDebugCurrentFrame.getStackAddendum = function() {
            var stack = "";
            if (currentExtraStackFrame) {
              stack += currentExtraStackFrame;
            }
            var impl = ReactDebugCurrentFrame.getCurrentStack;
            if (impl) {
              stack += impl() || "";
            }
            return stack;
          };
        }
        var enableScopeAPI = false;
        var enableCacheElement = false;
        var enableTransitionTracing = false;
        var enableLegacyHidden = false;
        var enableDebugTracing = false;
        var ReactSharedInternals = {
          ReactCurrentDispatcher,
          ReactCurrentBatchConfig,
          ReactCurrentOwner
        };
        {
          ReactSharedInternals.ReactDebugCurrentFrame = ReactDebugCurrentFrame;
          ReactSharedInternals.ReactCurrentActQueue = ReactCurrentActQueue;
        }
        function warn(format) {
          {
            {
              for (var _len = arguments.length, args = new Array(_len > 1 ? _len - 1 : 0), _key = 1; _key < _len; _key++) {
                args[_key - 1] = arguments[_key];
              }
              printWarning("warn", format, args);
            }
          }
        }
        function error(format) {
          {
            {
              for (var _len2 = arguments.length, args = new Array(_len2 > 1 ? _len2 - 1 : 0), _key2 = 1; _key2 < _len2; _key2++) {
                args[_key2 - 1] = arguments[_key2];
              }
              printWarning("error", format, args);
            }
          }
        }
        function printWarning(level, format, args) {
          {
            var ReactDebugCurrentFrame2 = ReactSharedInternals.ReactDebugCurrentFrame;
            var stack = ReactDebugCurrentFrame2.getStackAddendum();
            if (stack !== "") {
              format += "%s";
              args = args.concat([stack]);
            }
            var argsWithFormat = args.map(function(item) {
              return String(item);
            });
            argsWithFormat.unshift("Warning: " + format);
            Function.prototype.apply.call(console[level], console, argsWithFormat);
          }
        }
        var didWarnStateUpdateForUnmountedComponent = {};
        function warnNoop(publicInstance, callerName) {
          {
            var _constructor = publicInstance.constructor;
            var componentName = _constructor && (_constructor.displayName || _constructor.name) || "ReactClass";
            var warningKey = componentName + "." + callerName;
            if (didWarnStateUpdateForUnmountedComponent[warningKey]) {
              return;
            }
            error("Can't call %s on a component that is not yet mounted. This is a no-op, but it might indicate a bug in your application. Instead, assign to `this.state` directly or define a `state = {};` class property with the desired state in the %s component.", callerName, componentName);
            didWarnStateUpdateForUnmountedComponent[warningKey] = true;
          }
        }
        var ReactNoopUpdateQueue = {
          /**
           * Checks whether or not this composite component is mounted.
           * @param {ReactClass} publicInstance The instance we want to test.
           * @return {boolean} True if mounted, false otherwise.
           * @protected
           * @final
           */
          isMounted: function(publicInstance) {
            return false;
          },
          /**
           * Forces an update. This should only be invoked when it is known with
           * certainty that we are **not** in a DOM transaction.
           *
           * You may want to call this when you know that some deeper aspect of the
           * component's state has changed but `setState` was not called.
           *
           * This will not invoke `shouldComponentUpdate`, but it will invoke
           * `componentWillUpdate` and `componentDidUpdate`.
           *
           * @param {ReactClass} publicInstance The instance that should rerender.
           * @param {?function} callback Called after component is updated.
           * @param {?string} callerName name of the calling function in the public API.
           * @internal
           */
          enqueueForceUpdate: function(publicInstance, callback, callerName) {
            warnNoop(publicInstance, "forceUpdate");
          },
          /**
           * Replaces all of the state. Always use this or `setState` to mutate state.
           * You should treat `this.state` as immutable.
           *
           * There is no guarantee that `this.state` will be immediately updated, so
           * accessing `this.state` after calling this method may return the old value.
           *
           * @param {ReactClass} publicInstance The instance that should rerender.
           * @param {object} completeState Next state.
           * @param {?function} callback Called after component is updated.
           * @param {?string} callerName name of the calling function in the public API.
           * @internal
           */
          enqueueReplaceState: function(publicInstance, completeState, callback, callerName) {
            warnNoop(publicInstance, "replaceState");
          },
          /**
           * Sets a subset of the state. This only exists because _pendingState is
           * internal. This provides a merging strategy that is not available to deep
           * properties which is confusing. TODO: Expose pendingState or don't use it
           * during the merge.
           *
           * @param {ReactClass} publicInstance The instance that should rerender.
           * @param {object} partialState Next partial state to be merged with state.
           * @param {?function} callback Called after component is updated.
           * @param {?string} Name of the calling function in the public API.
           * @internal
           */
          enqueueSetState: function(publicInstance, partialState, callback, callerName) {
            warnNoop(publicInstance, "setState");
          }
        };
        var assign = Object.assign;
        var emptyObject = {};
        {
          Object.freeze(emptyObject);
        }
        function Component(props, context, updater) {
          this.props = props;
          this.context = context;
          this.refs = emptyObject;
          this.updater = updater || ReactNoopUpdateQueue;
        }
        Component.prototype.isReactComponent = {};
        Component.prototype.setState = function(partialState, callback) {
          if (typeof partialState !== "object" && typeof partialState !== "function" && partialState != null) {
            throw new Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");
          }
          this.updater.enqueueSetState(this, partialState, callback, "setState");
        };
        Component.prototype.forceUpdate = function(callback) {
          this.updater.enqueueForceUpdate(this, callback, "forceUpdate");
        };
        {
          var deprecatedAPIs = {
            isMounted: ["isMounted", "Instead, make sure to clean up subscriptions and pending requests in componentWillUnmount to prevent memory leaks."],
            replaceState: ["replaceState", "Refactor your code to use setState instead (see https://github.com/facebook/react/issues/3236)."]
          };
          var defineDeprecationWarning = function(methodName, info) {
            Object.defineProperty(Component.prototype, methodName, {
              get: function() {
                warn("%s(...) is deprecated in plain JavaScript React classes. %s", info[0], info[1]);
                return void 0;
              }
            });
          };
          for (var fnName in deprecatedAPIs) {
            if (deprecatedAPIs.hasOwnProperty(fnName)) {
              defineDeprecationWarning(fnName, deprecatedAPIs[fnName]);
            }
          }
        }
        function ComponentDummy() {
        }
        ComponentDummy.prototype = Component.prototype;
        function PureComponent(props, context, updater) {
          this.props = props;
          this.context = context;
          this.refs = emptyObject;
          this.updater = updater || ReactNoopUpdateQueue;
        }
        var pureComponentPrototype = PureComponent.prototype = new ComponentDummy();
        pureComponentPrototype.constructor = PureComponent;
        assign(pureComponentPrototype, Component.prototype);
        pureComponentPrototype.isPureReactComponent = true;
        function createRef() {
          var refObject = {
            current: null
          };
          {
            Object.seal(refObject);
          }
          return refObject;
        }
        var isArrayImpl = Array.isArray;
        function isArray(a) {
          return isArrayImpl(a);
        }
        function typeName(value) {
          {
            var hasToStringTag = typeof Symbol === "function" && Symbol.toStringTag;
            var type = hasToStringTag && value[Symbol.toStringTag] || value.constructor.name || "Object";
            return type;
          }
        }
        function willCoercionThrow(value) {
          {
            try {
              testStringCoercion(value);
              return false;
            } catch (e) {
              return true;
            }
          }
        }
        function testStringCoercion(value) {
          return "" + value;
        }
        function checkKeyStringCoercion(value) {
          {
            if (willCoercionThrow(value)) {
              error("The provided key is an unsupported type %s. This value must be coerced to a string before before using it here.", typeName(value));
              return testStringCoercion(value);
            }
          }
        }
        function getWrappedName(outerType, innerType, wrapperName) {
          var displayName = outerType.displayName;
          if (displayName) {
            return displayName;
          }
          var functionName = innerType.displayName || innerType.name || "";
          return functionName !== "" ? wrapperName + "(" + functionName + ")" : wrapperName;
        }
        function getContextName(type) {
          return type.displayName || "Context";
        }
        function getComponentNameFromType(type) {
          if (type == null) {
            return null;
          }
          {
            if (typeof type.tag === "number") {
              error("Received an unexpected object in getComponentNameFromType(). This is likely a bug in React. Please file an issue.");
            }
          }
          if (typeof type === "function") {
            return type.displayName || type.name || null;
          }
          if (typeof type === "string") {
            return type;
          }
          switch (type) {
            case REACT_FRAGMENT_TYPE:
              return "Fragment";
            case REACT_PORTAL_TYPE:
              return "Portal";
            case REACT_PROFILER_TYPE:
              return "Profiler";
            case REACT_STRICT_MODE_TYPE:
              return "StrictMode";
            case REACT_SUSPENSE_TYPE:
              return "Suspense";
            case REACT_SUSPENSE_LIST_TYPE:
              return "SuspenseList";
          }
          if (typeof type === "object") {
            switch (type.$$typeof) {
              case REACT_CONTEXT_TYPE:
                var context = type;
                return getContextName(context) + ".Consumer";
              case REACT_PROVIDER_TYPE:
                var provider = type;
                return getContextName(provider._context) + ".Provider";
              case REACT_FORWARD_REF_TYPE:
                return getWrappedName(type, type.render, "ForwardRef");
              case REACT_MEMO_TYPE:
                var outerName = type.displayName || null;
                if (outerName !== null) {
                  return outerName;
                }
                return getComponentNameFromType(type.type) || "Memo";
              case REACT_LAZY_TYPE: {
                var lazyComponent = type;
                var payload = lazyComponent._payload;
                var init = lazyComponent._init;
                try {
                  return getComponentNameFromType(init(payload));
                } catch (x) {
                  return null;
                }
              }
            }
          }
          return null;
        }
        var hasOwnProperty = Object.prototype.hasOwnProperty;
        var RESERVED_PROPS = {
          key: true,
          ref: true,
          __self: true,
          __source: true
        };
        var specialPropKeyWarningShown, specialPropRefWarningShown, didWarnAboutStringRefs;
        {
          didWarnAboutStringRefs = {};
        }
        function hasValidRef(config) {
          {
            if (hasOwnProperty.call(config, "ref")) {
              var getter = Object.getOwnPropertyDescriptor(config, "ref").get;
              if (getter && getter.isReactWarning) {
                return false;
              }
            }
          }
          return config.ref !== void 0;
        }
        function hasValidKey(config) {
          {
            if (hasOwnProperty.call(config, "key")) {
              var getter = Object.getOwnPropertyDescriptor(config, "key").get;
              if (getter && getter.isReactWarning) {
                return false;
              }
            }
          }
          return config.key !== void 0;
        }
        function defineKeyPropWarningGetter(props, displayName) {
          var warnAboutAccessingKey = function() {
            {
              if (!specialPropKeyWarningShown) {
                specialPropKeyWarningShown = true;
                error("%s: `key` is not a prop. Trying to access it will result in `undefined` being returned. If you need to access the same value within the child component, you should pass it as a different prop. (https://reactjs.org/link/special-props)", displayName);
              }
            }
          };
          warnAboutAccessingKey.isReactWarning = true;
          Object.defineProperty(props, "key", {
            get: warnAboutAccessingKey,
            configurable: true
          });
        }
        function defineRefPropWarningGetter(props, displayName) {
          var warnAboutAccessingRef = function() {
            {
              if (!specialPropRefWarningShown) {
                specialPropRefWarningShown = true;
                error("%s: `ref` is not a prop. Trying to access it will result in `undefined` being returned. If you need to access the same value within the child component, you should pass it as a different prop. (https://reactjs.org/link/special-props)", displayName);
              }
            }
          };
          warnAboutAccessingRef.isReactWarning = true;
          Object.defineProperty(props, "ref", {
            get: warnAboutAccessingRef,
            configurable: true
          });
        }
        function warnIfStringRefCannotBeAutoConverted(config) {
          {
            if (typeof config.ref === "string" && ReactCurrentOwner.current && config.__self && ReactCurrentOwner.current.stateNode !== config.__self) {
              var componentName = getComponentNameFromType(ReactCurrentOwner.current.type);
              if (!didWarnAboutStringRefs[componentName]) {
                error('Component "%s" contains the string ref "%s". Support for string refs will be removed in a future major release. This case cannot be automatically converted to an arrow function. We ask you to manually fix this case by using useRef() or createRef() instead. Learn more about using refs safely here: https://reactjs.org/link/strict-mode-string-ref', componentName, config.ref);
                didWarnAboutStringRefs[componentName] = true;
              }
            }
          }
        }
        var ReactElement = function(type, key, ref, self, source, owner, props) {
          var element = {
            // This tag allows us to uniquely identify this as a React Element
            $$typeof: REACT_ELEMENT_TYPE,
            // Built-in properties that belong on the element
            type,
            key,
            ref,
            props,
            // Record the component responsible for creating this element.
            _owner: owner
          };
          {
            element._store = {};
            Object.defineProperty(element._store, "validated", {
              configurable: false,
              enumerable: false,
              writable: true,
              value: false
            });
            Object.defineProperty(element, "_self", {
              configurable: false,
              enumerable: false,
              writable: false,
              value: self
            });
            Object.defineProperty(element, "_source", {
              configurable: false,
              enumerable: false,
              writable: false,
              value: source
            });
            if (Object.freeze) {
              Object.freeze(element.props);
              Object.freeze(element);
            }
          }
          return element;
        };
        function createElement(type, config, children) {
          var propName;
          var props = {};
          var key = null;
          var ref = null;
          var self = null;
          var source = null;
          if (config != null) {
            if (hasValidRef(config)) {
              ref = config.ref;
              {
                warnIfStringRefCannotBeAutoConverted(config);
              }
            }
            if (hasValidKey(config)) {
              {
                checkKeyStringCoercion(config.key);
              }
              key = "" + config.key;
            }
            self = config.__self === void 0 ? null : config.__self;
            source = config.__source === void 0 ? null : config.__source;
            for (propName in config) {
              if (hasOwnProperty.call(config, propName) && !RESERVED_PROPS.hasOwnProperty(propName)) {
                props[propName] = config[propName];
              }
            }
          }
          var childrenLength = arguments.length - 2;
          if (childrenLength === 1) {
            props.children = children;
          } else if (childrenLength > 1) {
            var childArray = Array(childrenLength);
            for (var i = 0; i < childrenLength; i++) {
              childArray[i] = arguments[i + 2];
            }
            {
              if (Object.freeze) {
                Object.freeze(childArray);
              }
            }
            props.children = childArray;
          }
          if (type && type.defaultProps) {
            var defaultProps = type.defaultProps;
            for (propName in defaultProps) {
              if (props[propName] === void 0) {
                props[propName] = defaultProps[propName];
              }
            }
          }
          {
            if (key || ref) {
              var displayName = typeof type === "function" ? type.displayName || type.name || "Unknown" : type;
              if (key) {
                defineKeyPropWarningGetter(props, displayName);
              }
              if (ref) {
                defineRefPropWarningGetter(props, displayName);
              }
            }
          }
          return ReactElement(type, key, ref, self, source, ReactCurrentOwner.current, props);
        }
        function cloneAndReplaceKey(oldElement, newKey) {
          var newElement = ReactElement(oldElement.type, newKey, oldElement.ref, oldElement._self, oldElement._source, oldElement._owner, oldElement.props);
          return newElement;
        }
        function cloneElement(element, config, children) {
          if (element === null || element === void 0) {
            throw new Error("React.cloneElement(...): The argument must be a React element, but you passed " + element + ".");
          }
          var propName;
          var props = assign({}, element.props);
          var key = element.key;
          var ref = element.ref;
          var self = element._self;
          var source = element._source;
          var owner = element._owner;
          if (config != null) {
            if (hasValidRef(config)) {
              ref = config.ref;
              owner = ReactCurrentOwner.current;
            }
            if (hasValidKey(config)) {
              {
                checkKeyStringCoercion(config.key);
              }
              key = "" + config.key;
            }
            var defaultProps;
            if (element.type && element.type.defaultProps) {
              defaultProps = element.type.defaultProps;
            }
            for (propName in config) {
              if (hasOwnProperty.call(config, propName) && !RESERVED_PROPS.hasOwnProperty(propName)) {
                if (config[propName] === void 0 && defaultProps !== void 0) {
                  props[propName] = defaultProps[propName];
                } else {
                  props[propName] = config[propName];
                }
              }
            }
          }
          var childrenLength = arguments.length - 2;
          if (childrenLength === 1) {
            props.children = children;
          } else if (childrenLength > 1) {
            var childArray = Array(childrenLength);
            for (var i = 0; i < childrenLength; i++) {
              childArray[i] = arguments[i + 2];
            }
            props.children = childArray;
          }
          return ReactElement(element.type, key, ref, self, source, owner, props);
        }
        function isValidElement(object) {
          return typeof object === "object" && object !== null && object.$$typeof === REACT_ELEMENT_TYPE;
        }
        var SEPARATOR = ".";
        var SUBSEPARATOR = ":";
        function escape(key) {
          var escapeRegex = /[=:]/g;
          var escaperLookup = {
            "=": "=0",
            ":": "=2"
          };
          var escapedString = key.replace(escapeRegex, function(match) {
            return escaperLookup[match];
          });
          return "$" + escapedString;
        }
        var didWarnAboutMaps = false;
        var userProvidedKeyEscapeRegex = /\/+/g;
        function escapeUserProvidedKey(text) {
          return text.replace(userProvidedKeyEscapeRegex, "$&/");
        }
        function getElementKey(element, index) {
          if (typeof element === "object" && element !== null && element.key != null) {
            {
              checkKeyStringCoercion(element.key);
            }
            return escape("" + element.key);
          }
          return index.toString(36);
        }
        function mapIntoArray(children, array, escapedPrefix, nameSoFar, callback) {
          var type = typeof children;
          if (type === "undefined" || type === "boolean") {
            children = null;
          }
          var invokeCallback = false;
          if (children === null) {
            invokeCallback = true;
          } else {
            switch (type) {
              case "string":
              case "number":
                invokeCallback = true;
                break;
              case "object":
                switch (children.$$typeof) {
                  case REACT_ELEMENT_TYPE:
                  case REACT_PORTAL_TYPE:
                    invokeCallback = true;
                }
            }
          }
          if (invokeCallback) {
            var _child = children;
            var mappedChild = callback(_child);
            var childKey = nameSoFar === "" ? SEPARATOR + getElementKey(_child, 0) : nameSoFar;
            if (isArray(mappedChild)) {
              var escapedChildKey = "";
              if (childKey != null) {
                escapedChildKey = escapeUserProvidedKey(childKey) + "/";
              }
              mapIntoArray(mappedChild, array, escapedChildKey, "", function(c) {
                return c;
              });
            } else if (mappedChild != null) {
              if (isValidElement(mappedChild)) {
                {
                  if (mappedChild.key && (!_child || _child.key !== mappedChild.key)) {
                    checkKeyStringCoercion(mappedChild.key);
                  }
                }
                mappedChild = cloneAndReplaceKey(
                  mappedChild,
                  // Keep both the (mapped) and old keys if they differ, just as
                  // traverseAllChildren used to do for objects as children
                  escapedPrefix + // $FlowFixMe Flow incorrectly thinks React.Portal doesn't have a key
                  (mappedChild.key && (!_child || _child.key !== mappedChild.key) ? (
                    // $FlowFixMe Flow incorrectly thinks existing element's key can be a number
                    // eslint-disable-next-line react-internal/safe-string-coercion
                    escapeUserProvidedKey("" + mappedChild.key) + "/"
                  ) : "") + childKey
                );
              }
              array.push(mappedChild);
            }
            return 1;
          }
          var child;
          var nextName;
          var subtreeCount = 0;
          var nextNamePrefix = nameSoFar === "" ? SEPARATOR : nameSoFar + SUBSEPARATOR;
          if (isArray(children)) {
            for (var i = 0; i < children.length; i++) {
              child = children[i];
              nextName = nextNamePrefix + getElementKey(child, i);
              subtreeCount += mapIntoArray(child, array, escapedPrefix, nextName, callback);
            }
          } else {
            var iteratorFn = getIteratorFn(children);
            if (typeof iteratorFn === "function") {
              var iterableChildren = children;
              {
                if (iteratorFn === iterableChildren.entries) {
                  if (!didWarnAboutMaps) {
                    warn("Using Maps as children is not supported. Use an array of keyed ReactElements instead.");
                  }
                  didWarnAboutMaps = true;
                }
              }
              var iterator = iteratorFn.call(iterableChildren);
              var step;
              var ii = 0;
              while (!(step = iterator.next()).done) {
                child = step.value;
                nextName = nextNamePrefix + getElementKey(child, ii++);
                subtreeCount += mapIntoArray(child, array, escapedPrefix, nextName, callback);
              }
            } else if (type === "object") {
              var childrenString = String(children);
              throw new Error("Objects are not valid as a React child (found: " + (childrenString === "[object Object]" ? "object with keys {" + Object.keys(children).join(", ") + "}" : childrenString) + "). If you meant to render a collection of children, use an array instead.");
            }
          }
          return subtreeCount;
        }
        function mapChildren(children, func, context) {
          if (children == null) {
            return children;
          }
          var result = [];
          var count = 0;
          mapIntoArray(children, result, "", "", function(child) {
            return func.call(context, child, count++);
          });
          return result;
        }
        function countChildren(children) {
          var n = 0;
          mapChildren(children, function() {
            n++;
          });
          return n;
        }
        function forEachChildren(children, forEachFunc, forEachContext) {
          mapChildren(children, function() {
            forEachFunc.apply(this, arguments);
          }, forEachContext);
        }
        function toArray(children) {
          return mapChildren(children, function(child) {
            return child;
          }) || [];
        }
        function onlyChild(children) {
          if (!isValidElement(children)) {
            throw new Error("React.Children.only expected to receive a single React element child.");
          }
          return children;
        }
        function createContext(defaultValue) {
          var context = {
            $$typeof: REACT_CONTEXT_TYPE,
            // As a workaround to support multiple concurrent renderers, we categorize
            // some renderers as primary and others as secondary. We only expect
            // there to be two concurrent renderers at most: React Native (primary) and
            // Fabric (secondary); React DOM (primary) and React ART (secondary).
            // Secondary renderers store their context values on separate fields.
            _currentValue: defaultValue,
            _currentValue2: defaultValue,
            // Used to track how many concurrent renderers this context currently
            // supports within in a single renderer. Such as parallel server rendering.
            _threadCount: 0,
            // These are circular
            Provider: null,
            Consumer: null,
            // Add these to use same hidden class in VM as ServerContext
            _defaultValue: null,
            _globalName: null
          };
          context.Provider = {
            $$typeof: REACT_PROVIDER_TYPE,
            _context: context
          };
          var hasWarnedAboutUsingNestedContextConsumers = false;
          var hasWarnedAboutUsingConsumerProvider = false;
          var hasWarnedAboutDisplayNameOnConsumer = false;
          {
            var Consumer = {
              $$typeof: REACT_CONTEXT_TYPE,
              _context: context
            };
            Object.defineProperties(Consumer, {
              Provider: {
                get: function() {
                  if (!hasWarnedAboutUsingConsumerProvider) {
                    hasWarnedAboutUsingConsumerProvider = true;
                    error("Rendering <Context.Consumer.Provider> is not supported and will be removed in a future major release. Did you mean to render <Context.Provider> instead?");
                  }
                  return context.Provider;
                },
                set: function(_Provider) {
                  context.Provider = _Provider;
                }
              },
              _currentValue: {
                get: function() {
                  return context._currentValue;
                },
                set: function(_currentValue) {
                  context._currentValue = _currentValue;
                }
              },
              _currentValue2: {
                get: function() {
                  return context._currentValue2;
                },
                set: function(_currentValue2) {
                  context._currentValue2 = _currentValue2;
                }
              },
              _threadCount: {
                get: function() {
                  return context._threadCount;
                },
                set: function(_threadCount) {
                  context._threadCount = _threadCount;
                }
              },
              Consumer: {
                get: function() {
                  if (!hasWarnedAboutUsingNestedContextConsumers) {
                    hasWarnedAboutUsingNestedContextConsumers = true;
                    error("Rendering <Context.Consumer.Consumer> is not supported and will be removed in a future major release. Did you mean to render <Context.Consumer> instead?");
                  }
                  return context.Consumer;
                }
              },
              displayName: {
                get: function() {
                  return context.displayName;
                },
                set: function(displayName) {
                  if (!hasWarnedAboutDisplayNameOnConsumer) {
                    warn("Setting `displayName` on Context.Consumer has no effect. You should set it directly on the context with Context.displayName = '%s'.", displayName);
                    hasWarnedAboutDisplayNameOnConsumer = true;
                  }
                }
              }
            });
            context.Consumer = Consumer;
          }
          {
            context._currentRenderer = null;
            context._currentRenderer2 = null;
          }
          return context;
        }
        var Uninitialized = -1;
        var Pending = 0;
        var Resolved = 1;
        var Rejected = 2;
        function lazyInitializer(payload) {
          if (payload._status === Uninitialized) {
            var ctor = payload._result;
            var thenable = ctor();
            thenable.then(function(moduleObject2) {
              if (payload._status === Pending || payload._status === Uninitialized) {
                var resolved = payload;
                resolved._status = Resolved;
                resolved._result = moduleObject2;
              }
            }, function(error2) {
              if (payload._status === Pending || payload._status === Uninitialized) {
                var rejected = payload;
                rejected._status = Rejected;
                rejected._result = error2;
              }
            });
            if (payload._status === Uninitialized) {
              var pending = payload;
              pending._status = Pending;
              pending._result = thenable;
            }
          }
          if (payload._status === Resolved) {
            var moduleObject = payload._result;
            {
              if (moduleObject === void 0) {
                error("lazy: Expected the result of a dynamic import() call. Instead received: %s\n\nYour code should look like: \n  const MyComponent = lazy(() => import('./MyComponent'))\n\nDid you accidentally put curly braces around the import?", moduleObject);
              }
            }
            {
              if (!("default" in moduleObject)) {
                error("lazy: Expected the result of a dynamic import() call. Instead received: %s\n\nYour code should look like: \n  const MyComponent = lazy(() => import('./MyComponent'))", moduleObject);
              }
            }
            return moduleObject.default;
          } else {
            throw payload._result;
          }
        }
        function lazy(ctor) {
          var payload = {
            // We use these fields to store the result.
            _status: Uninitialized,
            _result: ctor
          };
          var lazyType = {
            $$typeof: REACT_LAZY_TYPE,
            _payload: payload,
            _init: lazyInitializer
          };
          {
            var defaultProps;
            var propTypes;
            Object.defineProperties(lazyType, {
              defaultProps: {
                configurable: true,
                get: function() {
                  return defaultProps;
                },
                set: function(newDefaultProps) {
                  error("React.lazy(...): It is not supported to assign `defaultProps` to a lazy component import. Either specify them where the component is defined, or create a wrapping component around it.");
                  defaultProps = newDefaultProps;
                  Object.defineProperty(lazyType, "defaultProps", {
                    enumerable: true
                  });
                }
              },
              propTypes: {
                configurable: true,
                get: function() {
                  return propTypes;
                },
                set: function(newPropTypes) {
                  error("React.lazy(...): It is not supported to assign `propTypes` to a lazy component import. Either specify them where the component is defined, or create a wrapping component around it.");
                  propTypes = newPropTypes;
                  Object.defineProperty(lazyType, "propTypes", {
                    enumerable: true
                  });
                }
              }
            });
          }
          return lazyType;
        }
        function forwardRef(render) {
          {
            if (render != null && render.$$typeof === REACT_MEMO_TYPE) {
              error("forwardRef requires a render function but received a `memo` component. Instead of forwardRef(memo(...)), use memo(forwardRef(...)).");
            } else if (typeof render !== "function") {
              error("forwardRef requires a render function but was given %s.", render === null ? "null" : typeof render);
            } else {
              if (render.length !== 0 && render.length !== 2) {
                error("forwardRef render functions accept exactly two parameters: props and ref. %s", render.length === 1 ? "Did you forget to use the ref parameter?" : "Any additional parameter will be undefined.");
              }
            }
            if (render != null) {
              if (render.defaultProps != null || render.propTypes != null) {
                error("forwardRef render functions do not support propTypes or defaultProps. Did you accidentally pass a React component?");
              }
            }
          }
          var elementType = {
            $$typeof: REACT_FORWARD_REF_TYPE,
            render
          };
          {
            var ownName;
            Object.defineProperty(elementType, "displayName", {
              enumerable: false,
              configurable: true,
              get: function() {
                return ownName;
              },
              set: function(name) {
                ownName = name;
                if (!render.name && !render.displayName) {
                  render.displayName = name;
                }
              }
            });
          }
          return elementType;
        }
        var REACT_MODULE_REFERENCE;
        {
          REACT_MODULE_REFERENCE = Symbol.for("react.module.reference");
        }
        function isValidElementType(type) {
          if (typeof type === "string" || typeof type === "function") {
            return true;
          }
          if (type === REACT_FRAGMENT_TYPE || type === REACT_PROFILER_TYPE || enableDebugTracing || type === REACT_STRICT_MODE_TYPE || type === REACT_SUSPENSE_TYPE || type === REACT_SUSPENSE_LIST_TYPE || enableLegacyHidden || type === REACT_OFFSCREEN_TYPE || enableScopeAPI || enableCacheElement || enableTransitionTracing) {
            return true;
          }
          if (typeof type === "object" && type !== null) {
            if (type.$$typeof === REACT_LAZY_TYPE || type.$$typeof === REACT_MEMO_TYPE || type.$$typeof === REACT_PROVIDER_TYPE || type.$$typeof === REACT_CONTEXT_TYPE || type.$$typeof === REACT_FORWARD_REF_TYPE || // This needs to include all possible module reference object
            // types supported by any Flight configuration anywhere since
            // we don't know which Flight build this will end up being used
            // with.
            type.$$typeof === REACT_MODULE_REFERENCE || type.getModuleId !== void 0) {
              return true;
            }
          }
          return false;
        }
        function memo(type, compare) {
          {
            if (!isValidElementType(type)) {
              error("memo: The first argument must be a component. Instead received: %s", type === null ? "null" : typeof type);
            }
          }
          var elementType = {
            $$typeof: REACT_MEMO_TYPE,
            type,
            compare: compare === void 0 ? null : compare
          };
          {
            var ownName;
            Object.defineProperty(elementType, "displayName", {
              enumerable: false,
              configurable: true,
              get: function() {
                return ownName;
              },
              set: function(name) {
                ownName = name;
                if (!type.name && !type.displayName) {
                  type.displayName = name;
                }
              }
            });
          }
          return elementType;
        }
        function resolveDispatcher() {
          var dispatcher = ReactCurrentDispatcher.current;
          {
            if (dispatcher === null) {
              error("Invalid hook call. Hooks can only be called inside of the body of a function component. This could happen for one of the following reasons:\n1. You might have mismatching versions of React and the renderer (such as React DOM)\n2. You might be breaking the Rules of Hooks\n3. You might have more than one copy of React in the same app\nSee https://reactjs.org/link/invalid-hook-call for tips about how to debug and fix this problem.");
            }
          }
          return dispatcher;
        }
        function useContext(Context) {
          var dispatcher = resolveDispatcher();
          {
            if (Context._context !== void 0) {
              var realContext = Context._context;
              if (realContext.Consumer === Context) {
                error("Calling useContext(Context.Consumer) is not supported, may cause bugs, and will be removed in a future major release. Did you mean to call useContext(Context) instead?");
              } else if (realContext.Provider === Context) {
                error("Calling useContext(Context.Provider) is not supported. Did you mean to call useContext(Context) instead?");
              }
            }
          }
          return dispatcher.useContext(Context);
        }
        function useState2(initialState) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useState(initialState);
        }
        function useReducer(reducer, initialArg, init) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useReducer(reducer, initialArg, init);
        }
        function useRef(initialValue) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useRef(initialValue);
        }
        function useEffect2(create, deps) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useEffect(create, deps);
        }
        function useInsertionEffect(create, deps) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useInsertionEffect(create, deps);
        }
        function useLayoutEffect(create, deps) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useLayoutEffect(create, deps);
        }
        function useCallback(callback, deps) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useCallback(callback, deps);
        }
        function useMemo(create, deps) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useMemo(create, deps);
        }
        function useImperativeHandle(ref, create, deps) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useImperativeHandle(ref, create, deps);
        }
        function useDebugValue(value, formatterFn) {
          {
            var dispatcher = resolveDispatcher();
            return dispatcher.useDebugValue(value, formatterFn);
          }
        }
        function useTransition() {
          var dispatcher = resolveDispatcher();
          return dispatcher.useTransition();
        }
        function useDeferredValue(value) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useDeferredValue(value);
        }
        function useId() {
          var dispatcher = resolveDispatcher();
          return dispatcher.useId();
        }
        function useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot) {
          var dispatcher = resolveDispatcher();
          return dispatcher.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
        }
        var disabledDepth = 0;
        var prevLog;
        var prevInfo;
        var prevWarn;
        var prevError;
        var prevGroup;
        var prevGroupCollapsed;
        var prevGroupEnd;
        function disabledLog() {
        }
        disabledLog.__reactDisabledLog = true;
        function disableLogs() {
          {
            if (disabledDepth === 0) {
              prevLog = console.log;
              prevInfo = console.info;
              prevWarn = console.warn;
              prevError = console.error;
              prevGroup = console.group;
              prevGroupCollapsed = console.groupCollapsed;
              prevGroupEnd = console.groupEnd;
              var props = {
                configurable: true,
                enumerable: true,
                value: disabledLog,
                writable: true
              };
              Object.defineProperties(console, {
                info: props,
                log: props,
                warn: props,
                error: props,
                group: props,
                groupCollapsed: props,
                groupEnd: props
              });
            }
            disabledDepth++;
          }
        }
        function reenableLogs() {
          {
            disabledDepth--;
            if (disabledDepth === 0) {
              var props = {
                configurable: true,
                enumerable: true,
                writable: true
              };
              Object.defineProperties(console, {
                log: assign({}, props, {
                  value: prevLog
                }),
                info: assign({}, props, {
                  value: prevInfo
                }),
                warn: assign({}, props, {
                  value: prevWarn
                }),
                error: assign({}, props, {
                  value: prevError
                }),
                group: assign({}, props, {
                  value: prevGroup
                }),
                groupCollapsed: assign({}, props, {
                  value: prevGroupCollapsed
                }),
                groupEnd: assign({}, props, {
                  value: prevGroupEnd
                })
              });
            }
            if (disabledDepth < 0) {
              error("disabledDepth fell below zero. This is a bug in React. Please file an issue.");
            }
          }
        }
        var ReactCurrentDispatcher$1 = ReactSharedInternals.ReactCurrentDispatcher;
        var prefix;
        function describeBuiltInComponentFrame(name, source, ownerFn) {
          {
            if (prefix === void 0) {
              try {
                throw Error();
              } catch (x) {
                var match = x.stack.trim().match(/\n( *(at )?)/);
                prefix = match && match[1] || "";
              }
            }
            return "\n" + prefix + name;
          }
        }
        var reentry = false;
        var componentFrameCache;
        {
          var PossiblyWeakMap = typeof WeakMap === "function" ? WeakMap : Map;
          componentFrameCache = new PossiblyWeakMap();
        }
        function describeNativeComponentFrame(fn, construct) {
          if (!fn || reentry) {
            return "";
          }
          {
            var frame = componentFrameCache.get(fn);
            if (frame !== void 0) {
              return frame;
            }
          }
          var control;
          reentry = true;
          var previousPrepareStackTrace = Error.prepareStackTrace;
          Error.prepareStackTrace = void 0;
          var previousDispatcher;
          {
            previousDispatcher = ReactCurrentDispatcher$1.current;
            ReactCurrentDispatcher$1.current = null;
            disableLogs();
          }
          try {
            if (construct) {
              var Fake = function() {
                throw Error();
              };
              Object.defineProperty(Fake.prototype, "props", {
                set: function() {
                  throw Error();
                }
              });
              if (typeof Reflect === "object" && Reflect.construct) {
                try {
                  Reflect.construct(Fake, []);
                } catch (x) {
                  control = x;
                }
                Reflect.construct(fn, [], Fake);
              } else {
                try {
                  Fake.call();
                } catch (x) {
                  control = x;
                }
                fn.call(Fake.prototype);
              }
            } else {
              try {
                throw Error();
              } catch (x) {
                control = x;
              }
              fn();
            }
          } catch (sample) {
            if (sample && control && typeof sample.stack === "string") {
              var sampleLines = sample.stack.split("\n");
              var controlLines = control.stack.split("\n");
              var s = sampleLines.length - 1;
              var c = controlLines.length - 1;
              while (s >= 1 && c >= 0 && sampleLines[s] !== controlLines[c]) {
                c--;
              }
              for (; s >= 1 && c >= 0; s--, c--) {
                if (sampleLines[s] !== controlLines[c]) {
                  if (s !== 1 || c !== 1) {
                    do {
                      s--;
                      c--;
                      if (c < 0 || sampleLines[s] !== controlLines[c]) {
                        var _frame = "\n" + sampleLines[s].replace(" at new ", " at ");
                        if (fn.displayName && _frame.includes("<anonymous>")) {
                          _frame = _frame.replace("<anonymous>", fn.displayName);
                        }
                        {
                          if (typeof fn === "function") {
                            componentFrameCache.set(fn, _frame);
                          }
                        }
                        return _frame;
                      }
                    } while (s >= 1 && c >= 0);
                  }
                  break;
                }
              }
            }
          } finally {
            reentry = false;
            {
              ReactCurrentDispatcher$1.current = previousDispatcher;
              reenableLogs();
            }
            Error.prepareStackTrace = previousPrepareStackTrace;
          }
          var name = fn ? fn.displayName || fn.name : "";
          var syntheticFrame = name ? describeBuiltInComponentFrame(name) : "";
          {
            if (typeof fn === "function") {
              componentFrameCache.set(fn, syntheticFrame);
            }
          }
          return syntheticFrame;
        }
        function describeFunctionComponentFrame(fn, source, ownerFn) {
          {
            return describeNativeComponentFrame(fn, false);
          }
        }
        function shouldConstruct(Component2) {
          var prototype = Component2.prototype;
          return !!(prototype && prototype.isReactComponent);
        }
        function describeUnknownElementTypeFrameInDEV(type, source, ownerFn) {
          if (type == null) {
            return "";
          }
          if (typeof type === "function") {
            {
              return describeNativeComponentFrame(type, shouldConstruct(type));
            }
          }
          if (typeof type === "string") {
            return describeBuiltInComponentFrame(type);
          }
          switch (type) {
            case REACT_SUSPENSE_TYPE:
              return describeBuiltInComponentFrame("Suspense");
            case REACT_SUSPENSE_LIST_TYPE:
              return describeBuiltInComponentFrame("SuspenseList");
          }
          if (typeof type === "object") {
            switch (type.$$typeof) {
              case REACT_FORWARD_REF_TYPE:
                return describeFunctionComponentFrame(type.render);
              case REACT_MEMO_TYPE:
                return describeUnknownElementTypeFrameInDEV(type.type, source, ownerFn);
              case REACT_LAZY_TYPE: {
                var lazyComponent = type;
                var payload = lazyComponent._payload;
                var init = lazyComponent._init;
                try {
                  return describeUnknownElementTypeFrameInDEV(init(payload), source, ownerFn);
                } catch (x) {
                }
              }
            }
          }
          return "";
        }
        var loggedTypeFailures = {};
        var ReactDebugCurrentFrame$1 = ReactSharedInternals.ReactDebugCurrentFrame;
        function setCurrentlyValidatingElement(element) {
          {
            if (element) {
              var owner = element._owner;
              var stack = describeUnknownElementTypeFrameInDEV(element.type, element._source, owner ? owner.type : null);
              ReactDebugCurrentFrame$1.setExtraStackFrame(stack);
            } else {
              ReactDebugCurrentFrame$1.setExtraStackFrame(null);
            }
          }
        }
        function checkPropTypes(typeSpecs, values, location, componentName, element) {
          {
            var has = Function.call.bind(hasOwnProperty);
            for (var typeSpecName in typeSpecs) {
              if (has(typeSpecs, typeSpecName)) {
                var error$1 = void 0;
                try {
                  if (typeof typeSpecs[typeSpecName] !== "function") {
                    var err = Error((componentName || "React class") + ": " + location + " type `" + typeSpecName + "` is invalid; it must be a function, usually from the `prop-types` package, but received `" + typeof typeSpecs[typeSpecName] + "`.This often happens because of typos such as `PropTypes.function` instead of `PropTypes.func`.");
                    err.name = "Invariant Violation";
                    throw err;
                  }
                  error$1 = typeSpecs[typeSpecName](values, typeSpecName, componentName, location, null, "SECRET_DO_NOT_PASS_THIS_OR_YOU_WILL_BE_FIRED");
                } catch (ex) {
                  error$1 = ex;
                }
                if (error$1 && !(error$1 instanceof Error)) {
                  setCurrentlyValidatingElement(element);
                  error("%s: type specification of %s `%s` is invalid; the type checker function must return `null` or an `Error` but returned a %s. You may have forgotten to pass an argument to the type checker creator (arrayOf, instanceOf, objectOf, oneOf, oneOfType, and shape all require an argument).", componentName || "React class", location, typeSpecName, typeof error$1);
                  setCurrentlyValidatingElement(null);
                }
                if (error$1 instanceof Error && !(error$1.message in loggedTypeFailures)) {
                  loggedTypeFailures[error$1.message] = true;
                  setCurrentlyValidatingElement(element);
                  error("Failed %s type: %s", location, error$1.message);
                  setCurrentlyValidatingElement(null);
                }
              }
            }
          }
        }
        function setCurrentlyValidatingElement$1(element) {
          {
            if (element) {
              var owner = element._owner;
              var stack = describeUnknownElementTypeFrameInDEV(element.type, element._source, owner ? owner.type : null);
              setExtraStackFrame(stack);
            } else {
              setExtraStackFrame(null);
            }
          }
        }
        var propTypesMisspellWarningShown;
        {
          propTypesMisspellWarningShown = false;
        }
        function getDeclarationErrorAddendum() {
          if (ReactCurrentOwner.current) {
            var name = getComponentNameFromType(ReactCurrentOwner.current.type);
            if (name) {
              return "\n\nCheck the render method of `" + name + "`.";
            }
          }
          return "";
        }
        function getSourceInfoErrorAddendum(source) {
          if (source !== void 0) {
            var fileName = source.fileName.replace(/^.*[\\\/]/, "");
            var lineNumber = source.lineNumber;
            return "\n\nCheck your code at " + fileName + ":" + lineNumber + ".";
          }
          return "";
        }
        function getSourceInfoErrorAddendumForProps(elementProps) {
          if (elementProps !== null && elementProps !== void 0) {
            return getSourceInfoErrorAddendum(elementProps.__source);
          }
          return "";
        }
        var ownerHasKeyUseWarning = {};
        function getCurrentComponentErrorInfo(parentType) {
          var info = getDeclarationErrorAddendum();
          if (!info) {
            var parentName = typeof parentType === "string" ? parentType : parentType.displayName || parentType.name;
            if (parentName) {
              info = "\n\nCheck the top-level render call using <" + parentName + ">.";
            }
          }
          return info;
        }
        function validateExplicitKey(element, parentType) {
          if (!element._store || element._store.validated || element.key != null) {
            return;
          }
          element._store.validated = true;
          var currentComponentErrorInfo = getCurrentComponentErrorInfo(parentType);
          if (ownerHasKeyUseWarning[currentComponentErrorInfo]) {
            return;
          }
          ownerHasKeyUseWarning[currentComponentErrorInfo] = true;
          var childOwner = "";
          if (element && element._owner && element._owner !== ReactCurrentOwner.current) {
            childOwner = " It was passed a child from " + getComponentNameFromType(element._owner.type) + ".";
          }
          {
            setCurrentlyValidatingElement$1(element);
            error('Each child in a list should have a unique "key" prop.%s%s See https://reactjs.org/link/warning-keys for more information.', currentComponentErrorInfo, childOwner);
            setCurrentlyValidatingElement$1(null);
          }
        }
        function validateChildKeys(node, parentType) {
          if (typeof node !== "object") {
            return;
          }
          if (isArray(node)) {
            for (var i = 0; i < node.length; i++) {
              var child = node[i];
              if (isValidElement(child)) {
                validateExplicitKey(child, parentType);
              }
            }
          } else if (isValidElement(node)) {
            if (node._store) {
              node._store.validated = true;
            }
          } else if (node) {
            var iteratorFn = getIteratorFn(node);
            if (typeof iteratorFn === "function") {
              if (iteratorFn !== node.entries) {
                var iterator = iteratorFn.call(node);
                var step;
                while (!(step = iterator.next()).done) {
                  if (isValidElement(step.value)) {
                    validateExplicitKey(step.value, parentType);
                  }
                }
              }
            }
          }
        }
        function validatePropTypes(element) {
          {
            var type = element.type;
            if (type === null || type === void 0 || typeof type === "string") {
              return;
            }
            var propTypes;
            if (typeof type === "function") {
              propTypes = type.propTypes;
            } else if (typeof type === "object" && (type.$$typeof === REACT_FORWARD_REF_TYPE || // Note: Memo only checks outer props here.
            // Inner props are checked in the reconciler.
            type.$$typeof === REACT_MEMO_TYPE)) {
              propTypes = type.propTypes;
            } else {
              return;
            }
            if (propTypes) {
              var name = getComponentNameFromType(type);
              checkPropTypes(propTypes, element.props, "prop", name, element);
            } else if (type.PropTypes !== void 0 && !propTypesMisspellWarningShown) {
              propTypesMisspellWarningShown = true;
              var _name = getComponentNameFromType(type);
              error("Component %s declared `PropTypes` instead of `propTypes`. Did you misspell the property assignment?", _name || "Unknown");
            }
            if (typeof type.getDefaultProps === "function" && !type.getDefaultProps.isReactClassApproved) {
              error("getDefaultProps is only used on classic React.createClass definitions. Use a static property named `defaultProps` instead.");
            }
          }
        }
        function validateFragmentProps(fragment) {
          {
            var keys = Object.keys(fragment.props);
            for (var i = 0; i < keys.length; i++) {
              var key = keys[i];
              if (key !== "children" && key !== "key") {
                setCurrentlyValidatingElement$1(fragment);
                error("Invalid prop `%s` supplied to `React.Fragment`. React.Fragment can only have `key` and `children` props.", key);
                setCurrentlyValidatingElement$1(null);
                break;
              }
            }
            if (fragment.ref !== null) {
              setCurrentlyValidatingElement$1(fragment);
              error("Invalid attribute `ref` supplied to `React.Fragment`.");
              setCurrentlyValidatingElement$1(null);
            }
          }
        }
        function createElementWithValidation(type, props, children) {
          var validType = isValidElementType(type);
          if (!validType) {
            var info = "";
            if (type === void 0 || typeof type === "object" && type !== null && Object.keys(type).length === 0) {
              info += " You likely forgot to export your component from the file it's defined in, or you might have mixed up default and named imports.";
            }
            var sourceInfo = getSourceInfoErrorAddendumForProps(props);
            if (sourceInfo) {
              info += sourceInfo;
            } else {
              info += getDeclarationErrorAddendum();
            }
            var typeString;
            if (type === null) {
              typeString = "null";
            } else if (isArray(type)) {
              typeString = "array";
            } else if (type !== void 0 && type.$$typeof === REACT_ELEMENT_TYPE) {
              typeString = "<" + (getComponentNameFromType(type.type) || "Unknown") + " />";
              info = " Did you accidentally export a JSX literal instead of a component?";
            } else {
              typeString = typeof type;
            }
            {
              error("React.createElement: type is invalid -- expected a string (for built-in components) or a class/function (for composite components) but got: %s.%s", typeString, info);
            }
          }
          var element = createElement.apply(this, arguments);
          if (element == null) {
            return element;
          }
          if (validType) {
            for (var i = 2; i < arguments.length; i++) {
              validateChildKeys(arguments[i], type);
            }
          }
          if (type === REACT_FRAGMENT_TYPE) {
            validateFragmentProps(element);
          } else {
            validatePropTypes(element);
          }
          return element;
        }
        var didWarnAboutDeprecatedCreateFactory = false;
        function createFactoryWithValidation(type) {
          var validatedFactory = createElementWithValidation.bind(null, type);
          validatedFactory.type = type;
          {
            if (!didWarnAboutDeprecatedCreateFactory) {
              didWarnAboutDeprecatedCreateFactory = true;
              warn("React.createFactory() is deprecated and will be removed in a future major release. Consider using JSX or use React.createElement() directly instead.");
            }
            Object.defineProperty(validatedFactory, "type", {
              enumerable: false,
              get: function() {
                warn("Factory.type is deprecated. Access the class directly before passing it to createFactory.");
                Object.defineProperty(this, "type", {
                  value: type
                });
                return type;
              }
            });
          }
          return validatedFactory;
        }
        function cloneElementWithValidation(element, props, children) {
          var newElement = cloneElement.apply(this, arguments);
          for (var i = 2; i < arguments.length; i++) {
            validateChildKeys(arguments[i], newElement.type);
          }
          validatePropTypes(newElement);
          return newElement;
        }
        function startTransition(scope, options) {
          var prevTransition = ReactCurrentBatchConfig.transition;
          ReactCurrentBatchConfig.transition = {};
          var currentTransition = ReactCurrentBatchConfig.transition;
          {
            ReactCurrentBatchConfig.transition._updatedFibers = /* @__PURE__ */ new Set();
          }
          try {
            scope();
          } finally {
            ReactCurrentBatchConfig.transition = prevTransition;
            {
              if (prevTransition === null && currentTransition._updatedFibers) {
                var updatedFibersCount = currentTransition._updatedFibers.size;
                if (updatedFibersCount > 10) {
                  warn("Detected a large number of updates inside startTransition. If this is due to a subscription please re-write it to use React provided hooks. Otherwise concurrent mode guarantees are off the table.");
                }
                currentTransition._updatedFibers.clear();
              }
            }
          }
        }
        var didWarnAboutMessageChannel = false;
        var enqueueTaskImpl = null;
        function enqueueTask(task) {
          if (enqueueTaskImpl === null) {
            try {
              var requireString = ("require" + Math.random()).slice(0, 7);
              var nodeRequire = module2 && module2[requireString];
              enqueueTaskImpl = nodeRequire.call(module2, "timers").setImmediate;
            } catch (_err) {
              enqueueTaskImpl = function(callback) {
                {
                  if (didWarnAboutMessageChannel === false) {
                    didWarnAboutMessageChannel = true;
                    if (typeof MessageChannel === "undefined") {
                      error("This browser does not have a MessageChannel implementation, so enqueuing tasks via await act(async () => ...) will fail. Please file an issue at https://github.com/facebook/react/issues if you encounter this warning.");
                    }
                  }
                }
                var channel = new MessageChannel();
                channel.port1.onmessage = callback;
                channel.port2.postMessage(void 0);
              };
            }
          }
          return enqueueTaskImpl(task);
        }
        var actScopeDepth = 0;
        var didWarnNoAwaitAct = false;
        function act(callback) {
          {
            var prevActScopeDepth = actScopeDepth;
            actScopeDepth++;
            if (ReactCurrentActQueue.current === null) {
              ReactCurrentActQueue.current = [];
            }
            var prevIsBatchingLegacy = ReactCurrentActQueue.isBatchingLegacy;
            var result;
            try {
              ReactCurrentActQueue.isBatchingLegacy = true;
              result = callback();
              if (!prevIsBatchingLegacy && ReactCurrentActQueue.didScheduleLegacyUpdate) {
                var queue = ReactCurrentActQueue.current;
                if (queue !== null) {
                  ReactCurrentActQueue.didScheduleLegacyUpdate = false;
                  flushActQueue(queue);
                }
              }
            } catch (error2) {
              popActScope(prevActScopeDepth);
              throw error2;
            } finally {
              ReactCurrentActQueue.isBatchingLegacy = prevIsBatchingLegacy;
            }
            if (result !== null && typeof result === "object" && typeof result.then === "function") {
              var thenableResult = result;
              var wasAwaited = false;
              var thenable = {
                then: function(resolve, reject) {
                  wasAwaited = true;
                  thenableResult.then(function(returnValue2) {
                    popActScope(prevActScopeDepth);
                    if (actScopeDepth === 0) {
                      recursivelyFlushAsyncActWork(returnValue2, resolve, reject);
                    } else {
                      resolve(returnValue2);
                    }
                  }, function(error2) {
                    popActScope(prevActScopeDepth);
                    reject(error2);
                  });
                }
              };
              {
                if (!didWarnNoAwaitAct && typeof Promise !== "undefined") {
                  Promise.resolve().then(function() {
                  }).then(function() {
                    if (!wasAwaited) {
                      didWarnNoAwaitAct = true;
                      error("You called act(async () => ...) without await. This could lead to unexpected testing behaviour, interleaving multiple act calls and mixing their scopes. You should - await act(async () => ...);");
                    }
                  });
                }
              }
              return thenable;
            } else {
              var returnValue = result;
              popActScope(prevActScopeDepth);
              if (actScopeDepth === 0) {
                var _queue = ReactCurrentActQueue.current;
                if (_queue !== null) {
                  flushActQueue(_queue);
                  ReactCurrentActQueue.current = null;
                }
                var _thenable = {
                  then: function(resolve, reject) {
                    if (ReactCurrentActQueue.current === null) {
                      ReactCurrentActQueue.current = [];
                      recursivelyFlushAsyncActWork(returnValue, resolve, reject);
                    } else {
                      resolve(returnValue);
                    }
                  }
                };
                return _thenable;
              } else {
                var _thenable2 = {
                  then: function(resolve, reject) {
                    resolve(returnValue);
                  }
                };
                return _thenable2;
              }
            }
          }
        }
        function popActScope(prevActScopeDepth) {
          {
            if (prevActScopeDepth !== actScopeDepth - 1) {
              error("You seem to have overlapping act() calls, this is not supported. Be sure to await previous act() calls before making a new one. ");
            }
            actScopeDepth = prevActScopeDepth;
          }
        }
        function recursivelyFlushAsyncActWork(returnValue, resolve, reject) {
          {
            var queue = ReactCurrentActQueue.current;
            if (queue !== null) {
              try {
                flushActQueue(queue);
                enqueueTask(function() {
                  if (queue.length === 0) {
                    ReactCurrentActQueue.current = null;
                    resolve(returnValue);
                  } else {
                    recursivelyFlushAsyncActWork(returnValue, resolve, reject);
                  }
                });
              } catch (error2) {
                reject(error2);
              }
            } else {
              resolve(returnValue);
            }
          }
        }
        var isFlushing = false;
        function flushActQueue(queue) {
          {
            if (!isFlushing) {
              isFlushing = true;
              var i = 0;
              try {
                for (; i < queue.length; i++) {
                  var callback = queue[i];
                  do {
                    callback = callback(true);
                  } while (callback !== null);
                }
                queue.length = 0;
              } catch (error2) {
                queue = queue.slice(i + 1);
                throw error2;
              } finally {
                isFlushing = false;
              }
            }
          }
        }
        var createElement$1 = createElementWithValidation;
        var cloneElement$1 = cloneElementWithValidation;
        var createFactory = createFactoryWithValidation;
        var Children = {
          map: mapChildren,
          forEach: forEachChildren,
          count: countChildren,
          toArray,
          only: onlyChild
        };
        exports2.Children = Children;
        exports2.Component = Component;
        exports2.Fragment = REACT_FRAGMENT_TYPE;
        exports2.Profiler = REACT_PROFILER_TYPE;
        exports2.PureComponent = PureComponent;
        exports2.StrictMode = REACT_STRICT_MODE_TYPE;
        exports2.Suspense = REACT_SUSPENSE_TYPE;
        exports2.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = ReactSharedInternals;
        exports2.act = act;
        exports2.cloneElement = cloneElement$1;
        exports2.createContext = createContext;
        exports2.createElement = createElement$1;
        exports2.createFactory = createFactory;
        exports2.createRef = createRef;
        exports2.forwardRef = forwardRef;
        exports2.isValidElement = isValidElement;
        exports2.lazy = lazy;
        exports2.memo = memo;
        exports2.startTransition = startTransition;
        exports2.unstable_act = act;
        exports2.useCallback = useCallback;
        exports2.useContext = useContext;
        exports2.useDebugValue = useDebugValue;
        exports2.useDeferredValue = useDeferredValue;
        exports2.useEffect = useEffect2;
        exports2.useId = useId;
        exports2.useImperativeHandle = useImperativeHandle;
        exports2.useInsertionEffect = useInsertionEffect;
        exports2.useLayoutEffect = useLayoutEffect;
        exports2.useMemo = useMemo;
        exports2.useReducer = useReducer;
        exports2.useRef = useRef;
        exports2.useState = useState2;
        exports2.useSyncExternalStore = useSyncExternalStore;
        exports2.useTransition = useTransition;
        exports2.version = ReactVersion;
        if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ !== "undefined" && typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.registerInternalModuleStop === "function") {
          __REACT_DEVTOOLS_GLOBAL_HOOK__.registerInternalModuleStop(new Error());
        }
      })();
    }
  }
});

// node_modules/react/index.js
var require_react = __commonJS({
  "node_modules/react/index.js"(exports2, module2) {
    "use strict";
    if (process.env.NODE_ENV === "production") {
      module2.exports = require_react_production_min();
    } else {
      module2.exports = require_react_development();
    }
  }
});

// src/DogPicksPanel.jsx
var import_react = __toESM(require_react(), 1);
var GOLD = "#ffd700";
var FAV_CELLS = /* @__PURE__ */ new Set([
  "mc6_fav4_w",
  "mc6_fav4_m",
  "mc6_fav_band_m",
  "mc6_fav6_w",
  "mc6_fav150_m",
  "mc6_fav150_w"
]);
var isFavPick = (p) => p.odds != null && p.odds < 0;
var FAV_PRICE_TAGS = [
  { lo: -150, hi: -100, tag: "FAV \u2212100/150" },
  { lo: -200, hi: -150, tag: "FAV \u2212150/200" },
  { lo: -300, hi: -200, tag: "FAV \u2212200/300" },
  { lo: -500, hi: -300, tag: "FAV \u2212300/500" }
];
var FAV_RULE_NOTES = {
  mc6_fav6_w: "WOMEN >=6pt FLOOR, EV>=0 at the offered price: +14.79% on 57 (t 1.50) -- -100/150 +17.81%/23, -150/200 +16.36%/19, -200/300 +11.58%/10, -300/500 +1.37%/5, nothing deeper. A floor because the womens favourite side climbs with the margin.",
  mc6_fav_band_m: "MEN capped 3-6pt BAND, EV>=0 at the offered price: +32.42% on 20 (t 2.41). The EV check matters here -- it removes 14 of the 34 band picks, and without it the band is +24.72% on 34. Capped because the mens favourite side is an inverted U.",
  mc6_fav4_w: "WOMEN 4pt+ at -100..-200, no EV check: MC6 +11.57% on 50 (t 1.00) -- replay +19.87% on 41, forward -26.26% on 9.",
  mc6_fav4_m: "MEN 4pt+ at -100..-200, no EV check and no cap: MC6 +12.13% on 48 (t 1.04) -- replay +17.41% on 43, forward -33.25% on 5. (The -9.21% on 74 once quoted for this lane was MC2s record, not MC6s.)",
  mc6_fav150_m: "MEN -150..-200 RULE: MC6 2-8pt over the market and positive EV at the offered price. Replay +44.80% on 12 (t 3.38); the >=8pt tail it leaves out is -19.34% on 12. Six band shapes were tried before this one, so the t overstates it. The lane records only from 2026-10-17.",
  mc6_fav150_w: "WOMEN -150..-200 RULE: MC6 6+ points over the market (EV is automatic there). +16.36% on 19 -- replay +23.61% on 14, forward -3.94% on 5. The lane records only from 2026-10-17."
};
var FAV_NEGATIVE = /* @__PURE__ */ new Set([]);
var favMarkOf = (p, keys) => {
  if (p.odds == null || p.odds >= 0) return null;
  const fired = (keys || []).filter((k) => FAV_CELLS.has(k));
  if (!fired.length) return null;
  if (p.odds >= -200 && p.odds < -150) {
    const g150 = /wta|itf_women/i.test(String(p.league || "")) ? "w" : "m";
    if (!fired.includes(g150 === "w" ? "mc6_fav150_w" : "mc6_fav150_m")) return null;
  }
  const b = FAV_PRICE_TAGS.find((x) => p.odds >= x.lo && p.odds <= x.hi);
  const allBad = fired.every((k) => FAV_NEGATIVE.has(k));
  const lead = allBad ? 'CAUTION -- the only MC6 favourite rule that fired on this pick has a LOSING record. Gold here means "MC6 likes this favourite", which you asked to see on every one of them; it does not mean the cell wins. ' : "Gold = an MC6 favourite. Every MC6 favourite is marked (your call, 2026-10-16), so the colour says MC6 rates this favourite over the market, NOT that the rule behind it is proven. ";
  const rules = fired.map((k) => FAV_RULE_NOTES[k] || k).join("  ");
  const deep = !b ? " THIS PRICE IS DEEPER THAN -500, WHERE THERE IS NO SAMPLE AT ALL (n=1 men, n=0 women). Clearing EV there needs MC6 above about 93%, the region where a large claimed margin usually means the head misread the match rather than found value. Unmeasured, not endorsed." : "";
  const caveat = " READ THE SAMPLE: these records are mostly MC6 as-of REPLAY. The forward window opened 2026-10-15 and holds 12 settled womens bets on the 6pt floor and 1 mens bet on the 3-6pt band, and the dog gates on this same head are negative forward (men 2pt -11.37% on 43, women 3pt -10.36% on 44).";
  return {
    tag: (b ? b.tag : "FAV \u2212500+ \u26A0") + (allBad ? " \u26A0" : ""),
    col: GOLD,
    rgba: "255,215,0",
    note: lead + rules + deep + caveat
  };
};
var CELLS = [
  ["\u{1F7E1} MC6 4pt+ FAV \xB7 WOMEN -100..-200", "mc6_fav4_w", "MC6 rates this WOMENS favourite 4+ points above the de-vigged market, priced -100..-200, with no EV check. MC6 record: +11.57% on 50 (t 1.00) -- replay +19.87% on 41, forward -26.26% on 9. (The +22.85% on 51 that used to be quoted here was MC2s record.)"],
  [
    "\u{1F7E1} MC6 FAV \u2212150..\u2212200 \xB7 MEN 2\u20138pt",
    "mc6_fav150_m",
    "MENS favourites priced -150..-200 where MC6 is 2 to 8 points over the de-vigged market AND the bet is positive EV at the offered price. Replay +44.80% on 12 (t 3.38). Every mens favourite in this band is -13.04% on 115, and the >=8pt tail this rule leaves out is -19.34% on 12 -- the mens favourite side is an inverted U, sharper in this band than anywhere. Without the EV check it is +43.51% on 21 (same ROI, more volume); kept because 14 of 16 negative-EV favourite marks lost live on 2026-10-13. READ THE SAMPLE: six band shapes were scanned to choose 2-8pt, so the t overstates it, and there is ONE forward bet. The lane records only from 2026-10-17, so it opens at n=0."
  ],
  [
    "\u{1F7E1} MC6 FAV \u2212150..\u2212200 \xB7 WOMEN 6pt+",
    "mc6_fav150_w",
    "WOMENS favourites priced -150..-200 where MC6 is 6+ points over the de-vigged market (every such pick also clears EV). +16.36% on 19 -- replay +23.61% on 14, forward -3.94% on 5. Every womens favourite in this band is -1.46% on 96, about fair. Same floor as the all-price womens gate; the 4-6pt slice the 4pt lane would paint here is flat. >=7pt reads +32.40% on 12 but the whole difference is 7 bets. The lane records only from 2026-10-17, so it opens at n=0."
  ],
  [
    "\u{1F7E1} MC6 FAV 6pt+ \xB7 WOMEN",
    "mc6_fav6_w",
    "MC6 six or more points over the de-vigged market on a WOMENS favourite, still positive EV at the price offered. A FLOOR, not a band, because the womens favourite side CLIMBS with the margin where the mens decays -- >=4pt +9.3% on 68, >=6pt +14.8% on 57, >=8pt +19.0% on 41, against a baseline of -7.9% on 405. The 4-8pt band first proposed measures -5.2% on 27: for women a cap removes the good half. 6pt rather than 8pt keeps 57 picks instead of 41 for about 4 points of ROI, which on replay-only evidence is the better trade. READ THE SAMPLE: 57 picks, almost all MC6 replay, and it does not clear t=2."
  ],
  [
    "\u{1F7E1} MC6 FAV BAND 3-6pt \xB7 MEN",
    "mc6_fav_band_m",
    "MC6 between 3 and 6 points over the de-vigged market on a MENS favourite, and still positive EV at the price offered. A BAND rather than a floor because the mens favourite side is an inverted U: backing every mens favourite is -8.5% on 444 (t -2.61), the 3-6pt band is +21.2% on 35 (t 2.07), a plain floor of 3pt is only +10.2% on 88, and the tail above 6pt that the cap removes is +3.0% on 53. A huge claimed margin on a short price usually means the head misread the match rather than found value. Best cells: -150..-200 +44.6% on 10 (t 2.93) and -100..-150 +31.5% on 8. The EV condition is load-bearing -- only 21 of the 35 band picks clear it, so without it a third of the marks would be bets MC6 itself prices as losers. READ THE SAMPLE: 35 picks, 4 forward. Replay evidence, your call."
  ],
  ["\u{1F7E1} MC6 4pt+ FAV \xB7 MEN -100..-200", "mc6_fav4_m", "MC6 rates this MENS favourite 4+ points above the de-vigged market, priced -100..-200, with no EV check and no cap. MC6 record: +12.13% on 48 (t 1.04) -- replay +17.41% on 43, forward -33.25% on 5. It is NOT the losing control it was labelled as: the -9.21% on 74 was MC2s record. In -150..-200 its uncapped tail is the weak part (6pt+ -3.46% on 18)."],
  ["\u{1F7E6} s52 SEASONAL-BAND DOG \xB7 +100..+200", "s52_fav_band_dog", "Back the market DOG at +100..+200 when the FAVOURITE owns BOTH 52-week seasonal stats, hold% and break% -- a FADE of the seasonal stat leader, not a follow. The sibling cell where the DOG owns both is only +3.40% on 129, which is what makes the direction the finding. THE ONLY CELL ON THIS BOARD CLEARING t=2: +19.80% on 183 (92-91, 50.3% hit, $+905.75, t 2.25), men +13.49% on 94 and women +26.46% on 89 (t 2.04). By band: +100..+150 is +18.11%/119 (men +17.39/66, women +19.00/53) and +150..+200 is +22.94%/64 (men +4.29/28, women +37.44/36). The lane is hard-gated to +100..+200 and that ceiling is earned -- re-run without it, +200..+250 is -14.94% on 65 and +250..+300 is -11.21% on 38. CAVEAT: the frozen window is 39 days and the rule replays inside it, so part of this record is in-sample for the rule itself."],
  [
    "\u{1F7E4} MC6 2pt+ DOG \xB7 MEN",
    "mc6_dog2_all",
    "MC6 two or more points over the de-vigged market on the dog -- THE MENS GATE (2026-10-16). Mens record on the tab population: +8.22% on 182 (t 0.85), forward +7.22% on 27. By band: +100..+150 +38.64% on 73 (t 3.06; forward +21.64% on 14), +150..+200 -24.22% on 50, +200..+250 +12.53% on 38, +250..+300 -28.10% on 21. The mens edge lives at +100..+150 and alternates above it, which is why only two mens bands are pink. Mostly MC6 as-of REPLAY; the forward window opened 2026-10-15."
  ],
  [
    "\u{1F7E4} MC6 3pt+ DOG",
    "mc6_dog3_all",
    "MC6 three or more points over the de-vigged market on the dog -- THE WOMENS GATE (2026-10-16; men moved to 2pt the same day). Womens record on the tab population: +23.62% on 173 (t 2.21), but forward -0.82% on 34. By band: +100..+150 +12.93% on 68 (forward -19.86% on 14), +150..+200 +41.38% on 47, +200..+250 -15.70% on 27, +250..+300 +54.42% on 31. Mostly MC6 as-of REPLAY; the forward half is flat so far."
  ],
  [
    "\u{1F7E4} MC6 6pt+ DOG",
    "mc6_dog6_all",
    "MC6 six or more points over the de-vigged market on the dog, any price. Tab population: men +9.77% on 128 (forward +12.95% on 20), women +26.86% on 138 (t 2.19; forward -8.15% on 26). By band, men: +100..+150 +21.69%/52, +150..+200 -4.97%/34, +200..+250 +14.65%/26, +250..+300 -5.62%/16; women: +3.14%/51, +45.74%/38, -1.04%/23, +70.46%/26. (The ladder once quoted here was MC2s, not MC6s.)"
  ],
  [
    "\u{1F7E4} MC6 4pt+ DOG",
    "mc6_dog4_all",
    "MC6 four or more points over the de-vigged market on the dog, any price. Tab population: men +3.63% on 160 (forward -1.64% on 25), women +27.74% on 160 (t 2.47; forward -9.34% on 29). By band, men: +100..+150 +25.59%/61, +150..+200 -15.80%/45, +200..+250 +6.50%/34, +250..+300 -24.50%/20; women: +15.07%/61, +41.27%/45, -8.96%/25, +65.07%/29. Replay-heavy. (The +13.15% on 91 once quoted here was MC2s.)"
  ],
  [
    "\u{1F7E4} MC2 TAKE DOG \xB7 unstamped",
    "mc2_take_dog_all",
    "Your take rule at the new -6 threshold, counting every frozen row rather than only those after the rule was written. The date-stamped lane (mc2_take_dog) is the in-sample-free version and is much smaller."
  ],
  [
    "\u{1F9EE}\xB3 MC3 TAKE DOG \xB7 unstamped",
    "mc3_take_dog_all",
    "The same rule on MC3, counting every frozen row. MC3 is starved on the stamped lane because 1,326 of its 1,400 rows are recon backfills."
  ],
  [
    "\u{1F9EE}\u2075 MC5 TAKE DOG \xB7 unstamped",
    "mc5_take_dog_all",
    "The same rule on MC5. Only 13 of its 565 rows are forward, so this is near-empty and will stay that way for weeks -- shown so it accrues against a recorded rule rather than starting from scratch later."
  ],
  [
    "\u{1F9CA} FADE FORM \xB7 dogs",
    "pf_c75_dis_dog",
    "c75 pick where the pure-results form overlay points at the OPPONENT, and the pick is the dog. Best t on the board (2.40)."
  ],
  [
    "\u{1F500} 6-4 SPLIT \xB7 dogs",
    "split64_fade_dog",
    "The 10 heads split exactly 6-4; back the 4-minority when it is the dog. Even across genders (M +27.6 / W +27.7)."
  ],
  [
    "\u2684 c75 DOG FLIP",
    "mc_c75_dog",
    "c75 puts the market underdog past 50% and picks it outright. The largest honest sample of any flip (no recon rows)."
  ],
  [
    "\u{1F7E4} MC2 DOG FLIP",
    "mc2_dog_flip",
    "MC2 puts the market dog past 50%. The LANE is only days old (MC2_LIVE_FROM 2026-10-13), so n here is tiny; across the whole forward log MC2 flips are +14.3% on 84."
  ],
  [
    "\u{1F415} c75 DOG +100 up",
    "c75_dog_100plus",
    "Every c75 dog priced +100 or longer. Biggest dollar earner on the board and the deepest sample."
  ],
  [
    "\u{1F3BE} RETURNER DOG (W)",
    "returner_dog_w",
    "Women, dog wins the return-pressure gap. Highest ROI of any dog cell, on only 25 settles."
  ],
  [
    "\u{1F3AF} ALL-ROUND DOG (W)",
    "allround_dog_w",
    "Women, dog better on serve AND return pressure. 22 settles."
  ],
  [
    "\u2684 c50+c75 DOG \xB7 no D",
    "cc75_nod_dog",
    "Both C-MC variants back the dog and Model D does NOT. 77 settles."
  ],
  [
    "\u2B50 STAR DOG (resolver 1)",
    "cr1_stardog",
    "The conflict-resolver tier-1 star dog. 52 settles."
  ],
  ["\u2684 c50+c75 DOG", "cc75_dog", "Both C-MC variants back the dog, D ignored."],
  ["\u{1FA77} FADE-B DOG (M)", "pink_fadeb_dog_m", "Men, pink fade-B dog watch cell."],
  ["\u{1FA77} MC2 DOG (pink)", "pink_mc2_dog", "The pink MC2 dog watch cell."],
  [
    "\u26D4 TIER-AVOID \xB7 dogs",
    "tier_avoid_dog",
    "The dog side of cards the board labels AVOID. Counter-intuitive and worth watching: the avoid applies to the favourite, and the dog has paid."
  ],
  ["\u24B9 D-MA DOG", "dma_dog", "Model D market-aware picks the dog."],
  ["\u{1F7E4} MC2 DOG BAND", "mc2_dog_band", "MC2 dog inside the +100..+250 price band."],
  ["\u26AA C+GRAY DOG late", "cgray_dog_late", "C and the gray line on the dog, later rounds."],
  ["\u{1F501} OVERLAY DOG", "ovl_dog", "The overlay dog cell."],
  ["\u2694 FIGHT MC4 DOG", "fight_mc4_dog", "MC4 disagrees with the market on the dog."]
];
function splitByBand(cel) {
  const out = [];
  for (const [lab, lo, hi] of BANDS) {
    const ps = (cel.picks || []).filter((p) => p.odds != null && p.odds >= lo && p.odds <= hi && priceOK(p) && leagueOK(p));
    if (!ps.length) continue;
    const mk = (sub) => {
      const done = sub.filter((p) => p.won != null);
      const wins = done.filter((p) => p.won).length;
      const profit = done.reduce((a, p) => a + (p.pnl || 0), 0);
      return {
        n: done.length,
        wins,
        profit_usd: Math.round(profit * 100) / 100,
        staked_usd: 25 * done.length,
        roi_pct: done.length ? Math.round(1e3 * profit / (25 * done.length)) / 10 : 0,
        pending: sub.length - done.length
      };
    };
    const men = ps.filter((p) => genderOf(p) === "m");
    const women = ps.filter((p) => genderOf(p) === "w");
    const c = {
      ...mk(ps),
      m: mk(men),
      w: mk(women),
      m_dog: mk(men),
      w_dog: mk(women),
      dog: mk(ps),
      fav: mk([]),
      m_fav: mk([]),
      w_fav: mk([])
    };
    out.push({
      ...cel,
      uid: `${cel.key}@${lab}`,
      label: `${cel.baseLabel} \xB7 ${lab}`,
      c,
      cShown: c,
      hidden: [],
      picks: ps,
      t: tstat(c)
    });
  }
  return out;
}
function tstat(c) {
  const n = c && c.n, w = c && c.wins, roi = c && c.roi_pct;
  if (!n || w == null || roi == null || n < 2) return null;
  const r = roi / 100;
  if (w <= 0) return null;
  const gain = (r * n + (n - w)) / w;
  const varr = (w * gain * gain + (n - w)) / n - r * r;
  if (!(varr > 0)) return null;
  return r / (Math.sqrt(varr) / Math.sqrt(n));
}
var MAX_AM = 300;
var priceOK = (p) => p.odds != null && p.odds <= MAX_AM;
var PINK_RULES = [
  { lo: 100, hi: 150, g: "m", tag: "MC6 2pt+ M", cells: /* @__PURE__ */ new Set(["mc6_dog2_all"]), tip: "MEN, +100..+150. MC6 two or more points over the de-vigged market on the dog. MC6 record: +38.64% on 73 (46-27, t 3.06) -- replay +42.68% on 59, forward +21.64% on 14 (8-6). Blind mens dogs in this band are +14.75% on 141, and +28.55% on 20 forward -- so forward, MC6 is not yet beating simply backing every dog here. The strongest MC6 dog cell on replay; the forward half is far too small to confirm it." },
  { lo: 100, hi: 150, g: "w", tag: "MC6 3pt+ W", cells: /* @__PURE__ */ new Set(["mc6_dog3_all"]), tip: "WOMEN, +100..+150. MC6 three or more points over the de-vigged market on the dog. MC6 record: +12.93% on 68 (35-33, t 0.96) -- replay +21.43% on 54, but FORWARD -19.86% on 14 (5-9). Blind womens dogs here are -1.96% on 162 overall and +7.40% on 35 forward. THE WEAKEST PINK CELL: its forward half is negative and below the blind band. If it is still non-positive at 25 forward settles the tab drops it automatically." },
  { lo: 150, hi: 200, g: "w", tag: "MC6 3pt+ W", cells: /* @__PURE__ */ new Set(["mc6_dog3_all"]), tip: "WOMEN, +150..+200. MC6 three or more points over the de-vigged market on the dog. MC6 record: +41.38% on 47 (24-23, t 2.02) -- replay +49.21% on 39, forward +3.25% on 8 (3-5). Blind womens dogs here are +24.68% on 75 but -34.94% on 17 forward, so forward MC6 is well ahead of the blind band, on a tiny sample. The MENS half of this band loses for MC6 at every gate (2pt -24.22% on 50) and is off the tab." },
  { lo: 200, hi: 250, g: "m", tag: "MC6 2pt+ M", cells: /* @__PURE__ */ new Set(["mc6_dog2_all"]), tip: "MEN, +200..+250. MC6 two or more points over the de-vigged market on the dog. MC6 record: +12.53% on 38 (13-25, t 0.49) -- replay +10.18% on 33, forward +28.00% on 5. Blind mens dogs here are +3.35% on 51. The signal is MC6 agreeing with the dog at all -- when it does NOT, the dog is -45.42% on 12 -- and margin size adds little until about 10pt. Positive but unproven: a watch mark." },
  { lo: 250, hi: 300, g: "w", tag: "MC6 3pt+ W", cells: /* @__PURE__ */ new Set(["mc6_dog3_all"]), tip: "WOMEN, +250..+300. MC6 three or more points over the de-vigged market on the dog. MC6 record: +54.42% on 31 (13-18, t 1.64) -- replay +60.61% on 23, forward +36.62% on 8 (3-5). Blind womens dogs here are already +17.66% on 44 and +48.30% on 10 forward, so much of this is the price rather than MC6, and forward MC6 is BEHIND the blind band. The mens half is -28.10% on 21 at 2pt and is off the tab." },
  // s52 SEASONAL-BAND DOG (2026-10-14, user "mark both men and women dogs +100 to +200 with ...
  // s52_fav_band_dog ... pink"). The only cell on the board clearing t=2: +19.80% on 183, t 2.25,
  // with BOTH genders forward-positive (men +13.49%/94, women +26.46%/89). The lane is itself
  // hard-gated to +100..+200 and that ceiling is earned -- without it +200..+250 is -14.94%/65
  // and +250..+300 is -11.21%/38. Listed AFTER the MC2 rules so the MC2 tooltip wins where a
  // pick qualifies under both; the s52 cell still appears in the pick's badge list either way.
  // MENS RULE STOPS AT +150 (2026-10-14, user "lets remove that band then until it gets more
  // games"). It could never paint anyway -- the board band gate drops men +150..+200 -- so the
  // rule no longer claims a range it cannot deliver. Mens +100..+150 is +17.39%/66; the held
  // back +150..+200 half is +4.29%/28, the weakest quarter of the cell, inside a band that is
  // -6.57%/84 deduped. Nothing is deleted: the lane keeps scoring it and it returns on its own
  // if that band turns positive. WOMEN keep the full +100..+200, where their half is strongest
  // (+37.44%/36 at +150..+200 against +19.00%/53 at +100..+150).
  { lo: 100, hi: 150, g: "m", tag: "s52 BAND M", cells: /* @__PURE__ */ new Set(["s52_fav_band_dog"]), tip: 'MEN, +100..+150 ONLY, s52 SEASONAL-BAND DOG -- back the dog when the FAVOURITE owns both 52-week hold% and break%. This half is +17.39% on 66 forward. THE +150..+200 HALF IS HELD BACK (your call, 2026-10-14, "until it gets more games"): it is the weakest quarter of the cell at +4.29% on 28, and the whole mens +150..+200 band is -6.57% on 84 deduped across the tab, so the board gate drops it before pink is even considered. Nothing is deleted -- the lane keeps scoring those picks and they reappear on their own if that band turns positive. The cell overall is the only one on this board clearing t=2 (+19.80%/183, t 2.25), but that is carried by the womens half, which keeps the full +100..+200 range.' },
  { lo: 100, hi: 200, g: "w", tag: "s52 BAND W", cells: /* @__PURE__ */ new Set(["s52_fav_band_dog"]), tip: "WOMEN, +100..+200, s52 SEASONAL-BAND DOG -- back the dog when the FAVOURITE owns both 52-week hold% and break%. Womens half +26.46% on 89 (46-43, 51.7% hit against ~40% needed, t 2.04) -- the strongest gender half of the strongest cell on the board. Unlike the mens half it is carried by the DEEP band: +37.44% on 36 at +150..+200 against +19.00% on 53 at +100..+150. Note the lane records a 39-day window and replays inside it." },
  // c75 DOG FLIP (2026-10-14, user "lets do c75 flips men and women and also check +150 to 200").
  // The check is why this is two band-specific rules rather than one range: at +150..+200 the
  // genders go OPPOSITE ways, so marking both across +100..+200 would have painted the two
  // negative halves. Measured on the lane's own picks, ITF men excluded:
  //                   MEN                      WOMEN
  //   +100..+150   +22.88%/65  t 1.73       -23.53%/47  t -1.59
  //   +150..+200   -26.27%/15                +10.68%/22 t  0.38
  // A flip has no margin to tune, so the band is the only parameter chosen. The womens cell is
  // THIN (22 bets, t 0.38) and its badge says so; its blended lane number is further flattered by
  // a FOUR-bet +200..+250 cell at +140.75%, which is not marked.
  { lo: 100, hi: 150, g: "m", tag: "c75 FLIP M", cells: /* @__PURE__ */ new Set(["mc_c75_dog"]), tip: "MEN, +100..+150, c75 DOG FLIP -- Model C75 puts the market underdog past 50% and picks it outright, and you back the dog at the frozen price. +22.88% on 65 (37-28, 56.9% hit, t 1.73) against a blind mens dog baseline of about -1%. A flip has NO margin to tune, so the price band is the only choice made here, and the mens record collapses outside it: -26.27% on 15 at +150..+200 and -100% on 2 at +250..+300. Both C heads read the same thing -- requiring c50 to agree as well gives +22.24% on 55, no better -- so this is one signal, not two." }
];
var pinkRule = (p, cellKeys) => {
  if (p.odds == null || p.odds < 0) return null;
  const g = /wta|itf_women/i.test(String(p.league || "")) ? "w" : "m";
  const keys = [...cellKeys || []];
  for (const r of PINK_RULES) {
    if (r.g !== g) continue;
    if (p.odds >= r.lo && p.odds <= r.hi && keys.some((k) => r.cells.has(k))) return r;
  }
  return null;
};
var DROP_LEAGUES = /* @__PURE__ */ new Set(["itf_men"]);
var leagueOK = (p) => !DROP_LEAGUES.has(String(p.league || "").toLowerCase());
var BANDS = [
  ["+100..+150", 100, 150],
  ["+150..+200", 150, 200],
  ["+200..+250", 200, 250],
  ["+250..+300", 250, 300]
];
var bandOf = (od) => od == null ? null : (BANDS.find(([, lo, hi]) => od >= lo && od <= hi) || [null])[0];
function bandGenderRec(cel, g, odds) {
  const b = bandOf(odds);
  if (!b) return { n: 0, band: null };
  const lo = (BANDS.find((x) => x[0] === b) || [])[1];
  const hi = (BANDS.find((x) => x[0] === b) || [])[2];
  const ps = (cel.picks || []).filter((p) => p.odds != null && p.odds >= lo && p.odds <= hi && priceOK(p) && leagueOK(p) && genderOf(p) === g);
  const done = ps.filter((p) => p.won != null);
  const profit = done.reduce((a, p) => a + (p.pnl || 0), 0);
  return {
    band: b,
    n: done.length,
    wins: done.filter((p) => p.won).length,
    pending: ps.length - done.length,
    profit_usd: profit,
    per_bet: done.length ? profit / done.length : 0,
    roi_pct: done.length ? Math.round(1e3 * profit / (25 * done.length)) / 10 : 0
  };
}
var bandKey = (p) => {
  const b = bandOf(p.odds);
  return b ? `${/wta|itf_women/i.test(String(p.league || "")) ? "w" : "m"}|${b}` : null;
};
function badBandGenders(cells) {
  const seen = /* @__PURE__ */ new Map();
  for (const cel of cells) {
    if (FAV_CELLS.has(cel.key)) continue;
    for (const p of cel.picks) {
      if (!priceOK(p) || !leagueOK(p)) continue;
      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, genderOf(p))) continue;
        if (!cellThick(cel.c, genderOf(p))) continue;
      }
      const k = `${p.date}|||${p.pick}|||${p.opp}`;
      if (!seen.has(k)) seen.set(k, p);
    }
  }
  const tot = {};
  for (const p of seen.values()) {
    const k = bandKey(p);
    if (!k || p.won == null) continue;
    if (!tot[k]) tot[k] = { n: 0, w: 0, profit: 0 };
    tot[k].n += 1;
    tot[k].w += p.won ? 1 : 0;
    tot[k].profit += p.pnl || 0;
  }
  const bad = /* @__PURE__ */ new Map();
  for (const [k, v] of Object.entries(tot)) {
    const roi = 100 * v.profit / (25 * v.n);
    if (roi <= 0) bad.set(k, { ...v, roi });
  }
  return bad;
}
var genderOf = (p) => /wta|itf_women/i.test(String(p.league || "")) ? "w" : "m";
var MARK_CELLS = /* @__PURE__ */ new Set([
  ...PINK_RULES.flatMap((r) => [...r.cells]),
  "mc6_fav4_w",
  "mc6_fav4_m",
  // the men's 3-6pt favourite BAND (2026-10-16, user call) -- marks gold like the others
  "mc6_fav_band_m",
  // the women's >=6pt favourite FLOOR (2026-10-16, user call)
  "mc6_fav6_w",
  // the -150..-200 favourite rules (2026-10-17, user call)
  "mc6_fav150_m",
  "mc6_fav150_w"
]);
var SPLIT_BY_BAND = /* @__PURE__ */ new Set(["mc6_dog2_all", "mc6_dog3_all", "mc6_dog4_all", "mc6_dog6_all"]);
var allGendersNegative = (c) => {
  const seen = ["m", "w"].map((g) => genderRec(c, g)).filter((d) => d && d.n);
  return seen.length > 0 && seen.every((d) => (d.roi_pct || 0) <= 0);
};
var MIN_CELL_N = 25;
var cellThick = (c, g) => {
  const d = genderRec(c, g);
  return !d.n || d.n >= MIN_CELL_N;
};
var whenMs = (p) => {
  const t = Date.parse(p.start || "");
  if (!isNaN(t)) return t;
  const d = Date.parse(`${p.date || ""}T23:59:59Z`);
  return isNaN(d) ? 864e13 : d;
};
var genderRec = (c, g) => {
  const d = (c || {})[g + "_dog"];
  if (d && d.n) return d;
  return (c || {})[g] || {};
};
var genderOK = (c, g) => {
  const d = genderRec(c, g);
  if (!d.n) return true;
  return (d.roi_pct || 0) > 0;
};
var markOf = (x) => isFavPick(x.p) ? favMarkOf(x.p, x.cells.map((c) => c.key)) : pinkRule(x.p, x.cells.map((c) => c.key));
function buildCells(st) {
  const cells = CELLS.map(([label, key, note]) => {
    const c = st[key] || {};
    const shown = ["m", "w"].filter((g) => genderOK(c, g));
    const hidden = ["m", "w"].filter((g) => !genderOK(c, g));
    let cShown = c;
    if (hidden.length) {
      const parts = shown.map((g) => genderRec(c, g)).filter((d) => d && d.n);
      if (parts.length) {
        const n = parts.reduce((a, d) => a + d.n, 0);
        const wins = parts.reduce((a, d) => a + (d.wins || 0), 0);
        const profit_usd = parts.reduce((a, d) => a + (d.profit_usd || 0), 0);
        cShown = {
          ...c,
          n,
          wins,
          profit_usd,
          roi_pct: Math.round(1e3 * profit_usd / (25 * n)) / 10
        };
      }
    }
    return {
      label,
      baseLabel: label,
      key,
      note,
      c,
      cShown,
      hidden,
      picks: c.picks || [],
      t: tstat(cShown)
    };
  }).filter((x) => x.c && (x.c.n || x.picks.length)).flatMap((x) => SPLIT_BY_BAND.has(x.key) ? splitByBand(x) : [x]).filter((x) => !allGendersNegative(x.c));
  return cells;
}
function buildStacked(cells, nowMs) {
  const CUTOFF = nowMs - 6 * 3600 * 1e3;
  const badBG = badBandGenders(cells);
  const byMatch = {};
  for (const cel of cells) {
    for (const p of cel.picks) {
      if (p.won != null || p.settled) continue;
      if (whenMs(p) < CUTOFF) continue;
      if (!priceOK(p) || !leagueOK(p)) continue;
      const g = genderOf(p);
      if (!MARK_CELLS.has(cel.key)) {
        if (!genderOK(cel.c, g)) continue;
        if (!cellThick(cel.c, g)) continue;
      }
      {
        const bg = bandGenderRec(cel, g, p.odds);
        if (bg.n >= MIN_CELL_N && (bg.roi_pct || 0) <= 0) continue;
      }
      if (badBG.has(bandKey(p))) continue;
      const k = `${p.pick}|||${p.opp}`;
      if (!byMatch[k]) byMatch[k] = { p, g, cells: [] };
      byMatch[k].cells.push(cel);
    }
  }
  let stacked = Object.values(byMatch);
  const sameMatchKey = (x) => [
    String(x.p.date || ""),
    ...[String(x.p.pick || ""), String(x.p.opp || "")].sort()
  ].join("|||");
  const sides = /* @__PURE__ */ new Map();
  for (const x of stacked) {
    const k = sameMatchKey(x);
    if (!sides.has(k)) sides.set(k, []);
    sides.get(k).push(x);
  }
  stacked = stacked.filter((x) => {
    const grp = sides.get(sameMatchKey(x)) || [];
    if (grp.length < 2) return true;
    return grp.some((y) => markOf(y)) ? !!markOf(x) : true;
  });
  return stacked;
}

// src/dogEngineEntry.js
var chunks = [];
process.stdin.on("data", (c) => chunks.push(c));
process.stdin.on("end", () => {
  const d = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  const st = (d && (d.ab25 || d) || {}).study || {};
  const now = Number(process.argv[2]) || Date.now();
  const cells = buildCells(st);
  const stacked = buildStacked(cells, now);
  const out = stacked.map((x) => {
    const m = markOf(x);
    return {
      // gold for a favourite, pink for a dog -- the same split the tab paints
      kind: m ? x.p.odds < 0 ? "gold" : "pink" : null,
      tag: m ? m.tag : null,
      pick: x.p.pick,
      opp: x.p.opp,
      date: x.p.date,
      start: x.p.start,
      league: x.p.league,
      tournament: x.p.tournament || null,
      surface: x.p.surface || null,
      odds: x.p.odds,
      mc6_ev: x.p.mc6_ev == null ? null : x.p.mc6_ev,
      gender: x.g,
      cells: x.cells.map((c) => c.key)
    };
  });
  process.stdout.write(JSON.stringify({ now, n_list: out.length, highlights: out.filter((h) => h.kind) }));
});
/*! Bundled license information:

react/cjs/react.production.min.js:
  (**
   * @license React
   * react.production.min.js
   *
   * Copyright (c) Facebook, Inc. and its affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)

react/cjs/react.development.js:
  (**
   * @license React
   * react.development.js
   *
   * Copyright (c) Facebook, Inc. and its affiliates.
   *
   * This source code is licensed under the MIT license found in the
   * LICENSE file in the root directory of this source tree.
   *)
*/
