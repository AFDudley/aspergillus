// RuleTester suite for asp202-min-assertions. Run via `bun test`.

import { RuleTester } from 'eslint';
import { describe, it } from 'bun:test';
import tsParser from '@typescript-eslint/parser';

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

// Type-aware cases set this per-case parser so the rule can observe
// explicit `any` / `unknown` parameter annotations (the untrusted-data
// boundary). Consumers run the rule under exactly this parser.
const TS = { parser: tsParser };

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

// The assertion-COUNTING fixtures below all carry a leading `fetch(x)` so
// the FC/IS gate classifies them as imperative shell (in scope). They
// exercise the assertion-counting / recognition logic (asp-070), which is
// only reached for shell functions. `fetch` is not an assertion name, so
// it does not contribute to the count.
tester.run('asp202-min-assertions', rule, {
  valid: [
    // Trivial function: under default minFunctionLength (10 lines) — exempt.
    { code: 'function add(a, b) { return a + b; }' },

    // Two bare assert() calls (shell function: enough assertions => ok).
    {
      code: `function f(x) {
        fetch(x);
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
        fetch(x);
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
        fetch(x);
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
        fetch(x);
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
        fetch(input);
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
        fetch(input);
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
        fetch(x);
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

    // ── FC/IS predicate (asp-da5): functional core is EXEMPT ──────────
    // Pure (no I/O), no dynamically-typed parameter -> functional core.
    // Correctness is type/purity enforced; exempt despite 0 assertions.
    // (>= minFunctionLength, so the exemption is the FC/IS gate, not the
    // short-function shortcut.)
    {
      code: `function pureTransform(x) {
        const a = x + 1;
        const b = a * 2;
        const c = b - 3;
        const d = c / 4;
        const e = d + 5;
        const g = e - 6;
        const h = g + 7;
        const i = h - 8;
        return i;
      }`,
    },
    // Pure transform whose params are CONCRETELY typed (number) -> still
    // functional core under the type-aware parser: exempt.
    {
      code: `function scale(x: number, k: number): number {
        const a = x * k;
        const b = a + 1;
        const c = b - 2;
        const d = c * 3;
        const e = d + 4;
        const f = e - 5;
        const g = f * 6;
        const h = g + 7;
        return h;
      }`,
      languageOptions: TS,
    },
  ],

  invalid: [
    // Long shell function (calls fetch) with zero assertions.
    {
      code: `function f(x) { fetch(x);${longBody}}`,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },

    // One assertion, default min is 2.
    {
      code: `function f(x) {
        fetch(x);
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
        fetch(x);
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
        fetch(x);
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
        fetch(x);
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
        fetch(input);
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
        fetch(x);
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

    // ── FC/IS predicate (asp-da5): imperative shell IS in scope ───────
    // Performs I/O (a method on a known I/O object) with 0 assertions ->
    // imperative shell, flagged.
    {
      code: `function persist(key, value) {
        const payload = String(value);
        const stamped = payload + ':' + key;
        const sized = stamped.length;
        const upper = stamped.toUpperCase();
        const tag = upper.slice(0, 4);
        const ok = sized > 0;
        const marker = tag + ':' + sized;
        localStorage.setItem(key, marker);
        return ok;
      }`,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },
    // `await` marks the body as imperative shell (async I/O), 0 assertions.
    {
      code: `async function load(client, id) {
        const url = '/items/' + id;
        const res = await client.get(url);
        const body = res.data;
        const name = body.name;
        const size = body.size;
        const label = name + ':' + size;
        const trimmed = label.trim();
        return { name, size, trimmed };
      }`,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },
    // Pure, but a parameter is explicitly typed `any` -> untrusted-data
    // boundary -> imperative shell, flagged (type-aware parser).
    {
      code: `function normalize(payload: any): string {
        const raw = payload;
        const keys = Object.keys(raw);
        const first = keys[0];
        const rest = keys.slice(1);
        const joined = rest.join(',');
        const upper = joined.toUpperCase();
        const sized = upper.length;
        const tag = sized > 0 ? upper : first;
        return first + tag;
      }`,
      languageOptions: TS,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },
    // `unknown` parameter is likewise an untrusted boundary -> flagged.
    {
      code: `function decode(input: unknown): number {
        const v = input;
        const s = String(v);
        const n = s.length;
        const m = n * 2;
        const r = m - 1;
        const t = r + n;
        const u = t - m;
        const w = u * 3;
        return w;
      }`,
      languageOptions: TS,
      errors: [{ messageId: 'tooFew', data: { count: '0', min: '2' } }],
    },
  ],
});
