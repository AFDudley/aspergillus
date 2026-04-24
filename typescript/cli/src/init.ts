import { existsSync, mkdirSync, copyFileSync, writeFileSync, readFileSync, renameSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  CONFLICTS,
  INLINE_KEYS,
  isEslintWrapper,
  isPrettierWrapper,
  isTsconfigWrapper,
} from './wrappers.js';

// Reference configs live in ../../configs/ relative to the compiled CLI.
// Works at both bun-test time (src/) and post-build (dist/).
const here = dirname(fileURLToPath(import.meta.url));
const CONFIGS_DIR = resolve(here, '..', '..', 'configs');

const DEV_DEPS = [
  '@eslint/js',
  'typescript-eslint',
  'eslint-plugin-import',
  'eslint-plugin-unused-imports',
  'eslint-config-prettier',
  'eslint',
  'prettier',
  'typescript',
] as const;

type InitOpts = { target: string };

function relImport(from: string, to: string): string {
  const rel = relative(from, to).replace(/\\/g, '/');
  return rel.startsWith('.') ? rel : './' + rel;
}

function detectPackageManager(target: string): 'bun' | 'pnpm' | 'yarn' | 'npm' {
  if (existsSync(join(target, 'bun.lock')) || existsSync(join(target, 'bun.lockb'))) return 'bun';
  if (existsSync(join(target, 'pnpm-lock.yaml'))) return 'pnpm';
  if (existsSync(join(target, 'yarn.lock'))) return 'yarn';
  return 'npm'; // default; covers package-lock.json and no-lockfile cases
}

function devDepCommand(pm: 'bun' | 'pnpm' | 'yarn' | 'npm'): string {
  const deps = DEV_DEPS.join(' ');
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

// Human-readable error message for filesystem failures. Anything else
// rethrows — only convert OS-level errors, not bugs.
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

// Look at every known conflicting filename for `slot` in `target`. If a
// match already IS the aspergillus wrapper, return `our-wrapper`. If it's
// a competing config, back it up and return `backed-up`. If none exist,
// return `none`.
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

    // Is this the slot's primary filename AND already our wrapper? Leave it.
    if (name === wrapperName) {
      const src = readOrNull(path);
      if (src !== null && isWrapperFor(slot, src)) {
        return 'our-wrapper';
      }
    }

    const backupPath = path + '.local.bak';
    // If a .local.bak already exists, append a timestamp to avoid clobbering.
    const finalBackup = existsSync(backupPath)
      ? `${backupPath}.${Date.now()}`
      : backupPath;
    renameSync(path, finalBackup);
    backups.push({ from: name, to: finalBackup.slice(target.length + 1) });
    sawConflict = true;
  }

  return sawConflict ? 'backed-up' : 'none';
}

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

export async function init({ target }: InitOpts): Promise<number> {
  try {
    return await runInit({ target });
  } catch (err) {
    const msg = describeError(err);
    if (msg === null) throw err;
    process.stderr.write(`aspergillus-ts init failed: ${msg}\n`);
    return 1;
  }
}

async function runInit({ target }: InitOpts): Promise<number> {
  mkdirSync(target, { recursive: true });
  const rel = relImport(target, CONFIGS_DIR);
  const backups: { from: string; to: string }[] = [];

  const eslintWrapper = `// Aspergillus wrapper. Spreads the vendored reference config; add
// repo-specific overrides after the spread.
import base from '${rel}/eslint.config.js';

export default [...base];
`;

  const prettierWrapper = `// Aspergillus wrapper. Spreads the vendored reference; add overrides below.
module.exports = {
  ...require('${rel}/prettier.config.cjs'),
};
`;

  const tsconfigWrapper =
    JSON.stringify({ extends: `${rel}/tsconfig.base.json` }, null, 2) + '\n';

  writeSlot(target, 'eslint', eslintWrapper, backups);
  writeSlot(target, 'prettier', prettierWrapper, backups);
  writeSlot(target, 'tsconfig', tsconfigWrapper, backups);

  // Pre-commit has no native extends mechanism; copy the scaffold verbatim,
  // but only if the consumer doesn't already have their own.
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

  printBackupSummary(backups, rel);

  const inline = detectInlineConfigs(target);
  if (inline.length > 0) printInlineWarning(inline);

  const pm = detectPackageManager(target);
  process.stdout.write(`\nNext: install devDependencies (${pm} detected) —\n`);
  process.stdout.write(`  ${devDepCommand(pm)}\n`);
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

function printBackupSummary(
  backups: { from: string; to: string }[],
  rel: string,
): void {
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
      `    ...require('${rel}/prettier.config.cjs'),\n` +
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
