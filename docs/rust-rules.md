# Aspergillus — Rust rule mapping

This document names, for every rule in the aspergillus catalog, the Rust
disposition: how a Rust workspace that adopts aspergillus gets that rule
checked. Each disposition is one of five kinds:

- **Clippy lint** — a lint the gate forces on via `cargo clippy`
  (`rust/src/clippy.rs`, `FORCED_LINTS`).
- **ast-grep rule** — a declarative YAML rule under `rust/ast-grep-rules/`,
  run by the gate through the `ast-grep-core`/`ast-grep-config`/
  `ast-grep-language` libraries.
- **Gate check** — logic in the gate's own crate (`rust/src/purity.rs`)
  that the declarative ast-grep engine cannot express, because the rule
  needs a count or a combined predicate over a function body, not one
  structural pattern.
- **Language feature** — the Rust compiler already enforces the rule; no
  gate check runs because none is needed.
- **Does not apply** — the rule's premise does not hold for Rust, or the
  rule needs information the gate cannot get without per-consumer
  configuration; the reason is stated inline.

A rule marked clippy lint, ast-grep rule, or gate check is a **checked
rule**: `rust/fixtures/<ASPnnn>/violating/` and
`rust/fixtures/<ASPnnn>/satisfying/` hold a committed Rust crate each, and
the gate reports a finding on the first and none on the second (verified
by `scripts/asp_rust_rule_audit.py --fixtures`).

Run the gate with `cargo run --manifest-path rust/Cargo.toml -- <workspace-dir>`.
Every finding prints as `path:line: ASPnnn`.

## Level 2 — Blocking

| Rule   | Disposition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ASP201 | Clippy lint: `clippy::too_many_lines`, threshold 60 via `rust/configs/clippy.toml`. Checked rule.                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ASP202 | Gate check: `rust/src/purity.rs::assertion_density_findings` — a non-test function past 5 lines with fewer than 2 recognized assertion forms: an `assert!`/`assert_eq!`/`assert_ne!`/`debug_assert!`-family macro, the `?` operator, a `return Err(..)` guard, `ok_or`/`ok_or_else`, or a validating constructor (`try_from`/`try_new`/`from_str`/`parse`). Scoped to the imperative SHELL (fires only outside the declared functional core): a pure, fully-typed core function earns its correctness statically. Checked rule. |
| ASP203 | Language feature: safe Rust has no mutable `static`; a `static mut` declaration requires `unsafe` to read or write, so this class of global mutable state does not compile as ordinary code. `rust/ast-grep-rules/asp203-no-static-mut.yml` still flags the declaration itself as a defense-in-depth check.                                                                                                                                                                                                                     |
| ASP204 | ast-grep rule: `rust/ast-grep-rules/asp204-no-infinite-loop.yml` — flags every `loop { ... }` construct (no statically-determinable bound). Checked rule.                                                                                                                                                                                                                                                                                                                                                                       |
| ASP205 | Gate check: `rust/src/purity.rs::impure_function_findings` — a function whose body calls a known Rust I/O name (filesystem, process, network, console). Scoped to the consumer's declared functional core (`rust/src/core_declaration.rs`): a finding requires both the I/O call and a workspace-relative path matching a `core_paths` glob in `aspergillus.toml` (or `--core-config`). Checked rule.                                                                                                                           |
| ASP206 | Gate check: `rust/src/purity.rs::mixed_io_logic_findings` — a function that both calls I/O and holds more than 3 top-level logic statements. Scoped to the imperative SHELL: fires only in a declared, non-core, non-test file (with a core declared), where mixing I/O with logic is untested shell logic to lift into the core; exempts `#[test]`/`#[cfg(test)]` code. Checked rule.                                                                                                                                          |

### ASP205/ASP206 — the functional-core declaration

