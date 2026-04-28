import { existsSync, mkdirSync, writeFileSync, readFileSync, renameSync, copyFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  CONFLICTS,
  INLINE_KEYS,
  PACKAGE_SPECIFIERS,
  isEslintWrapper,
  isPrettierWrapper,
  isTsconfigWrapper,
} from './wrappers.js';
import { promptForLayout, type LayoutName } from './layouts.js';

// Reference pre-commit scaffold lives next to the configs. Works at both
// bun-test time (src/) and post-build (dist/).
const here = dirname(fileURLToPath(import.meta.url));
const CONFIGS_DIR = resolve(here, '..', '..', 'configs');

// Peer devDependencies consumers install alongside aspergillus itself.
const BASE_DEV_DEPS = [
  '@afdudley/aspergillus',
  '@eslint/js',
  'typescript-eslint',
  'eslint-plugin-functional',
  'eslint-plugin-import',
  'eslint-plugin-unused-imports',
  'eslint-config-prettier',
  'eslint',
  'prettier',
  'typescript',
] as const;

const LAYOUT_DEV_DEPS = ['eslint-plugin-boundaries'] as const;

type InitOpts = { target: string; layout?: LayoutName };

function detectPackageManager(target: string): 'bun' | 'pnpm' | 'yarn' | 'npm' {
  if (existsSync(join(target, 'bun.lock')) || existsSync(join(target, 'bun.lockb'))) return 'bun';
  if (existsSync(join(target, 'pnpm-lock.yaml'))) return 'pnpm';
  if (existsSync(join(target, 'yarn.lock'))) return 'yarn';
  return 'npm'; // default; covers package-lock.json and no-lockfile cases
}

function depsForLayout(layout: LayoutName): readonly string[] {
  return layout === 'none' ? BASE_DEV_DEPS : [...BASE_DEV_DEPS, ...LAYOUT_DEV_DEPS];
}

function devDepCommand(pm: 'bun' | 'pnpm' | 'yarn' | 'npm', layout: LayoutName): string {
  const deps = depsForLayout(layout).join(' ');
  switch (pm) {
    case 'bun':
      return `bun add -D ${deps}`;
    case 'pnpm':
      return `pnpm add -D ${deps}`;
    case 'yarn':
      return `yarn add -D ${deps}`;
    case 'npm':
      return `npm install -D ${deps}`;
  }
}

function describeError(err: unknown): string | null {
  if (err instanceof Error && typeof (err as NodeJS.ErrnoException).code === 'string') {
    return (err as NodeJS.ErrnoException).message;
  }
  return null;
}

function readOrNull(path: string): string | null {
  try {
    return readFileSync(path, 'utf8');
  } catch {
    return null;
  }
}

type Slot = 'eslint' | 'prettier' | 'tsconfig' | 'preCommit';

function wrapperFilenameFor(slot: Slot): string {
  switch (slot) {
    case 'eslint':
      return 'eslint.config.js';
    case 'prettier':
      return 'prettier.config.cjs';
    case 'tsconfig':
      return 'tsconfig.json';
    case 'preCommit':
      return '.pre-commit-config.yaml';
  }
}

function isWrapperFor(slot: Slot, src: string): boolean {
  switch (slot) {
    case 'eslint':
      return isEslintWrapper(src);
    case 'prettier':
      return isPrettierWrapper(src);
    case 'tsconfig':
      return isTsconfigWrapper(src);
    case 'preCommit':
      // Pre-commit is scaffold-only; no wrapper marker. Treat any existing
      // file as "owned by the consumer" and skip.
      return true;
  }
}

function handleConflicts(
  target: string,
  slot: Slot,
  backups: { from: string; to: string }[],
): 'our-wrapper' | 'backed-up' | 'none' {
  const candidates = CONFLICTS[slot];
  const wrapperName = wrapperFilenameFor(slot);
  let sawConflict = false;

  for (const name of candidates) {
    const path = join(target, name);
    if (!existsSync(path)) continue;

    if (name === wrapperName) {
      const src = readOrNull(path);
      if (src !== null && isWrapperFor(slot, src)) {
        return 'our-wrapper';
      }
    }

    const backupPath = path + '.local.bak';
    const finalBackup = existsSync(backupPath)
      ? `${backupPath}.${Date.now()}`
      : backupPath;
    renameSync(path, finalBackup);
    backups.push({ from: name, to: finalBackup.slice(target.length + 1) });
    sawConflict = true;
  }

  return sawConflict ? 'backed-up' : 'none';
}

function detectInlineConfigs(target: string): string[] {
  const pkgPath = join(target, 'package.json');
  const src = readOrNull(pkgPath);
  if (src === null) return [];
  try {
    const parsed = JSON.parse(src) as Record<string, unknown>;
    const warnings: string[] = [];
    if (parsed[INLINE_KEYS.prettier] !== undefined)
      warnings.push(`"${INLINE_KEYS.prettier}" key in package.json`);
    if (parsed[INLINE_KEYS.eslint] !== undefined)
      warnings.push(`"${INLINE_KEYS.eslint}" key in package.json`);
    return warnings;
  } catch {
    return [];
  }
}

export async function init(opts: InitOpts): Promise<number> {
  try {
    return await runInit(opts);
  } catch (err) {
    const msg = describeError(err);
    if (msg === null) throw err;
    process.stderr.write(`aspergillus-ts init failed: ${msg}\n`);
    return 1;
  }
}

