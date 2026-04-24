import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { mkdtempSync, rmSync, writeFileSync, copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { check } from './check.js';

const here = dirname(fileURLToPath(import.meta.url));
const CONFIGS_DIR = resolve(here, '..', '..', 'configs');

describe('check', () => {
  let tmp: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'asp-check-'));
  });

  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  test('returns 0 when consumer matches reference byte-for-byte', async () => {
    mkdirSync(tmp, { recursive: true });
    copyFileSync(join(CONFIGS_DIR, 'eslint.config.js'), join(tmp, 'eslint.config.js'));
    copyFileSync(join(CONFIGS_DIR, 'tsconfig.base.json'), join(tmp, 'tsconfig.base.json'));
    copyFileSync(join(CONFIGS_DIR, 'prettier.config.cjs'), join(tmp, 'prettier.config.cjs'));
    copyFileSync(join(CONFIGS_DIR, 'pre-commit-config.yaml'), join(tmp, '.pre-commit-config.yaml'));
    const code = await check({ target: tmp });
    expect(code).toBe(0);
  });

  test('returns 1 when a file is missing', async () => {
    const code = await check({ target: tmp });
    expect(code).toBe(1);
  });

  test('returns 1 when a file has drifted', async () => {
    copyFileSync(join(CONFIGS_DIR, 'eslint.config.js'), join(tmp, 'eslint.config.js'));
    copyFileSync(join(CONFIGS_DIR, 'tsconfig.base.json'), join(tmp, 'tsconfig.base.json'));
    copyFileSync(join(CONFIGS_DIR, 'prettier.config.cjs'), join(tmp, 'prettier.config.cjs'));
    writeFileSync(join(tmp, '.pre-commit-config.yaml'), 'drifted content\n');
    const code = await check({ target: tmp });
    expect(code).toBe(1);
  });
});
