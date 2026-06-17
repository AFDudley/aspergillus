// ASP202 — assertion density (imperative-shell scoped).
//
// NASA Power of 10 #5: minimum two assertions per function. Assertions
// are the correctness mechanism for the IMPERATIVE SHELL — a runtime
// precondition guarding data the type system cannot. They are NOT the
// mechanism for the FUNCTIONAL CORE: a pure, statically-typed transform
// earns correctness from the OTHER level-3 rules (the TS type checker,
// `neverthrow` Result-not-throw, the `boundaries` purity layering), so
// demanding two runtime asserts there mis-prescribes the shell mechanism
// onto the core. This rule therefore applies its `min`-assertion
// requirement ONLY to functions in the imperative shell (see
// `isImperativeShell`) and exempts the pure, statically-constrained
// functional core. Short functions (< minFunctionLength lines) are
// skipped regardless — the rule's intent is non-trivial logic.
//
// Functional-core / imperative-shell predicate (asp-da5, parity with the
// Python sibling `LowAssertionDensity`). A function is imperative shell —
// thus in scope — iff EITHER:
//   - it performs I/O — its body `await`s, or calls a known I/O global
//     (`ioNames`, e.g. `fetch`) or a method on a known I/O object
//     (`ioObjects`, e.g. `fs`, `localStorage`, `document`, `process`).
//     Side-effecting functions are the shell; preconditions belong here.
//   - it ingests dynamically-typed / untrusted data — a parameter is
//     explicitly typed `any` / `unknown` (`dynamicParamTypes`). The type
//     system cannot constrain such a value, so a pure function taking it
//     is still shell-ish and a runtime precondition IS the right guard.
// A pure function whose parameters are concretely typed is functional
// core and EXEMPT. (A MISSING annotation is NOT treated as untrusted:
// under the default espree parser there are no type nodes at all, and
// under a strict TS parser implicit-any is already a type error — so the
// untrusted signal is an EXPLICIT `any`/`unknown`, requiring a
// type-aware parser to observe, exactly as consumers run it.)
//
// Recognized as assertions by default:
//   assert(...)             — node:assert default export, or top-level
//                             helper conventionally named `assert`
//   assert.ok / .equal …    — namespace methods on `assert`
//   invariant(...)          — common helper convention
//   console.assert(...)     — JS host
//
// Consumers extend the lists via:
//   assertionNames        — bare callee name (`check(...)`)
//   memberPatterns        — single-dot `object.method` form
//                           (multi-dot paths like `chai.assert.ok` are
//                           not matched; list `chai.assert` in
//                           `assertionNames` instead so its namespace
//                           methods all count)
//   methodNames           — method name regardless of receiver
//                           (`schema.parse(...)` counts when 'parse'
//                           is listed; useful for Zod parse, schema
//                           validators, etc.)
//   countThrowStatements  — when true, `throw` statements count as
//                           assertions. NASA's `assert(cond)` is
//                           logically `if (!cond) throw`; explicit
//                           throws enforce preconditions equivalently.
//   ioNames               — bare callee names that are I/O (`fetch`).
//   ioObjects             — receiver names whose methods are I/O
//                           (`fs.readFile`, `localStorage.getItem`).
//   treatAwaitAsIo        — when true (default), an `await` in the body
//                           marks the function imperative-shell.
//   dynamicParamTypes     — TS type keywords that mark a parameter as
//                           untrusted (`any`, `unknown`).

const DEFAULT_MIN = 2;
const DEFAULT_MIN_FUNCTION_LENGTH = 10;
const DEFAULT_ASSERTION_NAMES = ['assert', 'invariant'];
const DEFAULT_MEMBER_PATTERNS = ['console.assert'];
const DEFAULT_METHOD_NAMES = [];
const DEFAULT_COUNT_THROW_STATEMENTS = false;
const DEFAULT_IO_NAMES = ['fetch'];
const DEFAULT_IO_OBJECTS = [
  'fs',
  'fsPromises',
  'localStorage',
  'sessionStorage',
  'document',
  'window',
  'navigator',
  'process',
];
const DEFAULT_TREAT_AWAIT_AS_IO = true;
const DEFAULT_DYNAMIC_PARAM_TYPES = ['any', 'unknown'];

