# Aspergillus — TypeScript

Reference ESLint, tsconfig, Prettier, and pre-commit configs for applying
the aspergillus rule set to TypeScript projects (Node services, React/Vite
apps, shared libraries).

## What's here

- `configs/eslint.config.js` — reference flat config, Level 1 baseline
- `configs/tsconfig.base.json` — strict TypeScript compiler baseline
- `configs/prettier.config.cjs` — Prettier 3 config
- `configs/pre-commit-config.yaml` — pre-commit hooks (ESLint + Prettier)
- `cli/` — `aspergillus-ts` stub CLI (`init`, `check`)

## Adoption (subtree era)

1. **Add aspergillus as a subtree** in your repo:

   ```bash
   git subtree add --prefix vendor/aspergillus <repo-url> main --squash
   ```

2. **Build the CLI once:**

   ```bash
   cd vendor/aspergillus/typescript/cli && bun install && bun run build && cd -
   ```

3. **Run `init` to copy reference configs into the repo root:**

   ```bash
   node vendor/aspergillus/typescript/cli/dist/index.js init
   ```

   `init` writes (but never overwrites) `eslint.config.js`,
   `tsconfig.base.json`, `prettier.config.cjs`, and `.pre-commit-config.yaml`,
   then prints the `bun add -D …` command for peer devDependencies.

4. **Install the printed devDependencies, then run the linter once with
   auto-fix:**

   ```bash
   bun run eslint . --fix
   ```

5. **Pull updates** by re-running the subtree pull and then `check`:

   ```bash
   git subtree pull --prefix vendor/aspergillus <repo-url> main --squash
   node vendor/aspergillus/typescript/cli/dist/index.js check
   ```

   `check` exits non-zero on any drift from the reference. Wire it into CI
   if you want drift enforcement.

## Severity-flip workflow

Every new rule lands at `warn`. It stays at `warn` until the tree has zero
violations for that rule; then a dedicated PR flips it to `error`. Rationale:
separates the "adopt the rule" change (reviewable mechanics) from the
"fix every existing violation" change (reviewable scope).

This is the main incremental axis — not level-preset switching. Level 2
and Level 3 rules are appended to the same `eslint.config.js` over time;
each new rule is subject to the warn→error flip.

## Rule mapping (summary)

See `../docs/design.md` for the authoritative ASP ID ↔ per-language tool
mapping. For TypeScript the short form is:

| ASP | Tooling |
|-----|---------|
| 201 | `max-lines-per-function` |
| 202 | Manual (assertion density — code review) |
| 203 | `functional/no-let`, `functional/immutable-data` |
| 204 | `functional/no-loop-statements` |
| 205 | `eslint-plugin-boundaries` (architecture enforcement) |
| 206 | `eslint-plugin-boundaries` + project layering |
| 301 | `functional/no-throw-statements`, `@okee-tech/neverthrow/must-consume-result` |
| 302 | `strictNullChecks` in tsconfig + neverthrow-typed returns |

## Future: published packages

Once the reference configs stabilize across 3+ consumer repos, these will
be published to GitHub Packages as `@afdudley/eslint-config`,
`@afdudley/tsconfig`, `@afdudley/prettier-config`, and
`@afdudley/aspergillus-ts`. Consumer config collapses to:

```js
// eslint.config.js
import base from '@afdudley/eslint-config';
export default [...base, /* repo overrides */];
```

```json
// tsconfig.json
{ "extends": "@afdudley/tsconfig" }
```

Trigger: N=3 TS consumers, or the first breaking change that needs
coordinated updates across consumers.