A consumer declares which workspace paths hold the functional core in
`aspergillus.toml` at the scanned workspace's root (or a file named by
`--core-config`): a `core_paths` array of workspace-relative,
gitignore/fnmatch-style globs, e.g. `core_paths = ["statechart/**"]`.
`core_paths` glob is the imperative shell; a file that matches one is the
functional core. **ASP205** (impure function) fires inside the core: any
I/O in a core file is the finding, and I/O in the shell is legal.
**ASP206** (mixed I/O and logic) fires in the SHELL — a declared,
non-core file whose function calls I/O and also holds more than three
top-level logic statements: a thin shell is adapters between the world
and the core's types, so shell logic mixed with I/O is untested logic
whose fix is lifting it into the core. ASP206 does not fire inside the
core (ASP205 already flags core I/O there) nor on test code (`#[test]`/
`#[tokio::test]` functions, functions inside a `#[cfg(test)]` module, and
files under a `tests/` directory are exempt, as the Python sibling
exempts `test_`). The gate requires a declaration: an undeclared
workspace (no `aspergillus.toml` and no `--core-config`), an unreadable
file, or one that does not parse as a `core_paths` array is a hard input
error and exits `2` — the gate never silently disables ASP205/ASP206 (a
judge must not fail open). A workspace with genuinely no pure core says
so explicitly with `core_paths = []`: ASP205 then never fires and ASP206
treats every non-test file as shell. ASP202 is also shell-scoped (see its
own row above): it applies its assertion-density floor only to non-core,
non-test functions, exempting the pure, fully-typed functional core whose
correctness the type system already carries.

`rust/src/purity.rs`'s I/O detection matches a call by its qualified
path, not a bare method or function name, for the names collision-prone
enough to name an ordinary domain method too (`open`, `create`, `read`,
`write`, `send`, `recv`, `accept`, …): only a call qualified by a known
I/O-providing prefix (`std::fs::`, `File::`, `std::net::`,
`std::process::`, …) counts. `book.open()` on an in-memory value,
`json5::read(text)` over a `&str`, an `mpsc` `Receiver::recv`/
`SyncSender::send`, and a domain `create`/`accept` constructor all stay
unmatched. A small set of names unambiguous on any receiver
(`write_all`, `flush`, `sync_all`, …) match regardless of call form. The
walk descends into a closure body (so `iter().for_each(|p|
std::fs::write(p, ..))` is seen) but not into a nested `fn` item (scanned
as its own separate signal). `println!`/`eprintln!`/`print!`/`eprint!`/
`write!`/`writeln!`/`dbg!` all count as I/O macros, except a `write!`/`writeln!`
whose first argument is `f` or `formatter` — the near-universal parameter
names a `Display`/`Debug`/`serde::de::Visitor::expecting` impl gives its
`fmt::Formatter`, so a `write!(f, ..)`/`write!(formatter, ..)` there is an
in-memory format, not I/O.

Verified against the real `lobaria` workspace at commit `d0269c7`
(`rust/fixtures/lobaria-d0269c7/`, its own `aspergillus.toml` declaring
`statechart/**` as the core): `shell/src/machine.rs`'s `create`,
`shell/src/capture.rs`'s `decode_worker` (`mpsc` `send`/`recv`),
`backtest/src/replay.rs`'s `open_tokens` (`Book::open`), and
`chart/src/lib.rs`'s `load` (`json5::read`) — all previously false
positives — report nothing; `statechart`, lobaria's pure core, still
reports zero ASP205 and zero ASP206 findings. Pebble: asp-b7b.1.

## Level 3 — Warning