// TS type-node `type` -> short keyword the predicate compares against.
const TS_TYPE_KEYWORD = {
  TSAnyKeyword: 'any',
  TSUnknownKeyword: 'unknown',
};

function isAssertionCall(node, assertionNames, memberPatterns, methodNames) {
  if (node.type !== 'CallExpression') return false;
  const callee = node.callee;

  if (callee.type === 'Identifier') {
    return assertionNames.includes(callee.name);
  }

  if (
    callee.type === 'MemberExpression' &&
    !callee.computed &&
    callee.property.type === 'Identifier'
  ) {
    // methodNames: match by property name regardless of receiver shape.
    // Covers `schema.parse(...)`, `chain().parse(...)`, etc.
    if (methodNames.includes(callee.property.name)) return true;

    if (callee.object.type === 'Identifier') {
      const full = `${callee.object.name}.${callee.property.name}`;
      if (memberPatterns.includes(full)) return true;
      // `assert.ok(...)`, `assert.equal(...)` etc. when `assert` is in
      // assertionNames — namespace methods on a configured name count.
      if (assertionNames.includes(callee.object.name)) return true;
    }
  }

  return false;
}

function countAssertionsIn(
  rootBody,
  assertionNames,
  memberPatterns,
  methodNames,
  countThrowStatements,
) {
  let count = 0;
  function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (const item of node) walk(item);
      return;
    }
    if (typeof node.type !== 'string') return;
    // Don't recurse into nested function bodies — each function is
    // visited separately by the rule's selectors.
    if (
      node !== rootBody &&
      (node.type === 'FunctionDeclaration' ||
        node.type === 'FunctionExpression' ||
        node.type === 'ArrowFunctionExpression')
    ) {
      return;
    }
    if (isAssertionCall(node, assertionNames, memberPatterns, methodNames)) {
      count++;
    }
    if (countThrowStatements && node.type === 'ThrowStatement') {
      count++;
    }
    for (const key of Object.keys(node)) {
      if (key === 'parent' || key === 'loc' || key === 'range') continue;
      walk(node[key]);
    }
  }
  walk(rootBody);
  return count;
}

// True for an I/O call: a bare `fetch(...)` (callee in ioNames) or a
// `obj.method(...)` whose root receiver is a known I/O object.
function isIoCall(node, ioNames, ioObjects) {
  if (node.type !== 'CallExpression') return false;
  const callee = node.callee;
  if (callee.type === 'Identifier') {
    return ioNames.includes(callee.name);
  }
  if (callee.type === 'MemberExpression' && callee.object.type === 'Identifier') {
    return ioObjects.includes(callee.object.name);
  }
  return false;
}

// Walk a function body for an I/O signal (await or an I/O call), without
// descending into nested function bodies — each is its own unit.
function bodyPerformsIo(rootBody, ioNames, ioObjects, treatAwaitAsIo) {
  let found = false;
  function walk(node) {
    if (found || !node || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (const item of node) walk(item);
      return;
    }
    if (typeof node.type !== 'string') return;
    if (
      node !== rootBody &&
      (node.type === 'FunctionDeclaration' ||
        node.type === 'FunctionExpression' ||
        node.type === 'ArrowFunctionExpression')
    ) {
      return;
    }
    if (treatAwaitAsIo && node.type === 'AwaitExpression') {
      found = true;
      return;
    }
    if (isIoCall(node, ioNames, ioObjects)) {
      found = true;
      return;
    }
    for (const key of Object.keys(node)) {
      if (key === 'parent' || key === 'loc' || key === 'range') continue;
      walk(node[key]);
    }
  }
  walk(rootBody);
  return found;
}

// The TS type annotation node attached to a parameter, unwrapping
// default-value (`x = 1`) and rest (`...xs`) wrappers. Returns undefined
// when the parser exposes no type info (e.g. the default espree parser).
function paramTypeNode(param) {
  let target = param;
  if (target.type === 'AssignmentPattern') target = target.left;
  if (target.type === 'RestElement') target = target.argument;
  const ann = target.typeAnnotation;
  return ann && ann.typeAnnotation ? ann.typeAnnotation : undefined;
}

