# Aspergillus — TypeScript

Reference ESLint, tsconfig, Prettier, and pre-commit configs for applying
the aspergillus rule set to TypeScript projects (Node services, React/Vite
apps, shared libraries).

## What's here

- `configs/eslint.config.js` — reference flat config, Level 1 baseline
- `configs/tsconfig.base.json` — strict TypeScript compiler baseline
- `configs/prettier.config.cjs` — Prettier 3 config
- `configs/pre-commit-config.yaml` — pre-commit hooks (ESLint + Prettier)
- `cli/` — `aspergillus-ts` CLI (`init`, `check`)

Consumers install aspergillus via npm (from GitHub in Phase 1, from a
registry later in Phase 2). The CLI exposes `init` / `check` as a
standard npm bin.

## Adoption

1. **Install aspergillus and peer devDependencies:**

   ```bash
   npm install -D github:AFDudley/aspergillus#main @eslint/js typescript-eslint \
     eslint-plugin-import eslint-plugin-unused-imports eslint-config-prettier \
     eslint prettier typescript
   ```

   (Use your project's package manager — `bun add -D …`, `pnpm add -D …`,
   `yarn add -D …` all work.)

2. **Run `init` to write consumer wrappers at the repo root:**

   ```bash
   npx aspergillus-ts init
   ```

   `init` writes:
   - `eslint.config.js` — spreads `@afdudley/aspergillus/eslint-config`
   - `prettier.config.cjs` — spreads `@afdudley/aspergillus/prettier-config`
   - `tsconfig.json` — `extends: "@afdudley/aspergillus/tsconfig"`
   - `.pre-commit-config.yaml` — scaffold copy (consumer owns it)

   If any of those files (or equivalent variants like `.prettierrc`,
   `eslint.config.mjs`, etc.) already exist, `init` renames them to
   `<name>.local.bak` and writes fresh aspergillus wrappers. Consumers
   port any repo-specific overrides into the wrappers below the spread.

3. **Run the tools:**

   ```bash
   npx eslint . --fix
   npx prettier --write .
   npx tsc --noEmit
   ```

4. **Detect drift via `check` (optional, wire into CI):**

   ```bash
   npx aspergillus-ts check
   ```

   Exits non-zero if any wrapper no longer references aspergillus.

5. **Update aspergillus:**

   ```bash
   npm update @afdudley/aspergillus
   npx aspergillus-ts check
   ```

## Severity-flip workflow

Every new aspergillus rule lands at `warn`. It stays `warn` until the
tree has zero violations for that rule; then a dedicated PR flips it to
`error`. Rationale: separates the "adopt the rule" change (reviewable
mechanics) from the "fix every existing violation" change (reviewable
scope).

This is the main incremental axis — not level-preset switching. Level 2
and Level 3 rules are appended to the same reference `eslint.config.js`
over time; each new rule is subject to the warn→error flip in each
consumer.

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

## Distribution phases

- **Phase 1 (current): git-URL npm install.** Consumers add
  `github:AFDudley/aspergillus#main` as a devDependency. npm clones the
  repo, runs the root `prepare` script (which builds `typescript/cli/dist/`
  via `tsc`), and exposes the package via the `exports` map. Works with
  `npm`, `pnpm`, `yarn`, and `bun` — no registry auth needed.

- **Phase 2 (planned): registry publish.** Once the package stabilizes,
  publish `@afdudley/aspergillus` to GitHub Packages. Consumers migrate
  with a one-line change in `package.json`:

  ```diff
  - "@afdudley/aspergillus": "github:AFDudley/aspergillus#main"
  + "@afdudley/aspergillus": "^0.1.0"
  ```

  Package name, `exports` paths, and import specifiers stay identical.
  No changes required in `eslint.config.js`, `prettier.config.cjs`, or
  `tsconfig.json`.

## Development

Aspergillus's own CLI tests run under bun:

```bash
cd typescript/cli
bun install
bun test
bun run build
```

Consumers do not need bun — the root `prepare` script uses `tsc` via
npm-installed `typescript`.
