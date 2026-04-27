// ASP202 — assertion density.
//
// NASA Power of 10 #5: minimum two assertions per function. Reports
// non-trivial functions whose bodies contain fewer than `min` assertion-
// like calls. Defaults skip short functions (< minFunctionLength lines)
// since the rule's intent is non-trivial logic, not 3-line helpers.
//
// Recognized as assertions by default:
//   assert(...)             — node:assert default export, or top-level
//                             helper conventionally named `assert`
//   assert.ok / .equal …    — namespace methods on `assert`
//   invariant(...)          — common helper convention
//   console.assert(...)     — JS host
//
// Consumers extend the lists via `assertionNames` (bare callee name)
// or `memberPatterns` (full `obj.method` form).

const DEFAULT_MIN = 2;
const DEFAULT_MIN_FUNCTION_LENGTH = 10;
const DEFAULT_ASSERTION_NAMES = ['assert', 'invariant'];
const DEFAULT_MEMBER_PATTERNS = ['console.assert'];

function isAssertionCall(node, assertionNames, memberPatterns) {
  if (node.type !== 'CallExpression') return false;
  const callee = node.callee;

  if (callee.type === 'Identifier') {
    return assertionNames.includes(callee.name);
  }

  if (
    callee.type === 'MemberExpression' &&
    !callee.computed &&
    callee.object.type === 'Identifier' &&
    callee.property.type === 'Identifier'
  ) {
    const full = `${callee.object.name}.${callee.property.name}`;
    if (memberPatterns.includes(full)) return true;
    // `assert.ok(...)`, `assert.equal(...)` etc. when `assert` is in
    // assertionNames — namespace methods on a configured name count.
    if (assertionNames.includes(callee.object.name)) return true;
  }

  return false;
}

function countAssertionsIn(rootBody, assertionNames, memberPatterns) {
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
    if (isAssertionCall(node, assertionNames, memberPatterns)) {
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
        },
        additionalProperties: false,
      },
    ],
    messages: {
      tooFew:
        "ASP202: function has {{count}} assertion(s); expected at least {{min}}. Add `assert(...)`, `invariant(...)`, or extend the rule's `assertionNames`/`memberPatterns` if you use a different convention.",
    },
  },
  create(context) {
    const opts = context.options[0] ?? {};
    const min = opts.min ?? DEFAULT_MIN;
    const minLength = opts.minFunctionLength ?? DEFAULT_MIN_FUNCTION_LENGTH;
    const assertionNames = opts.assertionNames ?? DEFAULT_ASSERTION_NAMES;
    const memberPatterns = opts.memberPatterns ?? DEFAULT_MEMBER_PATTERNS;

    function check(node) {
      if (!node.body || node.body.type !== 'BlockStatement') return;
      const length = node.loc.end.line - node.loc.start.line + 1;
      if (length < minLength) return;

      const count = countAssertionsIn(node.body, assertionNames, memberPatterns);
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