// True if any parameter is explicitly typed with a dynamic, unconstrained
// type (`any` / `unknown`) — an untrusted-data boundary.
function hasUntrustedParam(node, dynamicParamTypes) {
  for (const param of node.params) {
    const typeNode = paramTypeNode(param);
    if (!typeNode) continue;
    const keyword = TS_TYPE_KEYWORD[typeNode.type];
    if (keyword && dynamicParamTypes.includes(keyword)) return true;
  }
  return false;
}

// FC/IS predicate: the function is imperative shell (ASP202 applies) iff
// it performs I/O or ingests dynamically-typed data. A pure, statically
// typed function is functional core and returns false (exempt).
function isImperativeShell(node, cfg) {
  if (bodyPerformsIo(node.body, cfg.ioNames, cfg.ioObjects, cfg.treatAwaitAsIo)) {
    return true;
  }
  return hasUntrustedParam(node, cfg.dynamicParamTypes);
}

export default {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Require a minimum number of assertion-like calls per non-trivial function (ASP202).',
    },
    schema: [
      {
        type: 'object',
        properties: {
          min: { type: 'number', minimum: 0 },
          minFunctionLength: { type: 'number', minimum: 0 },
          assertionNames: { type: 'array', items: { type: 'string' } },
          memberPatterns: { type: 'array', items: { type: 'string' } },
          methodNames: { type: 'array', items: { type: 'string' } },
          countThrowStatements: { type: 'boolean' },
          ioNames: { type: 'array', items: { type: 'string' } },
          ioObjects: { type: 'array', items: { type: 'string' } },
          treatAwaitAsIo: { type: 'boolean' },
          dynamicParamTypes: { type: 'array', items: { type: 'string' } },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      tooFew:
        "ASP202: function has {{count}} assertion(s); expected at least {{min}}. Add `assert(...)`, `invariant(...)`, or extend the rule's `assertionNames`/`memberPatterns`/`methodNames`/`countThrowStatements` if you use a different convention.",
    },
  },
  create(context) {
    const opts = context.options[0] ?? {};
    const min = opts.min ?? DEFAULT_MIN;
    const minLength = opts.minFunctionLength ?? DEFAULT_MIN_FUNCTION_LENGTH;
    const assertionNames = opts.assertionNames ?? DEFAULT_ASSERTION_NAMES;
    const memberPatterns = opts.memberPatterns ?? DEFAULT_MEMBER_PATTERNS;
    const methodNames = opts.methodNames ?? DEFAULT_METHOD_NAMES;
    const countThrowStatements = opts.countThrowStatements ?? DEFAULT_COUNT_THROW_STATEMENTS;
    const shellCfg = {
      ioNames: opts.ioNames ?? DEFAULT_IO_NAMES,
      ioObjects: opts.ioObjects ?? DEFAULT_IO_OBJECTS,
      treatAwaitAsIo: opts.treatAwaitAsIo ?? DEFAULT_TREAT_AWAIT_AS_IO,
      dynamicParamTypes: opts.dynamicParamTypes ?? DEFAULT_DYNAMIC_PARAM_TYPES,
    };

    function check(node) {
      if (!node.body || node.body.type !== 'BlockStatement') return;
      const length = node.loc.end.line - node.loc.start.line + 1;
      if (length < minLength) return;

      // FC/IS predicate: ASP202 is the imperative-shell mechanism. A
      // pure, statically-typed functional-core function is exempt — its
      // correctness is enforced by the other level-3 rules.
      if (!isImperativeShell(node, shellCfg)) return;

      const count = countAssertionsIn(
        node.body,
        assertionNames,
        memberPatterns,
        methodNames,
        countThrowStatements,
      );
      if (count < min) {
        context.report({
          node,
          messageId: 'tooFew',
          data: { count: String(count), min: String(min) },
        });
      }
    }

    return {
      FunctionDeclaration: check,
      FunctionExpression: check,
      ArrowFunctionExpression: check,
    };
  },
};
