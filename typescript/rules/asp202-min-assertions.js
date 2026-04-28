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

const DEFAULT_MIN = 2;
const DEFAULT_MIN_FUNCTION_LENGTH = 10;
const DEFAULT_ASSERTION_NAMES = ['assert', 'invariant'];
const DEFAULT_MEMBER_PATTERNS = ['console.assert'];
const DEFAULT_METHOD_NAMES = [];
const DEFAULT_COUNT_THROW_STATEMENTS = false;

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

    function check(node) {
      if (!node.body || node.body.type !== 'BlockStatement') return;
      const length = node.loc.end.line - node.loc.start.line + 1;
      if (length < minLength) return;

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
