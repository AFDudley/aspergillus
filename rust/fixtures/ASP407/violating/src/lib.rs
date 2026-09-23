// ASP407: a free function whose whole body forwards every parameter,
// verbatim and in order, to a differently-named callee. Either grow the
// Worker/Wrapper rep/unrep logic or inline the wrapper.

pub fn add(x: i32, y: i32) -> i32 {
    combine(x, y)
}

fn combine(a: i32, b: i32) -> i32 {
    a + b
}
