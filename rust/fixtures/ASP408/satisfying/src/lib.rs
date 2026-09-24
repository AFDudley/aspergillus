// No special-casing: the literal-keyed branch COMPUTES its result, the
// `match` is a legitimate dispatch table, and the only env read is a
// non-test configuration key.

pub fn route(status: &str) -> String {
    if status == "active" {
        return build_profile(status);
    }
    default_profile()
}

fn build_profile(status: &str) -> String {
    status.to_string()
}

fn default_profile() -> String {
    String::new()
}

pub fn status_name(code: u32) -> &'static str {
    match code {
        404 => "Not Found",
        500 => "Server Error",
        _ => "Unknown",
    }
}

pub fn database_url() -> Result<String, std::env::VarError> {
    std::env::var("DATABASE_URL")
}
