import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { mkdtempSync, rmSync, existsSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { init } from './init.js';

describe('init', () => {
  let tmp: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'asp-init-'));
  });

  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  test('copies all four reference configs into the target dir', async () => {
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(existsSync(join(tmp, 'eslint.config.js'))).toBe(true);
    expect(existsSync(join(tmp, 'tsconfig.base.json'))).toBe(true);
    expect(existsSync(join(tmp, 'prettier.config.cjs'))).toBe(true);
    expect(existsSync(join(tmp, '.pre-commit-config.yaml'))).toBe(true);
  });

  test('does not overwrite existing files', async () => {
    const path = join(tmp, 'eslint.config.js');
    writeFileSync(path, 'existing-content');
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(readFileSync(path, 'utf8')).toBe('existing-content');
  });

  test('creates the target dir if missing', async () => {
    const nested = join(tmp, 'nested', 'repo');
    const code = await init({ target: nested });
    expect(code).toBe(0);
    expect(existsSync(join(nested, 'eslint.config.js'))).toBe(true);
  });
});
