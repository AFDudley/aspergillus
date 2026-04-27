#!/usr/bin/env node
// Aspergillus TypeScript CLI.
// Commands: init, check. See typescript/README.md for adoption workflow.

import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { check } from './check.js';
import { init } from './init.js';

const USAGE = `aspergillus-ts <command>

Commands:
  init [--target <dir>]      Copy reference configs into target dir (default: cwd)
  check [--target <dir>]     Diff consumer config vs reference; exit 1 on drift

Flags:
  --target <dir>             Consumer repo root (default: cwd)
  -h, --help                 Show this message
`;

type Args = { command: string | undefined; target: string; help: boolean };

export function parseArgs(argv: readonly string[]): Args {
  const rest = argv.slice(2);
  let target = process.cwd();
  let help = false;
  let command: string | undefined;
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === '-h' || a === '--help') help = true;
    else if (a === '--target') target = rest[++i] ?? target;
    else if (!command) command = a;
  }
  return { command, target, help };
}

export async function main(argv: readonly string[]): Promise<number> {
  const { command, target, help } = parseArgs(argv);
  if (help || !command) {
    process.stdout.write(USAGE);
    return help ? 0 : 1;
  }
  switch (command) {
    case 'init':
      return init({ target });
    case 'check':
      return check({ target });
    default:
      process.stderr.write(`unknown command: ${command}\n\n${USAGE}`);
      return 1;
  }
}

// Run when invoked directly as a CLI. Uses realpath comparison so that
// symlinked bin entries (e.g. node_modules/.bin/aspergillus-ts) match.
function isMainEntry(): boolean {
  try {
    const modulePath = realpathSync(fileURLToPath(import.meta.url));
    const argv1 = process.argv[1];
    return argv1 !== undefined && realpathSync(argv1) === modulePath;
  } catch {
    return false;
  }
}

if (isMainEntry()) {
  void main(process.argv).then((code) => process.exit(code));
}
