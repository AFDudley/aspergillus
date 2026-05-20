// Tests for the @afdudley/aspergillus/errors reference helper.

import { describe, it, expect } from 'bun:test';

import { aspError } from './index.js';

describe('aspError', () => {
  it('creates an object with _tag and message', () => {
    const e = aspError('NotFound', 'user 42 missing');
    expect(e._tag).toBe('NotFound');
    expect(e.message).toBe('user 42 missing');
    expect(e.data).toBeUndefined();
    expect(e.cause).toBeUndefined();
  });

  it('attaches optional data', () => {
    const e = aspError('Validation', 'bad email', { field: 'email' });
    expect(e.data).toEqual({ field: 'email' });
  });

  it('attaches optional cause', () => {
    const inner = new Error('connection refused');
    const e = aspError('Db', 'database error', undefined, inner);
    expect(e.cause).toBe(inner);
  });

  it('preserves discriminated _tag literal', () => {
    const e1 = aspError('A', 'a');
    const e2 = aspError('B', 'b');
    expect(e1._tag).toBe('A');
    expect(e2._tag).toBe('B');
  });

  it('returns a frozen-shaped plain object (no prototype chain)', () => {
    const e = aspError('Plain', 'msg');
    expect(Object.getPrototypeOf(e)).toBe(Object.prototype);
    expect(e instanceof Error).toBe(false);
  });
});
