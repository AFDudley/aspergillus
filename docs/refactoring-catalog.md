# Refactoring Catalog

The finite set of canonical refactoring moves an aspergillus-consuming
coordinator chooses from at dispatch time.

This file is the **canonical corpus**, maintained upstream in
aspergillus. Consumers either (a) consume the catalog by reference from
this file via the subtree, or (b) keep a slim consumer-side companion
that adds project-specific applicability notes layered on top of this
corpus. See the consumer-policy section at the end for the project-
applicability extension pattern.

The catalog is grounded in primary sources, not training-distribution
priors. Each move cites its source; moves without citations are not
in the catalog.

## Primary sources

- **Fowler, Martin.** *Refactoring: Improving the Design of Existing
  Code*, 2nd ed (Addison-Wesley, 2018). Canonical reference. Catalog
  mirrored at <https://refactoring.com/catalog/>. **"Fowler"** below.
- **Kerievsky, Joshua.** *Refactoring to Patterns* (Addison-Wesley,
  2004). Moves toward Gang-of-Four design patterns; flagged below
  where the move is OOP-centric and has an FP alternative.
- **Hughes, John.** "Why Functional Programming Matters" (1989),
  <https://www.cs.kent.ac.uk/people/staff/dat/miranda/whyfp90.pdf>.
  Justifies higher-order function moves.
- **Krishnamurthi, Shriram.** *Programming Languages: Application
  and Interpretation* (PLAI), <https://www.plai.org/>. Justifies the
  data-as-program / extract-interpreter family of moves.
- **Elliott, Conal.** "Denotational design with type class morphisms"
  and the broader denotational design corpus. Justifies the "find the
  algebra hiding in the code" framing.
- **Thompson, Simon + Reinke, Claus.** "Refactoring Functional
  Programs" (University of Kent Computing Lab Technical Report
  50-02, 2001). The canonical academic FP-Fowler analogue;
  enumerates binding-scope-aware moves (Generalise, Fold/Unfold,
  Promote/Demote, Lambda-lifting).
- **Burstall, R.M. + Darlington, J.** "A Transformation System
  for Developing Recursive Programs" (J. ACM 24(1), 1977).
  Primary source for the Fold / Unfold move — the foundational
  equational rewriting pair every later FP-refactoring catalogue
  inherits.
- **Bird, Richard + de Moor, Oege.** *Algebra of Programming*
  (Prentice Hall, 1997). Bird-Meertens formalism: catamorphisms,
  anamorphisms, fusion laws (map-fusion, filter-fusion, fold-
  fusion / banana split). Recursion-scheme algebra introduced in
  Meijer, Fokkinga, Paterson, "Functional Programming with
  Bananas, Lenses, Envelopes and Barbed Wire" (FPCA 1991).
- **Bird, Richard.** *Pearls of Functional Algorithm Design*
  (Cambridge University Press, 2010). Tupling and Accumulating
  Parameter as named techniques; tabulation techniques originally
  in Bird, "Tabulation Techniques for Recursive Programs" (ACM
  Comput. Surv. 1980). Accumulator-passing-style theory in Wand,
  M., "Continuation-Based Program Transformation Strategies"
  (J. ACM 1980).
- **Wadler, Philip.** "Theorems for Free!" (FPCA 1989). Free
  theorems from polymorphic type signatures; naturality-driven
  rewrites.
- **Gill, Andy + Hutton, Graham.** "The Worker/Wrapper
  Transformation" (J. Funct. Program. 19(2), 2009). Worker/
  Wrapper factorization with the correctness theorem. The
  performance-refactoring shape `newtype` and `deriving via`
  exploit in Haskell.
- **Johnsson, Thomas.** "Lambda Lifting: Transforming Programs
  to Recursive Equations" (FPCA 1985). Primary source for
  Lambda-Lifting.
- **Gill, Andy + Launchbury, John + Peyton Jones, Simon.** "A
  Short Cut to Deforestation" (FPCA 1993). `foldr/build` fusion;
  the primary source for the deforestation-via-rewrite-rules
  technique.
- **Mitchell, Neil.** *HLint*, <https://github.com/ndmitchell/hlint>.
  ~700 machine-checked declarative source-rewrite rules for
  Haskell. Each hint is a named rewrite with explicit LHS ⇒ RHS;
  the catalog adopts the structurally-significant subset (eta-
  reduction, boolean-conditional collapse, `concatMap` for
  `concat . map`, `foldr/build` fusion, named conversions) and
  excludes the hygiene-only hints (redundant parens, etc.) per
  the cut documented in the FP section below.

## Catalog of moves

Grouped by Fowler's category structure. Names are canonical from
Fowler unless otherwise noted. Each entry: name; trigger; behavior-
preservation guarantee; source.

### Basic moves

- **Extract Function** (Fowler ch. 6). Trigger: a code fragment is
  doing one identifiable thing and is used in 2+ places OR is hard
  to understand inline. Guarantee: every call site produces the
  same output; tests at every call site stay green.
- **Inline Function** (Fowler ch. 6). Trigger: function body is as
  clear as the function name; the indirection adds no value.
  Guarantee: every call site behaves identically with the body in
  place of the call.
