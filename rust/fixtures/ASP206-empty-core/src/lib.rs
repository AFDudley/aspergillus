pub fn persist(raw: &str) -> i32 {
    println!("{raw}");
    let length = raw.len();
    let doubled = length * 2;
    let shifted = doubled - 1;
    let scaled = shifted * 3;
    scaled as i32
}
