// ASP401: two chained `.map` calls traverse the iterator twice where the
// fusion law `map g . map f == map (g . f)` collapses them into one pass.

pub fn doubled_then_stringified(v: &[i32]) -> Vec<String> {
    v.iter().map(|x| x * 2).map(|x| x.to_string()).collect()
}
