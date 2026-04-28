#!/usr/bin/env node
// Aspergillus TypeScript CLI.
// Commands: init, check. See typescript/README.md for adoption workflow.

import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { check } from './check.js';
import { init } from './init.js';
import { ALL_LAYOUT_CHOICES, isValidLayout, type LayoutName } from './layouts.js';

const USAGE = `aspergillus-ts <command> [flags]

Commands:
  init [--target <dir>] [--layout <name>]
                             Copy reference configs into target dir.
                             --layout selects an ASP205/206 boundary
                             layout. If omitted, prompts (or 'none' on
                             non-TTY). Valid: ${ALL_LAYOUT_CHOICES.join(', ')}.
  check [--target <dir>]     Diff consumer config vs reference; exit 1 on drift

Flags:
  --target <dir>             Consumer repo root (default: cwd)
  --layout <name>            ASP205/206 layout (init only)
  -h, --help                 Show this message
`;

type Args = {
  command: string | undefined;
  target: string;
  layout: LayoutName | undefined;
  help: boolean;
};

export function parseArgs(argv: readonly string[]): Args {
  const rest = argv.slice(2);
  let target = process.cwd();
  let layout: LayoutName | undefined;
  let help = false;
  let command: string | undefined;
  // Accept both `--flag value` and `--flag=value` forms for any flag that
  // takes a value. Returns [value, advance] — `advance` is true when the
  // value was the next arg and the loop index must be advanced past it.
  function flagValue(arg: string, name: string): [string, boolean] | undefined {
    if (arg === name) {
      const next = rest[i + 1];
      return next !== undefined ? [next, true] : undefined;
    }
    if (arg.startsWith(`${name}=`)) return [arg.slice(name.length + 1), false];
    return undefined;
  }

  let i = 0;
  for (; i < rest.length; i++) {
    const a = rest[i] ?? '';
    if (a === '-h' || a === '--help') {
      help = true;
      continue;
    }
    const targetMatch = flagValue(a, '--target');
    if (targetMatch !== undefined) {
      target = targetMatch[0];
      if (targetMatch[1]) i++;
      continue;
    }
    const layoutMatch = flagValue(a, '--layout');
    if (layoutMatch !== undefined) {
      const v = layoutMatch[0];
      if (isValidLayout(v)) layout = v;
      else
        process.stderr.write(
          `unknown layout: ${v} (valid: ${ALL_LAYOUT_CHOICES.join(', ')})\n`,
        );
      if (layoutMatch[1]) i++;
      continue;
    }
    if (!command) command = a;
  }
  return { command, target, layout, help };
}

export async function main(argv: readonly string[]): Promise<number> {
  const { command, target, layout, help } = parseArgs(argv);
  if (help || !command) {
    process.stdout.write(USAGE);
    return help ? 0 : 1;
  }
  switch (command) {
    case 'init':
      return init({ target, layout });
    case 'check':
      return check({ target });
    default:
      process.stderr.write(`unknown command: ${command}\n\n${USAGE}`);
      return 1;
  }
}

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
