// ASP416 satisfied: this is a parse boundary — it takes the same raw `&str`
// input the violating `is_valid_email` reduces to a `bool`, but on success it
// returns a narrowed `Email`, so the proof that the check ran is recorded in
// the type rather than discarded into a yes/no a caller can ignore.

pub struct Email(String);

pub fn parse_email(raw: &str) -> Result<Email, String> {
    if raw.contains('@') && raw.contains('.') {
        Ok(Email(raw.to_string()))
    } else {
        Err(String::from("not an email"))
    }
}
