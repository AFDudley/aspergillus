// Two functions whose whole bodies differ - a distinct first statement and a
// distinct trailing statement each - but which share an identical run of SIX
// consecutive statements in the middle (the load-scale-and-fold block). A
// whole-body clone hash cannot see this copied spine, because the surrounding
// code makes the whole-body hashes differ; the statement-spine sliding window
// does. The run is a genuinely copied block, not a parallel typed variant
// (the two functions diverge in their real callees, not merely a type path)
// and not the guard/copy/sort preamble idiom, so both precision gates leave
// it alone and ASP501 fires at each copy's window start (pebble asp-7ac).

pub fn ingest(rows: &[Row]) -> Report {
    let head = first_marker();
    let mut acc = 0u64;
    let scale = load_scale();
    let width = rows.len() as u64;
    let total = acc + width;
    let scaled = total * scale;
    let adjusted = scaled + head;
    acc = adjusted;
    Report::new(acc)
}

pub fn summarize(cells: &[Cell]) -> Summary {
    let extra = other_source();
    let mut acc = 0u64;
    let scale = load_scale();
    let width = cells.len() as u64;
    let total = acc + width;
    let scaled = total * scale;
    let adjusted = scaled + extra;
    acc = adjusted;
    finalize(acc, extra)
}

fn first_marker() -> u64 {
    3
}

fn other_source() -> u64 {
    9
}

fn load_scale() -> u64 {
    2
}

fn finalize(total: u64, extra: u64) -> u64 {
    total + extra
}

pub struct Row {
    pub width: u64,
}

pub struct Cell {
    pub weight: u64,
}

pub struct Report {
    pub value: u64,
}

impl Report {
    pub fn new(value: u64) -> Self {
        Self { value }
    }
}

pub struct Summary {
    pub value: u64,
}