- **Extract Variable** (Fowler ch. 6). Trigger: an expression is
  complex enough that naming it clarifies; or it's used 2+ times
  in the same scope. Guarantee: variable's value is referentially
  transparent (no side effects in the expression).
- **Inline Variable** (Fowler ch. 6). Trigger: variable adds no
  clarity beyond inlining its expression. Guarantee: expression
  is referentially transparent.
- **Change Function Declaration** (Fowler ch. 6; aliases: Rename
  Function, Add/Remove Parameter, Change Signature). Trigger: name
  no longer reflects behavior; parameter list has unused or wrong-
  typed parameters. Guarantee: every caller updated; tests green.
- **Rename Variable / Rename Field** (Fowler ch. 6). Trigger: name
  is misleading or unclear. Guarantee: every reader sees the new
  name; semantics unchanged.

### Encapsulation

- **Encapsulate Variable** (Fowler ch. 6; aliases: Self-Encapsulate
  Field). Trigger: direct variable access from many sites; need to
  centralize read/write logic. Guarantee: reads and writes go
  through a function; observable behavior unchanged.
- **Encapsulate Record** (Fowler ch. 7; alias: Replace Record with
  Data Class). Trigger: a plain record is being mutated in place
  by multiple callers; need read-only or controlled-write
  semantics. Guarantee: same data shape; mutation paths controlled.
- **Encapsulate Collection** (Fowler ch. 7). Trigger: a collection
  is exposed and mutated by callers. Guarantee: callers use
  controlled add/remove methods.
- **Hide Delegate** (Fowler ch. 7). Trigger: a class exposes a
  delegate that callers then chain calls through (`a.getB().doX()`).
  Guarantee: callers go through the holder; the delegate is hidden.
- **Remove Middle Man** (Fowler ch. 7). Trigger: a class delegates
  so much that exposing the delegate would clarify. Inverse of
  Hide Delegate.

### Moving features

- **Move Function** (Fowler ch. 8; alias: Move Method). Trigger:
  a function references another module's data more than its own;
  or it logically belongs elsewhere. Guarantee: same callers,
  different import path; tests green.
- **Move Field** (Fowler ch. 8). Trigger: a field is accessed
  primarily from another module. Guarantee: data shape preserved;
  access paths updated.
- **Move Statements into Function** (Fowler ch. 8). Trigger:
  statements before/after a function call always run together
  with it. Guarantee: behavior identical.
- **Move Statements to Callers** (Fowler ch. 8). Inverse of the
  above.
- **Slide Statements** (Fowler ch. 8; alias: Consolidate Duplicate
  Conditional Fragments). Trigger: statements that should be
  adjacent are separated by unrelated code. Guarantee: no
  dependency reordering; behavior preserved.
- **Split Phase** (Fowler ch. 6). Trigger: a function does N
  distinct kinds of work that don't share state. Guarantee: each
  phase's output is the next phase's input; whole-function behavior
  unchanged.

### Organizing data

- **Replace Primitive with Object** (Fowler ch. 7; aliases: Replace
  Data Value with Object, Replace Type Code with Class). Trigger:
  a primitive (string, number) carries domain meaning and is used
  in multiple operations. Guarantee: callers update to use the
  object; underlying value preserved.
- **Replace Temp with Query** (Fowler ch. 7). Trigger: a local
  variable holds a value computed once; the computation could be
  re-run cheaply. Guarantee: query is referentially transparent.
- **Introduce Parameter Object** (Fowler ch. 6). Trigger: a
  parameter list contains the same group of values across multiple
  functions. Guarantee: each caller bundles the values into the
  object; same arguments reach the function bodies.
- **Replace Magic Literal** (Fowler ch. 9; alias: Replace Magic
  Number with Symbolic Constant). Trigger: a literal value appears
  in multiple places with no name explaining its meaning.
  Guarantee: every reference updated; value unchanged.

### Simplify conditional logic

- **Decompose Conditional** (Fowler ch. 10). Trigger: a conditional
  expression or block is complex enough that extracting the
  condition and the body into named functions clarifies. Guarantee:
  same branches taken; same effects.
- **Consolidate Conditional Expression** (Fowler ch. 10). Trigger:
  several condition checks lead to the same result and can be
  unioned. Guarantee: combined condition matches the union of the
  individual conditions.
- **Replace Nested Conditional with Guard Clauses** (Fowler ch. 10).
  Trigger: nested `if/else` with early returns hidden inside.
  Guarantee: early returns produce the same return values as the
  matching nested branches.
- **Replace Conditional with Polymorphism** (Fowler ch. 10).
  Trigger: a `switch` over a type code drives different behavior
  per case; the cases share enough structure to be a type
  hierarchy. **FP alternative: Replace Conditional with Data
  Table** (see "Replace Switch with Data Table" below) — the FP
  move uses a discriminated union + lookup table rather than
  polymorphic subclasses. Prefer the FP variant in FP-leaning
  codebases. Guarantee: every case produces the same output as
  before.
- **Introduce Special Case** (Fowler ch. 10; alias: Introduce Null
  Object). Trigger: many callers check for a special value (null,
  zero, empty) and branch. Guarantee: the special-case object
  responds to the same methods as the normal case, producing the
  branch-taken behavior.
