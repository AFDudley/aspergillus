# aspergillus — testing

Mechanics for the multi-engine code-quality rule corpus. A rule's "e2e" is the
rule **firing on real fixture code**: RED on a violating fixture, GREEN on a clean
one — the rule-author analogue of "no mocks in the path" (you run the real
engine over real source, you don't assert on the rule's internals).

- `python/tests/` — pytest over the fixit/LibCST Python rules
  (`test_catalog.py`, `test_cli.py`, `test_anti_special_casing.py` — the last
  proves a rule can't be satisfied by hardcoding the one fixture input).
- TypeScript rules — ast-grep / ESLint custom rules tested against fixture
  code the same way.

The corpus is severity-graduated (warn → promote); a new rule lands at `warn`
with fixture tests before it can `error`. See
[`decisions/2026-05-19-severity-graduation.md`](decisions/2026-05-19-severity-graduation.md).

## Testing policy

The gate is the rule firing on real fixtures (the "e2e"); a unit test of a rule's
helper is the inner loop. **Done = the rule discriminates real violating vs clean
code**, not that its helpers pass — an anti-special-casing test is the honesty
check that the rule generalizes. Full taxonomy + the by-construction-vs-empirical
split: `.claude/doctrine/testing.md` in the consuming monorepo; this file is
aspergillus's mechanics + the testing policy, so a standalone checkout is self-contained.
