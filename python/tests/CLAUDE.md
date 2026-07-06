# aspergillus/python/tests/

pytest over the Python (fixit/LibCST) rule corpus. Testing mechanics + the
taxonomy these tests obey: [`../../docs/testing.md`](../../docs/testing.md).

The "e2e" of a rule is the rule firing on real fixture code (RED on a violating
fixture, GREEN on a clean one); `test_anti_special_casing.py` is the honesty
check that a rule generalizes rather than hardcoding one fixture input. Per
[`../../docs/testing.md`](../../docs/testing.md) § "Testing policy": done = the rule
discriminates real violating vs clean code, not that its helpers pass.
