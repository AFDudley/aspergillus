// ASP401 satisfied: the two transforms are composed into a single `.map`
// pass, so the iterator is traversed once.

pub fn doubled_then_stringified(v: &[i32]) -> Vec<String> {
    v.iter().map(|x| (x * 2).to_string()).collect()
}
