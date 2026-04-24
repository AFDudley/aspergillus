import { describe, test, expect, beforeEach, afterEach } from 'bun:test';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { init } from './init.js';
import { check } from './check.js';

describe('check', () => {
  let tmp: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), 'asp-check-'));
  });

  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  test('returns 0 immediately after init', async () => {
    await init({ target: tmp });
    const code = await check({ target: tmp });
    expect(code).toBe(0);
  });

  test('returns 0 when the consumer has added overrides to wrappers', async () => {
    await init({ target: tmp });
    writeFileSync(
      join(tmp, 'eslint.config.js'),
      `import base from './vendor/aspergillus/typescript/configs/eslint.config.js';
export default [...base, { rules: { 'no-console': 'error' } }];
`,
    );
    const code = await check({ target: tmp });
    expect(code).toBe(0);
  });

  test('returns 1 when a config is missing', async () => {
    const code = await check({ target: tmp });
    expect(code).toBe(1);
  });

  test('returns 1 when eslint.config.js no longer imports the vendored config', async () => {
    await init({ target: tmp });
    writeFileSync(join(tmp, 'eslint.config.js'), 'export default [];');
    const code = await check({ target: tmp });
    expect(code).toBe(1);
  });

  test('returns 1 when tsconfig.json extends something else', async () => {
    await init({ target: tmp });
    writeFileSync(
      join(tmp, 'tsconfig.json'),
      JSON.stringify({ extends: './other/tsconfig.json' }),
    );
    const code = await check({ target: tmp });
    expect(code).toBe(1);
  });
});