| Rule   | Disposition                                                                                                                                                                                                                                                                                                                                                                                    |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ASP301 | Clippy lint: `clippy::unwrap_used`, `clippy::expect_used`, `clippy::panic`, forced at `deny`. `Result<T, E>` is the idiomatic Rust failure channel these lints push toward. Checked rule.                                                                                                                                                                                                      |
| ASP302 | Language feature: Rust has no `null`; a value that may be absent is `Option<T>`, so a caller must match or unwrap it before use — the compiler refuses a bare access to a possibly-absent value.                                                                                                                                                                                               |
| ASP303 | Does not apply: the Python rule catches an error swallowed into a falsy success sentinel by a bare `except:` clause — a mechanism specific to exception-based control flow. Rust has no exceptions; a fallible Rust function returns `Result<T, E>`, so its fallibility is visible in the signature regardless of how the caller later handles the `Err` arm.                                  |
| ASP304 | Does not apply: the Python rule catches evidence discarded when an exception is re-raised without its original cause. Rust has no exception re-raise; propagating a Rust error is either `?` (which carries the original `Err` value forward unchanged) or an explicit `From`/`map_err` conversion the author writes out, so there is no re-raise path that silently drops the original error. |

## Catalog rules — ASP4xx

| Rule   | Disposition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ASP401 | Does not apply: `Iterator::map` is a lazy, generic (not virtual) adapter. Rust compiles two chained `.map(f).map(g)` calls to the same code as one fused closure after monomorphization and inlining — there is no separate heap-allocated intermediate and no per-element dispatch cost to fuse away, unlike Python's `map()` object.                                                                                                                                                                                    |
| ASP402 | Does not apply: `Iterator::filter` is the same kind of lazy, zero-cost adapter as `Iterator::map` — see ASP401.                                                                                                                                                                                                                                                                                                                                                                                                           |
| ASP403 | Clippy lint: `clippy::redundant_closure`, forced at `deny` — a closure that only forwards its argument to another function reduces to that function. Checked rule.                                                                                                                                                                                                                                                                                                                                                        |
| ASP404 | ast-grep rule: `rust/ast-grep-rules/asp404-redundant-conditional-bool.yml` — `if $COND { true } else { $Y }` collapses to a boolean-or of `$COND` and `$Y`. Checked rule.                                                                                                                                                                                                                                                                                                                                                 |
| ASP405 | Does not apply: the TypeScript rule this Python entry deliberately skips targets JavaScript's implicit await-on-return. Rust has the same guarantee Python has — no implicit await — so, as with the Python catalog (`python/src/aspergillus/rules/catalog/__init__.py`, "Why no ASP405"), this rule number stays unassigned for Rust too.                                                                                                                                                                                |
| ASP406 | Does not apply: the Python rule matches repeated calls to a closed set of builtin aggregation names (`sum`, `len`, `max`, …) over the same bound iterable name. Rust has no equivalent closed builtin set — aggregation is a generic `Iterator` method (`.sum()`, `.count()`, `.fold()`, …) chained off an arbitrary receiver expression, so proving two chains read "the same iterable" needs type and borrow information beyond syntactic matching.                                                                     |
| ASP407 | Does not apply: a function whose body is one forwarding call to another function is, in Rust, frequently a required trait-conformance shape — `Deref`/`DerefMut` for the newtype pattern, a trait method that must exist to satisfy an interface even when it only forwards. A blanket port of the Python heuristic would flag idiomatic Rust as often as it would flag a genuine accidental wrapper.                                                                                                                     |
| ASP408 | Does not apply: the Python rule's CI/test-environment-branching trigger targets `os.environ`-style runtime environment inspection. Rust's own idiomatic equivalent, `#[cfg(test)]`, is a compile-time conditional-compilation attribute the language provides for exactly this purpose — porting the Python trigger would flag ordinary Rust test modules, not gaming.                                                                                                                                                    |
| ASP409 | Does not apply: the Python rule takes a per-consumer `own_package` name so it can tell "this subprocess call invokes my own package" from an unrelated one. In a multi-crate Cargo workspace (aspergillus's first Rust consumer, lobaria, has 33), the analogous Rust signal — `Command::new(env!("CARGO_BIN_EXE_<name>"))` — cannot tell "the current crate's own binary" from "a workspace sibling's binary" without the same per-consumer identity the Python rule requires, which the gate does not yet parameterize. |
| ASP410 | Does not apply: identifying "this test file constructs the SUT in-process" needs to know what the SUT is, which the Python rule resolves through the same retargetable `own_package`-style configuration ASP409 needs (see the Python rule's own docstring). No default, consumer-independent trigger exists without it.                                                                                                                                                                                                  |
| ASP411 | Does not apply: detecting "likely redundant" branches needs a semantic near-duplicate comparison between two match-arm or if/else-if bodies, the same class of analysis as the duplicate-function whole-workspace check this deliverable does not include (a sibling deliverable's scope) — not a single structural ast-grep pattern.                                                                                                                                                                                     |
| ASP412 | Does not apply: flagging unbounded work inside a "transition body" needs the gate to know which functions are FSM transition handlers, a project-specific naming or trait convention with no default across arbitrary Rust workspaces.                                                                                                                                                                                                                                                                                    |
| ASP413 | Language feature: `match` on an enum-typed value is exhaustiveness-checked by the compiler — an arm-missing match fails to compile unless a wildcard (`_`) arm is present. The if/elif-dispatch shape the Python rule watches for has no non-exhaustive Rust analogue for the compiler to miss.                                                                                                                                                                                                                           |
| ASP414 | Does not apply: confirming a string-typed dispatch "shadows a same-module Enum's values" needs to resolve which enum, and that the match's subject really originates from stringifying it — type information beyond what syntactic ast-grep matching provides. A syntax-only trigger (e.g., any `match $X.as_str()`) would flag ordinary string dispatch with no corresponding enum at all.                                                                                                                               |
| ASP415 | Does not apply: this rule is specific to exophial's own Python reducer/daemon-start entry point (`python/src/aspergillus/rules/catalog/reducer_reachability.py`) — it has no general Rust analogue; it does not describe a Rust language or ecosystem concept at all.                                                                                                                                                                                                                                                     |
| ASP416 | Does not apply: confirming a return type's union arm is type-equal to a parameter's type needs real type resolution — generics, trait objects and lifetimes make syntactic name comparison unreliable in Rust in both directions (false positives on distinct types that print the same base name, false negatives on type aliases), unlike Python's simpler annotation-name comparison.                                                                                                                                  |
| ASP417 | Does not apply: the Python rule matches a configurable small set of effect method names plus a fixed set of stdlib I/O calls, then checks lexical precedence against a later rejection. Rust's effect surface is far less enumerable syntactically (traits, generics, no closed stdlib I/O naming convention the way Python's blocklist has), so the same fixed-set heuristic would both over- and under-match without semantic narrowing this gate's declarative ast-grep engine does not provide.                       |

## Whole-project checks (cross-file, not a Level or ASP4xx rule)

These are the Rust analogue of Python's `aspergillus check-duplicates`: a
fact only visible across the whole workspace, not one file. A dedicated
binary reads every crate and reports each occurrence as `path:line:
ASPnnn`, the same output shape the gate uses.

| Rule   | Disposition                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ASP502 | Whole-workspace check: `aspergillus-rust-dup-type-check` (`rust/src/duplicate_types.rs`, `rust/src/bin/aspergillus_rust_dup_type_check.rs`). Reports a struct or enum declared in more than one crate of a Cargo workspace with the same name and the same shape (a tuple struct's field count, a named-field struct's field-name list, or an enum's variant-name list — never each field's own type or visibility). Reads `--allowlist FILE`, one accepted type name per line with `#` comments, mirroring `aspergillus check-duplicates`. Verified against the real `lobaria` workspace at commit `a027fb9` (`rust/fixtures/lobaria-a027fb9/`, `scripts/oracle/`): it reports `Nanos` and `Receipt`, and stays silent about `Refused`, `Carried`, `Hit` and `Finding`, which share a name across files but not a shape. Pebble: asp-ce6.4. |
