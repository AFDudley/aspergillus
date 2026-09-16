# aspergillus/python/tests/oracle_scripts/

Behavioral acceptance-oracle entrypoints for asp-d88.2's derived spec
(`contracts/specs/derived-asp-d88.2.spec.json`). Each `check_*.py` is a
standalone script the exophial reducer runs directly
(`python3 check_x.py <fixture_dir>`) against the fixtures under
`../fixtures/asp_*`. A script only emits one `stdout_json` observation — it
judges nothing; the derived spec's `then` predicates own every verdict.
`_scan.py` holds the one bit of repeated plumbing (reading a fixture
directory's `.py` files into `FunctionRecord`s and locating a match by
function name) so no script re-describes it.