- **Introduce Assertion** (Fowler ch. 10). Trigger: an assumption
  is implicit in the code; an explicit check would document it.
  Guarantee: assertions never fire in correct execution; they
  fire-loud on doctrine violations.

### Refactoring APIs

- **Separate Query from Modifier** (Fowler ch. 11). Trigger: a
  function both returns a value AND mutates state. Guarantee:
  the query is referentially transparent; the modifier returns
  nothing.
- **Parameterize Function** (Fowler ch. 11; alias: Parameterize
  Method). Trigger: 2+ functions do the same thing with different
  hard-coded values. Guarantee: each call site passes the value
  that was hard-coded.
- **Remove Flag Argument** (Fowler ch. 11; alias: Replace Parameter
  with Explicit Methods). Trigger: a function has a boolean
  parameter that selects between two different behaviors.
  Guarantee: two explicit functions replace the flagged one; every
  caller updated to call the right function.
- **Replace Error Code with Exception** (Fowler ch. 11). Trigger:
  a function returns a sentinel error value that callers check;
  exception handling would be clearer. **FP alternative: use a
  `Result<T, E>` type** (e.g. `neverthrow` in TypeScript) —
  never raise exceptions; encode errors in the return type.
  Guarantee: error paths are reachable via match on Result.
- **Replace Exception with Precheck** (Fowler ch. 11). Trigger:
  exceptional conditions are routine and predictable; a guard
  clause is clearer. Guarantee: the precheck rejects exactly the
  inputs the exception would have caught.

### Collections / loops

- **Replace Loop with Pipeline** (Fowler ch. 8). Trigger: a `for`
  or `while` loop is doing a sequence of map / filter / reduce
  steps. Guarantee: the pipeline produces the same final value.
  Justified at the FP level by **Hughes (1989)** §3-4 on the
  composability of higher-order functions.
- **Split Loop** (Fowler ch. 8). Trigger: a loop does N
  independent things in the same body. Guarantee: the loops can
  be re-ordered freely; total side effects identical.

### Inheritance (mostly OOP-centric; flagged for non-applicability in FP codebases)

- **Replace Subclass with Delegate** / **Replace Superclass with
  Delegate** (Fowler ch. 12; alias: Replace Inheritance with
  Delegation). Trigger: a subclass relationship is more naturally
  a composition. **Applicability in FP-leaning consumers:**
  inheritance hierarchies are not idiomatic; these moves apply
  rarely. When they do, prefer the FP alternative: a tagged-union
  type + match-over-variant rendering.
- **Collapse Hierarchy** (Fowler ch. 12). Trigger: a subclass adds
  nothing distinguishing. **Applicability in FP-leaning consumers:**
  rare.
- **Replace Type Code with Subclasses** (Fowler ch. 12). **FP
  alternative: Replace Type Code with Discriminated Union.** The
  FP form preserves exhaustiveness checking and avoids OOP-shape
  state coupling.

### FP-specific / data-as-program moves

- **Replace Switch with Data Table** (synthesized from Fowler's
  "Replace Conditional with Polymorphism" + Krishnamurthi PLAI's
  interpreter pattern). Trigger: a reducer or other function's
  `switch` statement has cases that share structural shape (same
  state-transition pattern with different labels). Move: extract
  the switch as a `Map<DiscriminatorValue, Handler>` data table
  + a single interpreter function that looks up the handler and
  applies it. Guarantee: each discriminator-value's handler
  receives the same arguments and produces the same output as
  the corresponding switch case. **This is the canonical move
  that state-machine extracts execute** (`useMachine`, `StateChart`,
  `interpret`).
- **Parameterize Over Data / Extract Interpreter** (Krishnamurthi
  PLAI ch. 17-18, the meta-circular evaluator pattern). Trigger:
  N isomorphic algorithms differ only in their data tables.
  Move: write ONE algorithm parameterized by data; each instance
  becomes a data value handed to the interpreter. Guarantee: the
  interpreter applied to each data instance produces the same
  output as the original N algorithms. **Justification at the
  language-theory level:** programs are data; data is programs;
  separating them is a category error.
- **Replace Imperative Loop with Higher-Order Function** (Hughes
  1989 §3, §4). Trigger: a loop that maps, filters, folds, or
  scans. Move: replace with `Array.prototype.map`/`filter`/
  `reduce` (TypeScript) or analogous higher-order operations.
  Guarantee: composability with other higher-order functions; the
  loop body becomes a named function.
