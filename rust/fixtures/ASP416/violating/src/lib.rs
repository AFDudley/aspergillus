// ASP416: a validation function that reduces raw input to a yes/no instead
// of parsing it into a narrowed type. Parse, don't validate (Alexis King,
// 2019): return the stronger type the check proves, so a caller cannot use
// the raw input without first passing through the parse.

pub fn is_valid_email(raw: &str) -> bool {
    raw.contains('@') && raw.contains('.')
}
