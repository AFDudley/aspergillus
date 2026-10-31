// ASP402 satisfied: the two predicates are fused into a single `.filter`
// pass over the iterator.

pub fn positive_evens(v: &[i32]) -> Vec<i32> {
    v.iter()
        .filter(|x| **x > 0 && **x % 2 == 0)
        .copied()
        .collect()
}
