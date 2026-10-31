// `static mut` declares global mutable state: any code path may mutate it,
// and reads and writes race without a lock. ASP203 fires on the declaration.

pub static mut COUNTER: u32 = 0;

pub fn bump() {
    // SAFETY: single-threaded demo; still a global-mutable-state defect.
    unsafe {
        COUNTER += 1;
    }
}
