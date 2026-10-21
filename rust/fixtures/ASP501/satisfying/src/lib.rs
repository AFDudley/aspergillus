// Every function here does real, multi-statement work, yet ASP501 stays
// silent. Three independent reasons cover the three pairs below, and together
// they pin the spine pass's precision (pebble asp-7ac):
//
//   * `render_widths` / `join_labels` share no run of statements at all -
//     different accumulators, callees, and control flow.
//   * `InstructionTable::push` / `LookupTable::push` are PARALLEL TYPED
//     VARIANTS: identical but for the count newtype each constructs. Their
//     four-statement common spine is not a clone one helper could hoist
//     without erasing that newtype, so it is not reported.
//   * `stats` / `median` share only the guard/copy/sort PREAMBLE IDIOM
//     (`if empty return; sorted copy; sort`), a convention two unrelated
//     statistics routines both open with, not a copied block.

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

pub struct InstructionTable {
    count: InstructionCount,
    spans: [InstructionSpan; 64],
}

impl InstructionTable {
    pub fn push(&mut self, span: InstructionSpan) -> Result<(), Refusal> {
        let at = usize::from(self.count.get());
        let slot = self.spans.get_mut(at).ok_or(Refusal::CapacityExceeded)?;
        *slot = span;
        let next = self
            .count
            .get()
            .checked_add(1)
            .ok_or(Refusal::CapacityExceeded)?;
        self.count = InstructionCount::new(next);
        Ok(())
    }
}

pub struct LookupTable {
    count: LookupCount,
    spans: [LookupSpan; 64],
}

impl LookupTable {
    pub fn push(&mut self, span: LookupSpan) -> Result<(), Refusal> {
        let at = usize::from(self.count.get());
        let slot = self.spans.get_mut(at).ok_or(Refusal::CapacityExceeded)?;
        *slot = span;
        let next = self
            .count
            .get()
            .checked_add(1)
            .ok_or(Refusal::CapacityExceeded)?;
        self.count = LookupCount::new(next);
        Ok(())
    }
}

pub fn stats(latencies: &[f64]) -> Option<Summary> {
    if latencies.is_empty() {
        return None;
    }
    let mut sorted = latencies.to_vec();
    sorted.sort_by(f64::total_cmp);
    Some(Summary {
        count: sorted.len(),
        min: *sorted.first()?,
        max: *sorted.last()?,
    })
}

pub fn median(returns: &[f64]) -> Option<f64> {
    if returns.is_empty() {
        return None;
    }
    let mut sorted = returns.to_vec();
    sorted.sort_by(f64::total_cmp);
    let n = sorted.len();
    let mid = n / 2;
    if n % 2 == 1 {
        return sorted.get(mid).copied();
    }
    let lower = mid.checked_sub(1)?;
    Some((sorted.get(lower)?.max(*sorted.get(mid)?)) / 2.0)
}

pub struct Widget {
    pub width: u32,
}

pub struct Row {
    pub label: String,
}

pub struct Summary {
    pub count: usize,
    pub min: f64,
    pub max: f64,
}

pub struct InstructionSpan;
pub struct LookupSpan;

pub enum Refusal {
    CapacityExceeded,
}

#[derive(Clone, Copy)]
pub struct InstructionCount(u16);

impl InstructionCount {
    pub fn new(value: u16) -> Self {
        Self(value)
    }
    pub fn get(self) -> u16 {
        self.0
    }
}

#[derive(Clone, Copy)]
pub struct LookupCount(u16);

impl LookupCount {
    pub fn new(value: u16) -> Self {
        Self(value)
    }
    pub fn get(self) -> u16 {
        self.0
    }
}
