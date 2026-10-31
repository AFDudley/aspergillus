// ASP406: two aggregation chains rooted at the same receiver `xs` traverse
// it twice. Bird's Tupling collapses them into one pass returning a tuple.

pub fn mean(xs: &[f64]) -> f64 {
    let total: f64 = xs.iter().sum();
    let count = xs.iter().count();
    total / count as f64
}
