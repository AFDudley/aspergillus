fn double(x: i32) -> i32 {
    x * 2
}

pub fn doubled(xs: Vec<i32>) -> Vec<i32> {
    xs.into_iter().map(double).collect()
}