- **Push Effects to the Edge** (Elliott denotational design;
  echoed in React's "You Might Not Need an Effect" docs). Trigger:
  side effects are interleaved with pure computation. Move:
  separate the pure computation (state → state); fire the side
  effect from a single point (a useEffect in React; a state-entry
  effect in a state machine). Guarantee: the pure portion is
  referentially transparent and testable in isolation.

The moves below extend this section with the named refactorings
from the FP primary sources cited above. They are grouped by
source to make citations easy to audit; ordering within the
section is by source, not by frequency-of-use. The HIGH-LEVERAGE
moves frequent in React-FP-TS consumers are flagged inline
(map-fusion, filter-fusion, Tupling, Eta-Reduction, Worker/Wrapper).

#### Thompson + Reinke 2001 (binding-scope-aware moves)

- **Generalise Definition** (Thompson + Reinke, "Refactoring
  Functional Programs," Kent TR 50-02, 2001, §3). Trigger: a
  function body contains a literal or fixed sub-expression that
  should vary across call sites. Move: lift the literal to a
  parameter; every call site passes the value previously hard-
  coded. FP-binding-aware analogue of Fowler's `Parameterize
  Function`. Rewrite:

  ```
  f x = e[c]            ⇒    f c x = e[c]
                              -- update call sites: f x  ⇒  f c x
  ```

  Guarantee: each call site receives the same value the literal
  previously had; behavior preserved. **Consumer applicability
  (TS-React):** translatable directly. Cite the FP version when
  the binding hierarchy is the unit of refactoring (`core/`,
  `services/`); cite Fowler's `Parameterize Function` for OO-
  shape call sites.

- **Fold / Unfold** (Burstall + Darlington, "A Transformation
  System for Developing Recursive Programs," J. ACM 1977 —
  primary source; Thompson + Reinke 2001 §3 for the FP-
  refactoring framing). Trigger: a function call could be
  replaced by its body (unfold), or a body-shape could be
  replaced by an equivalent call (fold). Foundational pair for
  equational reasoning. Rewrite:

  ```
  unfold:  f x     ⇒  e[x]      where f x = e[x]
  fold:    e[x]    ⇒  f x       where f x = e[x]
  ```

  Guarantee: by definitional equality of the rewritten call to
  its body. **Consumer applicability (TS-React):** TS-translatable
  directly — `unfold` is `Inline Function`, `fold` is `Extract
  Function`. The Fowler names are catalogued under Basic moves.
  Cite Fold / Unfold when reasoning equationally about a chain
  (e.g., justifying `Replace Loop with Pipeline` → `map-fusion`
  → `Inline Function` as a fold/unfold sequence).

- **Promote Definition / Demote Definition** (Thompson + Reinke
  2001 §4). Trigger (promote): a `where` / `let` binding is used
  outside its current scope or duplicated across sibling scopes.
  Trigger (demote): a top-level binding is used in exactly one
  site and its name doesn't add clarity. Move: lift the binding
  to a wider scope, or push it down. Binding-scope-aware analogue
  of `Move Function`. Rewrite:

  ```
  promote:  f x = let g y = e in body
            ⇒  g y = e
               f x = body                -- g now top-level
  demote:   g y = e
            f x = ... g ...
            ⇒  f x = let g y = e in body
  ```

  Guarantee: every reference resolves identically; behavior
  unchanged. **Consumer applicability (TS-React):** TS-translatable
  to module-level function declarations and nested functions in
  components/hooks. Higher friction than in Haskell because
  closure-over-state semantics differ between hoisted and
  inlined arrow functions — verify capture is preserved (React's
  stale-closure trap).

- **Lambda-Lifting / Lambda-Dropping** (Johnsson, "Lambda
  Lifting: Transforming Programs to Recursive Equations," FPCA
  1985 — primary source; revisited in Thompson + Reinke 2001
  §5). Trigger (lift): a closure captures free variables and is
  allocated in a hot path; lifting them to parameters allows
  hoisting the lambda to module scope and reusing one function
  value. Trigger (drop): a top-level helper takes passthrough
  arguments threaded by exactly one caller; folding it into a
  closure clarifies. Rewrite:

  ```
  lift:  \x -> ... y ...        ⇒  helper y x = ... y ...
         -- y is free                \x -> helper y x
  drop:  helper y x = ... y ...  ⇒  \x -> ... y ...
         -- y in scope at call site
  ```

  Guarantee: each closure-allocation point and each free-
  variable reference is preserved by construction. **Consumer
  applicability (TS-React):** TS-translatable directly.
  Particularly relevant in React: inline arrow handlers in JSX
  (`onPress={() => doX(y)}`) re-allocate every render and break
  memoization; lift to `useCallback`-wrapped functions or
  module-scope helpers. Combines with `eslint-plugin-functional`
  `no-loop-statements` pressure toward higher-order functions to
  keep allocations stable across renders.

#### Bird + de Moor 1997 (Bird-Meertens formalism)

- **map-fusion** (Bird + de Moor, *Algebra of Programming*,
  1997, §2.6 "Fusion laws"; introduced in Bird, "An Introduction
  to the Theory of Lists," NATO ASI 1987). **HIGH-LEVERAGE for
  FP consumers.** Trigger: two consecutive `map` calls in a
  pipeline. Move: replace with one `map` over composed functions.
  Rewrite:

  ```
  map f . map g  ≡  map (f . g)
  xs.map(g).map(f)  ⇒  xs.map(x => f(g(x)))
  ```

  Guarantee: by the map-fusion law (provable by induction on
  the list); output element-for-element identical. **Consumer
  applicability (TS-React):** TS-translatable directly. Frequent
  in selector/derive code:
  `state.boxes.map(toViewModel).map(applyTint)` ⇒
  `state.boxes.map(box => applyTint(toViewModel(box)))`. One
  fewer array allocation per pipeline; observable behavior
  preserved. Encoded as the executable ast-grep rule
  `aspergillus/typescript/ast-grep-rules/map-fusion.yml`.

- **filter-fusion** (Bird + de Moor 1997 §2.6). **HIGH-LEVERAGE
  for FP consumers.** Trigger: two consecutive `filter` calls
  with predicates `p`, `q`. Move: replace with one `filter`
  whose predicate is the conjunction. Rewrite:

  ```
  filter p . filter q  ≡  filter (\x -> p x && q x)
  xs.filter(q).filter(p)  ⇒  xs.filter(x => q(x) && p(x))
  ```

  Guarantee: by the filter-fusion law; the survivors of `q`
  that also pass `p` are exactly the survivors of the
  conjunction. **Consumer applicability (TS-React):**
  TS-translatable directly. Same allocation-reduction story as
  map-fusion. Frequent in inventory and list-filtering code.
  Encoded as the executable ast-grep rule
  `aspergillus/typescript/ast-grep-rules/filter-fusion.yml`.

- **fold-fusion / Banana Split** (Bird + de Moor 1997 §3.4
  "Banana split"; recursion-scheme algebra in Meijer, Fokkinga,
  Paterson, "Functional Programming with Bananas, Lenses,
  Envelopes and Barbed Wire," FPCA 1991 — primary source).
  Trigger: two folds over the same structure producing two
  results (sum + length, min + max, etc.). Move: combine into
  one fold producing a tuple. Rewrite:

  ```
  (foldr f a xs, foldr g b xs)
  ≡  foldr (\x (acc1, acc2) -> (f x acc1, g x acc2)) (a, b) xs
  ```

  Guarantee: by the banana-split theorem; each component of the
  tuple equals the corresponding individual fold. **Consumer
  applicability (TS-React):** Requires adaptation. JS
  `Array.prototype.reduce` is the analogue, but `.reduce` is
  rare in `.map`/`.filter`-dominated code. Apply only when an
  explicit two-pass `reduce` pair appears in a hot path; often
  the better prerequisite move is `Replace Loop with Pipeline`
  first.

- **Recognise as Catamorphism / Anamorphism / Hylomorphism**
  (Meijer, Fokkinga, Paterson, "Bananas, Lenses, Envelopes and
  Barbed Wire," FPCA 1991 — primary source for the named
  schemes; Bird + de Moor 1997 ch. 6 for the algebraic
  treatment). Trigger: ad-hoc recursion over a data structure
  that matches a standard scheme — consume (catamorphism),
  produce (anamorphism), or transform via a never-materialized
  intermediate (hylomorphism). Move: rewrite the explicit
  recursion using the named scheme. Rewrite shapes:

  ```
  catamorphism (consume):   recurse over list  ⇒  foldr f z xs
  anamorphism (produce):    generate list      ⇒  unfoldr f seed
  hylomorphism (consume∘produce):  the intermediate is fused away
  ```

  Guarantee: each scheme has a uniqueness theorem fixing the
  recursive structure; rewriting preserves the recursion's
  fixpoint by construction. **Consumer applicability (TS-React):**
  Requires adaptation. TS lacks `unfoldr` in the standard library
  and hand-written recursion is a smell under
  `eslint-plugin-functional`; the catalog's `Replace Imperative
  Loop with Higher-Order Function` already covers the consume
  direction. The named scheme is useful at code-review time —
  when reviewing hand-written recursion, ask "is this a cata/
  ana/hylo?" before accepting it.

#### Bird Pearls 2010 (traversal-shape moves)

- **Tupling** (Bird, *Pearls of Functional Algorithm Design*,
  Cambridge University Press 2010, Pearl 9 "Finding celebrities"
  and Pearl 11 "Not the maximum segment sum"; technique
  introduced in Bird, "Tabulation Techniques for Recursive
  Programs," ACM Comput. Surv. 1980). **HIGH-LEVERAGE for FP
  consumers.** Trigger: two functions traverse the same
  structure to compute two results; called together by a third
  function. Move: collapse to one traversal returning a tuple
  (or object). Rewrite:

  ```
  (f xs, g xs)                              -- two traversals
  ⇒  let (a, b) = h xs in (a, b)
     where h xs = traverse-once-returning-pair xs
  ```

  Guarantee: by the tupling lemma; the tuple's components equal
  the individual functions' outputs. **Consumer applicability
  (TS-React):** TS-translatable directly. Direct match for
  React selector-recompute idioms: two `useMemo` selectors over
  the same state slice ⇒ one selector returning a tuple/object.
  Reduces re-computation and re-render churn. Apply in `hooks/`
  and `core/selectors/` when profiling shows redundant selector
  evaluation across closely-related slices.

- **Accumulating Parameter** (Wand, "Continuation-Based Program
  Transformation Strategies," J. ACM 1980 — primary source;
  applied technique in Bird *Pearls* 2010 Pearl 1 "The smallest
  free number" and Pearl 7 "Building a tree with minimum
  height"). Trigger: a naive recursion does work after the
  recursive call (`f (x:xs) = combine x (f xs)`); causes stack
  pressure on long lists, or repeats work via `++`/concat-in-
  loop. Move: introduce an accumulator parameter that carries
  the result-so-far; resulting recursion is tail-recursive.
  Rewrite:

  ```
  naive:    reverse []     = []
            reverse (x:xs) = reverse xs ++ [x]      -- O(n²)
  accum:    reverse xs = go xs []
              where go []     acc = acc
                    go (x:xs) acc = go xs (x:acc)   -- O(n)
  ```

  Guarantee: by induction; the accumulator is empty initially
  and threaded through every recursive step, so the final value
  equals the naive recursion's. **Consumer applicability
  (TS-React):** TS-translatable directly. Foundational for
  difference-list / `ShowS`-style string builders. JS engines
  don't reliably TCO, so the stack-depth benefit is partial —
  but the algorithmic improvement (O(n²) → O(n) from avoiding
  repeated `++`/concat) is real. Useful in chat-history
  rendering and any O(n²) string-build hot paths.

#### Wadler 1989 (free theorems)

- **Naturality-Driven Rewrite** (Wadler, "Theorems for Free!"
  FPCA 1989 — primary source). Trigger: a polymorphic function
  with type `f :: forall a. F a -> G a`. The free theorem of
  `f`'s type guarantees `map_G h . f = f . map_F h` — applying
  a transformation on elements commutes with `f`. Move: push or
  pull transformations through `f` without reasoning about
  `f`'s body. Rewrite (example for `reverse :: forall a. [a] -> [a]`):

  ```
  ∀ g, f :: [a] -> [a] polymorphic.   map g . f = f . map g
  xs.reverse().map(g)  ≡  xs.map(g).reverse()
  ```

  Guarantee: by parametricity (the operator must treat values
  of `a` opaquely). **Consumer applicability (TS-React):**
  Requires adaptation. TS lacks Haskell's parametric-polymorphism
  guarantees — a TS function typed `<T>(xs: T[]) => T[]` can
  still inspect runtime tags (`instanceof`, prototype shape)
  and break naturality. Reserve for the `Result<T, E>` corner
  of `neverthrow` and standard `Array` operations where
  parametricity is genuine. Most useful at code-review time as
  a rewrite-justification ("this swap is sound by the free
  theorem of `f`") rather than as a routine refactor.

#### Gill + Hutton 2009 (representation moves)

- **Worker / Wrapper** (Gill + Hutton, "The Worker/Wrapper
  Transformation," J. Funct. Program. 19(2), 2009 — primary
  source with the factorization theorem). **HIGH-LEVERAGE for
  FP consumers.** Trigger: a function operates on a
  representation that's clear-but-slow; a faster representation
  exists, but changing the public type would break callers.
  Move: introduce an inner `worker` over the efficient
  representation; keep the outer `wrapper` over the clear
  representation; the wrapper converts in, the worker computes,
  the wrapper converts out. Rewrite:

  ```
  slow:    f :: A -> A           -- clear but slow
  ⇒        work :: B -> B        -- efficient inner
           wrap :: A -> A        -- thin outer
           wrap = unrep . work . rep
           where  rep   :: A -> B
                  unrep :: B -> A
                  unrep . rep = id      -- correctness condition
  ```

  Guarantee: by the worker/wrapper factorization theorem
  (Gill + Hutton 2009 §3); `wrap` is observationally equal to
  `f` provided `unrep . rep = id`. **Consumer applicability
  (TS-React):** TS-translatable directly. The shape
  `newtype`-deriving and `deriving via` exploit in Haskell; in
  TS the analogue is "introduce an internal-only optimized
  representation behind a public type-alias / class boundary."
  Use when profiling identifies a hot data path (e.g., a
  reducer doing repeated linear scans over an array that could
  be a `Map` internally without changing the public state
  shape). **Distinct from `Push Effects to the Edge`:** Push
  Effects isolates side-effects; Worker/Wrapper isolates
  representation. Both factor a function, but along different
  axes.

#### HLint corpus (Mitchell, declarative source rewrites)

The HLint corpus (Mitchell, *HLint*) is ~700 machine-checked
declarative rewrites. Most are language-hygiene (redundant
parens, trailing whitespace, etc.) and belong in lint config,
not the refactoring catalog. The catalog cut is Fowler's
("preserves observable behavior" + "makes the code easier for
a senior engineer to reason about cold"). The high-leverage
subset that meets the cut:

- **Eta-Reduction / Eta-Expansion** (HLint hints `Eta reduce`,
  `Avoid lambda`; theory: η-conversion from the untyped λ-
  calculus, Church, *The Calculi of Lambda-Conversion*, 1941).
  **HIGH-LEVERAGE for FP consumers.** Trigger (reduce): a
  lambda's body is exactly a function applied to the lambda's
  argument(s) with nothing else. Trigger (expand): point-free
  code obscures which argument is which (Wadler 1989's
  eta-expansion direction). Move: drop or introduce the lambda.
  Rewrite:

  ```
  reduce:  \x -> f x          ⇒  f
           xs.map(x => f(x))   ⇒  xs.map(f)
  expand:  f                   ⇒  \x -> f x   -- to name the argument
  ```

  Guarantee: by η-equivalence (`f` and `\x -> f x` are
  observationally indistinguishable in a pure functional
  setting). **Consumer applicability (TS-React):** TS-translatable
  directly. HLint flags this constantly; the equivalent in
  TypeScript is `xs.map(x => f(x))` ⇒ `xs.map(f)`. Mechanical,
  safe, frequent. Encoded as the executable ast-grep rule
  `aspergillus/typescript/ast-grep-rules/eta-reduce-arrow.yml`.
  **Conservativeness:** in TS, `this`-binding and `arguments`
  make eta-reduction over methods unsafe — the ast-grep rule
  excludes those cases via a `constraints.F.kind: identifier`
  filter (member-expression callees do not match).

- **Boolean-Conditional Collapse** (HLint hints `Use ||`,
  `Use &&`, `Use not`; theory: `if`-`then`-`else` over `Bool`
  is definable as `||`/`&&`). Trigger: an `if` expression
  returns a literal `True` or `False` in one branch. Move:
  collapse to a boolean operator. Rewrite:

  ```
  if x then True  else y    ⇒   x || y
  if x then y     else False ⇒   x && y
  if x then False else y    ⇒   not x && y
  if x then y     else True  ⇒   not x || y
  ```

  Guarantee: by the truth table; the resulting expression has
  the same value on every input. **Consumer applicability
  (TS-React):** TS-translatable directly (`x ? true : y` ⇒
  `x || y`). Mechanical. Catches verbose ternaries common in
  component render-condition expressions and selector return
  shapes. Encoded as the executable ast-grep rules
  `aspergillus/typescript/ast-grep-rules/redundant-ternary-bool-true.yml`
  and
  `aspergillus/typescript/ast-grep-rules/redundant-ternary-bool-false.yml`.

- **`concatMap` for `concat . map`** (HLint hint `Use concatMap`;
  theory: definitional unfold of `concatMap`). Trigger: a
  `map` followed by `concat`, i.e., a `flatMap` written in two
  steps. Move: replace with `concatMap` / `flatMap`. Rewrite:

  ```
  concat . map f xs     ≡   concatMap f xs
  xs.map(f).flat()      ⇒   xs.flatMap(f)
  ```

  Guarantee: by the definition of `concatMap`; the outputs are
  element-wise equal. **Consumer applicability (TS-React):**
  TS-translatable directly. JS `Array.prototype.flatMap` is
  exactly this; the HLint rule lifts verbatim. One allocation
  fewer; semantically identical. Generalization of `map-fusion`
  for the "one-input, N-output" direction.

- **`foldr` / `build` Fusion (Shortcut Deforestation)** (Gill,
  Launchbury, Peyton Jones, "A Short Cut to Deforestation,"
  FPCA 1993 — primary source; surfaces indirectly in HLint via
  suggestions toward `foldr`-shape). Trigger: a producer
  constructs an intermediate list that is immediately consumed
  by a fold. Move: rewrite the producer as `build (\c n -> ...)`,
  consumer as `foldr c n`; fuse by GHC `RULES`. Rewrite:

  ```
  foldr c n (build g)   ⇒  g c n              -- the fusion rule
  foldr c n (map f xs)  ⇒  foldr (\x -> c (f x)) n xs   -- fused
  ```

  Guarantee: by the `foldr/build` rewrite rule (Gill et al.
  1993, Theorem 2); the intermediate list is provably never
  observed. **Consumer applicability (TS-React):** Not
  applicable as a mechanical rewrite — TS has no GHC `RULES`
  equivalent and V8/Hermes do not deforest intermediate arrays.
  The principle (avoid materializing intermediates in hot paths)
  is real and motivates targeted reversals of `Replace Loop
  with Pipeline` when profiling shows allocation pressure —
  collapse the pipeline back into one `reduce` or one explicit
  loop. Cite the principle when justifying such a reversal;
  do not attempt the literal Haskell rewrite.

- **Redundant `return await`** (HLint hint `Use return`; theory:
  `return $ await x` is observationally equal to `return x`
  outside try/catch context because an async function awaits
  its returned promise before resolving its own). Trigger:
  `return await $X` in an async function. Move: drop the
  `await`. Rewrite:

  ```
  return await x   ⇒  return x   -- outside try blocks
  ```

  Guarantee: by the async/await semantics — the awaiter of the
  async function's promise sees the same resolved value either
  way; stack-trace shape is preserved because the automatic
  await on the returned promise preserves the original
  promise's rejection frame. **Consumer applicability (TS):**
  TS-translatable directly. **Conservativeness:** inside a
  `try` block, `return await` is load-bearing — the `await`
  forces the promise to reject inside the local catch frame,
  whereas `return` (no await) lets the unawaited promise
  reject in the caller's frame, bypassing the local catch.
  Encoded as the executable ast-grep rule
  `aspergillus/typescript/ast-grep-rules/redundant-await-return.yml`
  with a `not.inside: try_statement` ancestor filter so the
  autofix only fires outside try-blocks.

- **Named-Conversion Rewrites** (HLint hints `Use <$>`, `Use
  fmap`, `Use section`, point-free conversions; theory:
  standard typeclass-method and operator-section identities).
  Trigger: applying a known identity makes intent clearer.
  Selected TS-relevant analogues:
  - `fmap f x` ⇒ `f <$> x` — Not applicable in TS (no
    `Functor` typeclass; JS `Array#map` is already the named
    form).
  - Point-free conversion (`\x -> f (g x)` ⇒ `f . g`) — Partial
    applicability via `pipe` / `flow` (`fp-ts`, `effect`).
    Avoid when it obscures argument identity (Wadler 1989's
    eta-expansion direction).
  - Section introduction (`\x -> x + 1` ⇒ `(+ 1)`) — Not
    directly translatable; the equivalent TS form
    `(x: number) => x + 1` is already the clearest shape and
    short-circuiting to `Array#some` etc. is JS's native idiom.

  **Consumer applicability (TS-React):** Mostly not applicable.
  The category exists in this catalog to mark that the HLint
  corpus has been surveyed and most of its named-conversion
  hints don't translate to TS. Cite the principle ("name the
  standard operation") rather than the literal rewrite.

#### Hygiene-only HLint hints (NOT in the catalog)

For completeness, the HLint hints excluded by the catalog cut:

- Redundant parens (`(x)` ⇒ `x` where unambiguous) — pure
  cosmetic; belongs in lint config.
- Redundant `$` (`f $ x` ⇒ `f x` when no precedence concern) —
  pure cosmetic; lint config.
- Redundant `do` blocks, semicolons, etc. — Haskell-specific
  cosmetic; not applicable.

The cut: does the rewrite help a senior engineer reason about
the code cold? Whitespace-/parens-only changes don't; they
belong in `prettier` / lint config, not this catalog.

### Make implicit explicit

- **Combine Functions into Class** (Fowler ch. 6) / **Combine
  Functions into Transform** (Fowler ch. 6). Trigger: a group of
  functions share input data and could be expressed as
  transformations of a value. Guarantee: each function call
  produces the same output via the transform.
- **Remove Setting Method** (Fowler ch. 11). Trigger: a setter
  enables mutation that violates an immutability invariant.
  Guarantee: the field is set only via construction; clients can't
  mutate.
- **Replace Derived Variable with Query** (Fowler ch. 9). Trigger:
  a field caches a value that could be recomputed cheaply.
  Guarantee: the query returns the same value the cache would have
  held.

### Renaming / clarity (no behavior change)

- **Rename Function / Variable / Field** (Fowler ch. 6). Trigger:
  name doesn't reflect behavior. Guarantee: every reference updated.

### Removal

- **Remove Dead Code** (Fowler ch. 8). Trigger: code is unreachable
  or unused. Guarantee: no caller observes the removal.
- **Remove Flag Argument** (see Refactoring APIs).
- **Remove Middle Man** (see Encapsulation).

## Composition rules

From Fowler's "Lots of Little Steps" principle (Fowler ch. 1
§"Why Should I Refactor?"):

