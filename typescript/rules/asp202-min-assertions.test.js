// RuleTester suite for asp202-min-assertions. Run via `bun test`.

import { RuleTester } from 'eslint';
import { describe, it } from 'bun:test';

import rule from './asp202-min-assertions.js';

// Wire bun:test into RuleTester. ESLint v9 RuleTester calls
// RuleTester.describe / RuleTester.it directly; assigning bun:test's
// versions makes the suite report through the bun runner.
RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it;

const tester = new RuleTester({
  languageOptions: { ecmaVersion: 2022, sourceType: 'module' },
});

const longBody = `
  // line 1
  // line 2
  // line 3
  // line 4
  // line 5
  // line 6
  // line 7
  // line 8
  // line 9
  return x;
`;

tester.run('asp202-min-assertions', rule, {
  valid: [
    // Trivial function: under default minFunctionLength (10 lines) — exempt.
    { code: 'function add(a, b) { return a + b; }' },

    // Two bare assert() calls.
    {
      code: `function f(x) {
        assert(x > 0);
        assert(x < 100);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
    },

    // Namespace methods on a configured assertionName count: assert.ok, assert.equal.
    {
      code: `function f(x) {
        assert.ok(x);
        assert.equal(x, 1);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
    },

    // console.assert counts (from default memberPatterns).
    {
      code: `function f(x) {
        console.assert(x !== null);
        console.assert(x !== undefined);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
    },

    // Custom assertionNames option recognizes 'check'.
    {
      code: `function f(x) {
        check(x > 0);
        check(x < 100);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
      options: [{ assertionNames: ['check'] }],
    },

    // methodNames matches `.parse(...)` regardless of receiver. Two
    // distinct receivers, both count.
    {
      code: `function f(input) {
        const a = schemaA.parse(input);
        const b = schemaB.parse(input);
        const c = 1;
        const d = 2;
        const e = 3;
        const g = 4;
        const h = 5;
        return [a, b, c, d, e, g, h];
      }`,
      options: [{ methodNames: ['parse'] }],
    },

    // methodNames also matches when the receiver is a chained call
    // (`z.string().parse(...)`), since we only check the property name.
    {
      code: `function f(input) {
        const a = z.string().parse(input);
        const b = z.number().parse(input);
        const c = 1;
        const d = 2;
        const e = 3;
        const g = 4;
        const h = 5;
        return [a, b, c, d, e, g, h];
      }`,
      options: [{ methodNames: ['parse'] }],
    },

    // countThrowStatements: throw statements count as assertions when
    // enabled. Two `if (!x) throw` patterns satisfy min=2.
    {
      code: `function f(x, y) {
        if (!x) throw new Error('x required');
        if (!y) throw new Error('y required');
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + y + a + b + c + d + e;
      }`,
      options: [{ countThrowStatements: true }],
    },

    // Arrow functions with non-block body are skipped (no body to count).
    { code: 'const f = (x) => x + 1;' },
  ],

  invalid: [
    // Long function with zero assertions.
    {
      code: `function f(x) {${longBody}}`,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },

    // One assertion, default min is 2.
    {
      code: `function f(x) {
        assert(x > 0);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        const g = 6;
        return x + a + b + c + d + e + g;
      }`,
      errors: [{ messageId: 'tooFew', data: { count: '1', min: '2' } }],
    },

    // Nested function bodies are NOT counted toward the outer function's
    // assertion total — each function is checked independently.
    {
      code: `function outer(x) {
        function inner(y) {
          assert(y > 0);
          assert(y < 100);
          return y;
        }
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        return inner(x) + a + b + c + d;
      }`,
      errors: [
        // outer has 0 assertions, fails.
        // inner has 2 but is only 5 lines — under minFunctionLength, exempt.
        { messageId: 'tooFew', data: { count: '0', min: '2' } },
      ],
    },

    // Custom min option.
    {
      code: `function f(x) {
        assert(x > 0);
        assert(x < 100);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
      options: [{ min: 3 }],
      errors: [{ messageId: 'tooFew', data: { count: '2', min: '3' } }],
    },

    // Custom assertionNames REPLACES the default — `assert` no longer counts.
    {
      code: `function f(x) {
        assert(x > 0);
        assert(x < 100);
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + a + b + c + d + e;
      }`,
      options: [{ assertionNames: ['check'] }],
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },

    // methodNames is opt-in: without it, `.parse(...)` doesn't count.
    {
      code: `function f(input) {
        const a = schemaA.parse(input);
        const b = schemaB.parse(input);
        const c = 1;
        const d = 2;
        const e = 3;
        const g = 4;
        const h = 5;
        return [a, b, c, d, e, g, h];
      }`,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },

    // countThrowStatements is opt-in: without it, `throw` doesn't count.
    {
      code: `function f(x, y) {
        if (!x) throw new Error('x required');
        if (!y) throw new Error('y required');
        const a = 1;
        const b = 2;
        const c = 3;
        const d = 4;
        const e = 5;
        return x + y + a + b + c + d + e;
      }`,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },
  ],
});
