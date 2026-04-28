// CLI-side layout name list. Mirrors typescript/layouts/index.js.
// Tasks adding a layout must update both lists.

import { createInterface } from 'node:readline';

export const LAYOUT_NAMES = [
  'node-service',
  'rn-app',
  'react-spa',
  'fullstack-monorepo',
  'generic-3-layer',
] as const;

export type LayoutName = (typeof LAYOUT_NAMES)[number] | 'none';

export const ALL_LAYOUT_CHOICES: readonly LayoutName[] = [...LAYOUT_NAMES, 'none'];

export function isValidLayout(s: string): s is LayoutName {
  return (ALL_LAYOUT_CHOICES as readonly string[]).includes(s);
}

const LAYOUT_DESCRIPTIONS: Record<LayoutName, string> = {
  'node-service': 'Express/Fastify backend with DB (core/db/services/routes)',
  'rn-app': 'React Native app (core/services/hooks/components/screens)',
  'react-spa': 'React/Vite SPA (shared/services/components/pages)',
  'fullstack-monorepo': 'Top-level server/, client/, shared/ dirs (no src/ nesting)',
  'generic-3-layer': 'Minimal FC/IS fallback (core/infra/app)',
  none: 'Skip — declare elements yourself in eslint.config.js',
};

export function describeLayout(name: LayoutName): string {
  return LAYOUT_DESCRIPTIONS[name];
}

/**
 * Prompt the user to pick a layout. Default is 'none'. Returns 'none' if
 * stdin is not a TTY (so non-interactive callers like CI silently get the
 * documented default).
 */
export async function promptForLayout(): Promise<LayoutName> {
  if (!process.stdin.isTTY) return 'none';

  process.stdout.write('\nPick an ASP205/206 boundary layout (you can change later):\n');
  ALL_LAYOUT_CHOICES.forEach((name, i) => {
    process.stdout.write(`  ${i + 1}) ${name.padEnd(20)} ${describeLayout(name)}\n`);
  });
  process.stdout.write(`Choice [${ALL_LAYOUT_CHOICES.indexOf('none') + 1}]: `);

  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const answer: string = await new Promise((resolve) => rl.question('', (a) => resolve(a)));
  rl.close();

  const trimmed = answer.trim();
  if (trimmed === '') return 'none';
  const n = Number.parseInt(trimmed, 10);
  if (Number.isFinite(n) && n >= 1 && n <= ALL_LAYOUT_CHOICES.length) {
    return ALL_LAYOUT_CHOICES[n - 1] as LayoutName;
  }
  if (isValidLayout(trimmed)) return trimmed;
  process.stdout.write(`Invalid choice "${trimmed}". Defaulting to "none".\n`);
  return 'none';
}
