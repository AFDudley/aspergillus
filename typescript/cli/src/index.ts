#!/usr/bin/env node
// Aspergillus TypeScript CLI.
// Commands: init, check. See typescript/README.md for adoption workflow.

import { init } from './init.js';
import { check } from './check.js';

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

if (import.meta.url === `file://${process.argv[1]}`) {
  main(process.argv).then((code) => process.exit(code));
}
