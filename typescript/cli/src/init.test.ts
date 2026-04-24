import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { init } from './init.js';

const PKG_ESLINT = '@afdudley/aspergillus/eslint-config';
const PKG_PRETTIER = '@afdudley/aspergillus/prettier-config';
const PKG_TSCONFIG = '@afdudley/aspergillus/tsconfig';

describe('init', () => {
  let tmp: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'asp-init-'));
  });

  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  test('writes all four consumer config files', async () => {
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(existsSync(join(tmp, 'eslint.config.js'))).toBe(true);
    expect(existsSync(join(tmp, 'prettier.config.cjs'))).toBe(true);
    expect(existsSync(join(tmp, 'tsconfig.json'))).toBe(true);
    expect(existsSync(join(tmp, '.pre-commit-config.yaml'))).toBe(true);
  });

  test('eslint wrapper imports the aspergillus package export', async () => {
    await init({ target: tmp });
    const content = readFileSync(join(tmp, 'eslint.config.js'), 'utf8');
    expect(content).toContain(PKG_ESLINT);
    expect(content).toContain('export default [...base]');
  });

  test('prettier wrapper requires the aspergillus package export', async () => {
    await init({ target: tmp });
    const content = readFileSync(join(tmp, 'prettier.config.cjs'), 'utf8');
    expect(content).toContain(PKG_PRETTIER);
    expect(content).toContain('module.exports');
  });

  test('tsconfig.json extends the aspergillus package export', async () => {
    await init({ target: tmp });
    const parsed = JSON.parse(readFileSync(join(tmp, 'tsconfig.json'), 'utf8'));
    expect(parsed.extends).toBe(PKG_TSCONFIG);
  });

  test('backs up .prettierrc and writes fresh wrapper', async () => {
    writeFileSync(join(tmp, '.prettierrc'), '{ "printWidth": 120 }');
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(existsSync(join(tmp, '.prettierrc'))).toBe(false);
    expect(existsSync(join(tmp, '.prettierrc.local.bak'))).toBe(true);
    const wrapper = readFileSync(join(tmp, 'prettier.config.cjs'), 'utf8');
    expect(wrapper).toContain(PKG_PRETTIER);
  });

  test('backs up eslint.config.mjs variant', async () => {
    writeFileSync(join(tmp, 'eslint.config.mjs'), 'export default [];');
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(existsSync(join(tmp, 'eslint.config.mjs'))).toBe(false);
    expect(existsSync(join(tmp, 'eslint.config.mjs.local.bak'))).toBe(true);
    expect(existsSync(join(tmp, 'eslint.config.js'))).toBe(true);
  });

  test('backs up non-wrapper eslint.config.js', async () => {
    writeFileSync(join(tmp, 'eslint.config.js'), 'export default [{ rules: {} }];');
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(existsSync(join(tmp, 'eslint.config.js.local.bak'))).toBe(true);
    const wrapper = readFileSync(join(tmp, 'eslint.config.js'), 'utf8');
    expect(wrapper).toContain(PKG_ESLINT);
  });

  test('leaves existing aspergillus wrapper alone (idempotent re-init)', async () => {
    await init({ target: tmp });
    const original = readFileSync(join(tmp, 'eslint.config.js'), 'utf8');
    const code = await init({ target: tmp });
    expect(code).toBe(0);
    expect(existsSync(join(tmp, 'eslint.config.js.local.bak'))).toBe(false);
    expect(readFileSync(join(tmp, 'eslint.config.js'), 'utf8')).toBe(original);
  });

  test('warns about inline "prettier" key in package.json', async () => {
    writeFileSync(
      join(tmp, 'package.json'),
      JSON.stringify({ name: 'x', prettier: { printWidth: 120 } }),
    );
    const chunks: string[] = [];
    const orig = process.stdout.write.bind(process.stdout);
    process.stdout.write = ((s: string) => {
      chunks.push(s);
      return true;
    }) as typeof process.stdout.write;
    try {
      const code = await init({ target: tmp });
      expect(code).toBe(0);
    } finally {
      process.stdout.write = orig;
    }
    const out = chunks.join('');
    expect(out).toContain('"prettier" key in package.json');
    expect(existsSync(join(tmp, 'package.json'))).toBe(true);
  });

  test('detects npm when package-lock.json is present', async () => {
    writeFileSync(join(tmp, 'package-lock.json'), '{}');
    const chunks: string[] = [];
    const orig = process.stdout.write.bind(process.stdout);
    process.stdout.write = ((s: string) => {
      chunks.push(s);
      return true;
    }) as typeof process.stdout.write;
    try {
      await init({ target: tmp });
    } finally {
      process.stdout.write = orig;
    }
    const out = chunks.join('');
    expect(out).toContain('npm install -D');
    expect(out).toContain('(npm detected)');
    expect(out).toContain('@afdudley/aspergillus');
  });

  test('creates the target dir if missing', async () => {
    const nested = join(tmp, 'nested', 'repo');
    const code = await init({ target: nested });
    expect(code).toBe(0);
    expect(existsSync(join(nested, 'eslint.config.js'))).toBe(true);
  });

  test('returns 1 with a clean error message when target is a file', async () => {
    const filePath = join(tmp, 'not-a-dir');
    writeFileSync(filePath, '');
    const code = await init({ target: filePath });
    expect(code).toBe(1);
  });
});
