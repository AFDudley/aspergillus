// ASP402: two chained `.filter` calls traverse the iterator twice where a
// single predicate `p(x) && q(x)` does it in one pass.

pub fn positive_evens(v: &[i32]) -> Vec<i32> {
    v.iter()
        .filter(|x| **x > 0)
        .filter(|x| **x % 2 == 0)
        .copied()
        .collect()
}