1. **Apply one move at a time.** After each move, run tests. The
   move is valid only if tests stay green.
2. **Extract first, then inline.** If you're not sure whether
   extracting a function helps, extract it (cheap to reverse).
   Then if it's not useful after some time, inline it. The
   reverse — inline first, then re-extract — burns the previously-
   extracted structure that may have been load-bearing.
3. **Rename before consolidating.** Names reveal duplication. Two
   functions named `processFoo` and `processBar` may turn out to
   be the same operation after renaming reveals their similarity.
4. **Move data before moving the code that uses it.** Otherwise
   the code accumulates long-distance references that obscure the
   data's owner.
5. **Polymorphism (tagged unions in FP) before parameterization.**
   Exhaustiveness checks at the type level catch missed cases
   before they reach runtime.

## Anti-moves

Refactor-shaped operations that are NOT in the catalog:

- **Premature abstraction by speculation.** "We might need N
  variants of this later; let's parameterize now." Fowler
  explicitly cautions against this (ch. 3 "Bad Smells in Code" §
  "Speculative Generality"). The correct move is: build for the
  current N; refactor when N increases.
- **Introducing a framework where a function would do.**
  Consumer-side ADRs may reject specific frameworks (XState /
  Redux / actor frameworks, etc.) for specific reasons;
  introducing a third-party framework to "save" boilerplate that
  a small helper would handle is an anti-move regardless of the
  specific rejection.