async function runInit(opts: InitOpts): Promise<number> {
  const { target } = opts;
  const layout: LayoutName = opts.layout ?? (await promptForLayout());

  mkdirSync(target, { recursive: true });
  const backups: { from: string; to: string }[] = [];

  const layoutSpec = `@afdudley/aspergillus/layouts/${layout}`;

  const layoutImport =
    layout === 'none'
      ? ''
      : `import layout from '${layoutSpec}';\n`;

  const layoutSpread = layout === 'none' ? '' : '  layout,\n';

  const layoutComments =
    layout === 'none'
      ? `// To enable ASP205/206 layered-import enforcement, declare
// settings['boundaries/elements'] in this config (or re-run
// 'aspergillus-ts init --layout=<name>' to import a preset).
`
      : `// To switch layouts: change the import above to one of:
//   '@afdudley/aspergillus/layouts/node-service'
//   '@afdudley/aspergillus/layouts/rn-app'
//   '@afdudley/aspergillus/layouts/react-spa'
//   '@afdudley/aspergillus/layouts/fullstack-monorepo'
//   '@afdudley/aspergillus/layouts/generic-3-layer'
//
// To customize WITHOUT switching layouts, append your overrides AFTER
// 'layout' above. Settings merge deeply; the last block wins for any
// 'boundaries/elements' or rule options you redefine. Example:
//   {
//     settings: { 'boundaries/elements': [
//       { type: 'core', pattern: 'src/lib/**' },
//     ] },
//   },
`;

  const eslintWrapper = `// Aspergillus wrapper. Spreads the package reference; add repo-specific
// overrides after the spread.
import base from '${PACKAGE_SPECIFIERS.eslint}';
${layoutImport}
export default [
  ...base,
${layoutSpread}];

${layoutComments}`;

  const prettierWrapper = `// Aspergillus wrapper. Spreads the package reference; add overrides below.
module.exports = {
  ...require('${PACKAGE_SPECIFIERS.prettier}'),
};
`;

  const tsconfigWrapper =
    JSON.stringify({ extends: PACKAGE_SPECIFIERS.tsconfig }, null, 2) + '\n';

  writeSlot(target, 'eslint', eslintWrapper, backups);
  writeSlot(target, 'prettier', prettierWrapper, backups);
  writeSlot(target, 'tsconfig', tsconfigWrapper, backups);

  const preCommitResult = handleConflicts(target, 'preCommit', backups);
  if (preCommitResult === 'our-wrapper') {
    process.stdout.write(`skip (exists): .pre-commit-config.yaml\n`);
  } else {
    copyFileSync(
      join(CONFIGS_DIR, 'pre-commit-config.yaml'),
      join(target, '.pre-commit-config.yaml'),
    );
    process.stdout.write(`wrote: .pre-commit-config.yaml\n`);
  }

  printBackupSummary(backups);

  if (layout !== 'none') {
    process.stdout.write(`\nASP205/206 layout: ${layout}\n`);
  } else {
    process.stdout.write(`\nASP205/206 layout: none (skipped — see eslint.config.js comments)\n`);
  }

  const inline = detectInlineConfigs(target);
  if (inline.length > 0) printInlineWarning(inline);

  const pm = detectPackageManager(target);
  process.stdout.write(`\nNext: install aspergillus and its peer devDependencies (${pm} detected) —\n`);
  process.stdout.write(`  ${devDepCommand(pm, layout)}\n`);
  return 0;
}

function writeSlot(
  target: string,
  slot: Exclude<Slot, 'preCommit'>,
  content: string,
  backups: { from: string; to: string }[],
): void {
  const result = handleConflicts(target, slot, backups);
  const wrapperPath = join(target, wrapperFilenameFor(slot));
  if (result === 'our-wrapper') {
    process.stdout.write(`skip (our wrapper): ${wrapperFilenameFor(slot)}\n`);
    return;
  }
  writeFileSync(wrapperPath, content);
  process.stdout.write(`wrote: ${wrapperFilenameFor(slot)}\n`);
}

function printBackupSummary(backups: { from: string; to: string }[]): void {
  if (backups.length === 0) return;
  process.stdout.write('\n─ Backed up existing configs ──────────────────────\n');
  process.stdout.write(
    'Aspergillus is now the source of truth for these files.\n' +
      'Your previous configs were preserved as .local.bak:\n\n',
  );
  for (const { from, to } of backups) {
    process.stdout.write(`  ${from}  →  ${to}\n`);
  }
  process.stdout.write(
    '\nNext step: port any repo-specific overrides into the aspergillus\n' +
      'wrappers, below the spread. Example for prettier:\n\n' +
      '  // prettier.config.cjs\n' +
      '  module.exports = {\n' +
      `    ...require('${PACKAGE_SPECIFIERS.prettier}'),\n` +
      '    printWidth: 120,                  // ← your overrides\n' +
      '  };\n\n' +
      'Delete the .local.bak files once you have migrated the overrides.\n',
  );
}

function printInlineWarning(warnings: string[]): void {
  process.stdout.write('\n─ Warning: inline config in package.json ─────────\n');
  for (const w of warnings) process.stdout.write(`  - ${w}\n`);
  process.stdout.write(
    '\nAspergillus cannot back this up automatically. Remove the key(s)\n' +
      'from package.json and move any overrides into the matching wrapper.\n',
  );
}
