// Shape tests for aspergillus layouts. Each layout exports an array of
// flat-config blocks: a boundaries block plus L3 stratification blocks.

import { describe, it, expect } from 'bun:test';

import genericThreeLayer from './generic-3-layer.js';
import nodeService from './node-service.js';
import reactSpa from './react-spa.js';
import rnApp from './rn-app.js';
import fullstackMonorepo from './fullstack-monorepo.js';

const ALL = {
  'generic-3-layer': genericThreeLayer,
  'node-service': nodeService,
  'react-spa': reactSpa,
  'rn-app': rnApp,
  'fullstack-monorepo': fullstackMonorepo,
};

const findBlock = (layout, predicate) => layout.find(predicate);
const hasFilesGlob = (block, substring) =>
  Array.isArray(block.files) && block.files.some((f) => f.includes(substring));

describe.each(Object.entries(ALL))('layout %s', (name, layout) => {
  it('exports an array of config blocks', () => {
    expect(Array.isArray(layout)).toBe(true);
    expect(layout.length).toBeGreaterThanOrEqual(3);
  });

  it('first block defines boundaries plugin and elements', () => {
    const first = layout[0];
    expect(first.plugins?.boundaries).toBeDefined();
    expect(first.settings?.['boundaries/elements']).toBeDefined();
  });

  it('has an FC block that warns no-throw-statements', () => {
    const fc = findBlock(
      layout,
      (b) => b.rules?.['functional/no-throw-statements'] === 'warn',
    );
    expect(fc).toBeDefined();
  });

  it('has a shell block that disables no-throw-statements', () => {
    const shell = findBlock(
      layout,
      (b) => b.rules?.['functional/no-throw-statements'] === 'off',
    );
    expect(shell).toBeDefined();
  });
});

describe('node-service stratification', () => {
  it('FC block targets core, db, services', () => {
    const fc = findBlock(
      nodeService,
      (b) => b.rules?.['functional/no-throw-statements'] === 'warn',
    );
    expect(hasFilesGlob(fc, '/core/')).toBe(true);
    expect(hasFilesGlob(fc, '/db/')).toBe(true);
    expect(hasFilesGlob(fc, '/services/')).toBe(true);
  });

  it('shell block targets routes', () => {
    const shell = findBlock(
      nodeService,
      (b) => b.rules?.['functional/no-throw-statements'] === 'off',
    );
    expect(hasFilesGlob(shell, '/routes/')).toBe(true);
  });
});

describe('fullstack-monorepo stratification', () => {
  it('FC block covers server- and client- FC element globs', () => {
    const fc = findBlock(
      fullstackMonorepo,
      (b) => b.rules?.['functional/no-throw-statements'] === 'warn',
    );
    expect(hasFilesGlob(fc, '/server/')).toBe(true);
    expect(hasFilesGlob(fc, '/client/')).toBe(true);
  });

  it('shell block covers server-routes and client-pages globs', () => {
    const shell = findBlock(
      fullstackMonorepo,
      (b) => b.rules?.['functional/no-throw-statements'] === 'off',
    );
    expect(hasFilesGlob(shell, '/routes/')).toBe(true);
    expect(hasFilesGlob(shell, '/pages/')).toBe(true);
  });
});