- **Inlining too early.** Reversal cost is high; the inline burns
  structure that was load-bearing.
- **Changing behavior while refactoring.** Refactor and behavior-
  change are two separate concerns; mixing them makes the test
  evidence ambiguous (did the behavior change break a test, or
  was the refactor wrong?). Apply behavior changes as their own
  commits, separately from refactors.
- **"Senior FP analysis" without code-read.** Producing output
  that looks like senior engineering (vocabulary, framing,
  calibrated numbers) while the underlying process is pattern-
  match against training data is the failure mode the
  discipline-of-refactoring ADRs in consuming repos catch.

## Consumer policy: extending this catalog

Consumers (repos that subtree aspergillus) keep their own
project-specific applicability notes in a slim `docs/refactoring-
catalog.md` adjacent to their own ADRs. The slim file:

- Lists which moves from this corpus are highest-leverage given
  the consumer's current codebase shape (e.g., a state-machine-
  heavy React-FP codebase will flag `Replace Switch with Data
  Table` and `Parameterize Over Data`; a Python pandas pipeline
  may flag different moves).
- Cites where consumer-specific encodings of the corpus live
  (e.g., the consumer's ast-grep rules, the consumer's ESLint
  custom-rule packages).
- Cross-references consumer ADRs that justify why specific
  catalog moves are or aren't relevant in that codebase.

This file does NOT track consumer-specific encodings or
applicability flags; it's the catalog corpus, period. Consumer
files cite this file by its subtree-relative path and add their
own narrative on top.
