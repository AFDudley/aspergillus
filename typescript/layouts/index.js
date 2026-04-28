// Internal barrel — lists the layout names aspergillus ships. The CLI's
// `aspergillus-ts init --layout=<name>` flag validates against this list.
// Consumers import individual layouts via `@afdudley/aspergillus/layouts/<name>`,
// not this file (which is excluded from the publish manifest).

export const LAYOUT_NAMES = [
  'node-service',
  'rn-app',
  'react-spa',
  'fullstack-monorepo',
  'generic-3-layer',
];
