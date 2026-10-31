pub fn summarize(raw: &str) -> i32 {
    let scaled = pure_scale(raw);
    println!("{scaled}");
    scaled
}

fn pure_scale(raw: &str) -> i32 {
    let length = raw.len();
    let doubled = length * 2;
    let shifted = doubled - 1;
    let scaled = shifted * 3;
    scaled as i32
}
