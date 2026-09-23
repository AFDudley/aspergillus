// Two functions that each do real, multi-statement work but share no run of
// statements: different accumulator shapes, different called functions, and
// different control flow. Neither the whole-body hash nor the statement-spine
// sliding window finds a match, so ASP501 stays silent.

pub fn render_widths(items: &[Widget]) -> u32 {
    let mut total = 0;
    for item in items {
        total += item.width;
    }
    total
}

pub fn join_labels(rows: &[Row]) -> String {
    let mut out = String::new();
    for row in rows {
        out.push_str(&row.label);
        out.push('\n');
    }
    out.trim_end().to_string()
}

pub struct Widget {
    pub width: u32,
}

pub struct Row {
    pub label: String,
}
