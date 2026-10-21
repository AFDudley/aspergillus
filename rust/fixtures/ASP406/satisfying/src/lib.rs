// ASP406 satisfied: a single pass over `xs` accumulates both the sum and
// the count, so the iterable is traversed once.

pub fn mean(xs: &[f64]) -> f64 {
    let (total, count) = xs
        .iter()
        .fold((0.0_f64, 0_usize), |(sum, n), x| (sum + x, n + 1));
    total / count as f64
}
