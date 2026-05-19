// Aspergillus ESLint plugin — flat-config compatible.
//
// Hosts custom rules that don't have a sufficient off-the-shelf
// equivalent. Add new rules to the `rules` map here and re-export the
// rule object from a sibling file.

import asp202MinAssertions from './asp202-min-assertions.js';

export default {
  meta: {
    name: '@afdudley/aspergillus',
    // Bumped manually alongside the package version. Used by ESLint flat
    // config in error reporting and cache keys.
    version: '0.1.0-rc.3',
  },
  rules: {
    'asp202-min-assertions': asp202MinAssertions,
  },
};
