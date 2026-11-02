use crate::fss::Frame;

const SEARCH_FROM: f64 = 0.5;
const SEARCH_TO: f64 = 0.97;
const OFF_CENTRE: f64 = 0.05;
const MIN_RULE: f64 = 0.25;
const RUN_GAP: f64 = 0.01;
const RULE_APART: f64 = 0.006;
const LINE_FROM: f64 = 0.08;
const LINE_TO: f64 = 0.025;
const LINE_REFERENCE: f64 = 0.012;
const LINE_LIFT: i32 = 30;
const MIN_LINE: f64 = 0.6;
const LINE_SHARE: f64 = 0.8;
const LINE_THICK: f64 = 0.004;
const END_CAP: f64 = 0.014;
const REACH: f64 = 0.026;
const BACKDROP_FROM: f64 = 0.06;
const BACKDROP_TO: f64 = 0.035;
const BACKDROP_SHARE: f64 = 0.5;
const LINE_COLOUR: f64 = 0.6;
const STROKE_GAP: f64 = 0.006;
const ACROSS: f64 = 0.5;
const MIN_AMPLITUDE: f64 = 0.006;
const MERGE_GAP: f64 = 0.009;
const MIN_WIDTH: f64 = 0.006;
const TALL_SPIKE: f64 = 0.010;
const PAST_FROM: f64 = 0.004;
const PAST_TO: f64 = 0.012;
const ICON_FROM: f64 = 0.008;
const ICON_TO: f64 = 0.035;
const ICON_GAP: f64 = 0.003;
const ICON_MIN: f64 = 0.007;
const ICON_MAX: f64 = 0.022;
const ICON_PIXELS: f64 = 0.04;
const ICON_ROW: f64 = 0.021;
const ICON_ROW_SLACK: f64 = 0.004;
const HALO_FROM: f64 = 0.0075;
const HALO_TO: f64 = 0.0105;
const OUTSIDE_FROM: f64 = 0.012;
const OUTSIDE_TO: f64 = 0.014;
const HALO_STEP: f64 = 20.0;
const HALO_SAMPLES: usize = 72;
const NEEDLE_COLUMN: f64 = 0.9;
const BRIGHT: u8 = 150;
const CHROMA: u8 = 100;
const WHITE: u8 = 170;
const GLYPH_BRIGHT: i32 = 200;
const DISC_OPEN: f64 = 0.001;
pub const SLOT: f64 = 0.00506;
pub const SLOT_ZERO: f64 = 0.00037;
const TIP: f64 = 0.012;

pub fn slot_at(slot: usize) -> f64 {
    SLOT_ZERO + slot as f64 * SLOT
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Bar {
    pub top: usize,
    pub bottom: usize,
    pub left: usize,
    pub right: usize,
}

impl Bar {
    fn length(&self) -> f64 {
        (self.right - self.left) as f64
    }

    pub fn px(&self, share: f64) -> usize {
        (share * self.length()).round() as usize
    }

    fn along(&self, x: f64) -> f64 {
        (x - self.left as f64) / self.length()
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Spike {
    pub at: f64,
    pub width: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Icon {
    pub at: f64,
    pub x: usize,
    pub y: usize,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Tip {
    pub at: f64,
    pub slot: usize,
    pub up: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Reading {
    pub bar: Bar,
    pub spikes: Vec<Spike>,
    pub tips: Vec<Tip>,
    pub icons: Vec<Icon>,
}

impl Reading {
    pub fn slots(&self) -> Vec<usize> {
        let mut lit: Vec<usize> = self.tips.iter().map(|t| t.slot).collect();
        lit.sort_unstable();
        lit.dedup();
        lit
    }
}

fn pixel(f: &Frame, x: usize, y: usize) -> [i32; 3] {
    let i = (y * f.width + x) * 3;
    [f.rgb[i] as i32, f.rgb[i + 1] as i32, f.rgb[i + 2] as i32]
}

fn chroma(p: [i32; 3]) -> i32 {
    p.iter().max().unwrap_or(&0) - p.iter().min().unwrap_or(&0)
}

fn ruled(f: &Frame, x: usize, y: usize, apart: usize) -> bool {
    if y < apart || y + apart >= f.height || !strong(f, x, y) {
        return false;
    }
    let around = chroma(pixel(f, x, y - apart)).max(chroma(pixel(f, x, y + apart)));
    chroma(pixel(f, x, y)) - around >= LINE_LIFT || !strong(f, x, y - apart) && !strong(f, x, y + apart)
}

fn strong(f: &Frame, x: usize, y: usize) -> bool {
    let p = pixel(f, x, y);
    p.iter().max().is_some_and(|&hi| hi > BRIGHT as i32) && chroma(p) > CHROMA as i32
}

fn white(f: &Frame, x: usize, y: usize) -> bool {
    pixel(f, x, y).iter().all(|&c| c > WHITE as i32)
}

fn distance(a: [i32; 3], b: [i32; 3]) -> i32 {
    (0..3).map(|i| (a[i] - b[i]).abs()).sum()
}

fn median(mut values: Vec<[i32; 3]>) -> [i32; 3] {
    let mut out = [0; 3];
    for (c, slot) in out.iter_mut().enumerate() {
        values.sort_by_key(|p| p[c]);
        *slot = values.get(values.len() / 2).map_or(0, |p| p[c]);
    }
    out
}

fn longest_run(f: &Frame, y: usize, gap: usize) -> (usize, usize) {
    let mut best = (0, 0);
    let mut run: Option<(usize, usize)> = None;
    let apart = (RULE_APART * f.height as f64).round() as usize;
    for x in (0..f.width).filter(|&x| ruled(f, x, y, apart)) {
        run = match run {
            Some((start, end)) if x - end <= gap => Some((start, x)),
            _ => Some((x, x)),
        };
        if let Some((start, end)) = run
            && end - start > best.1 - best.0
        {
            best = (start, end);
        }
    }
    best
}

fn rules(f: &Frame) -> Vec<(usize, usize, usize)> {
    let h = f.height as f64;
    let gap = (RUN_GAP * h).round() as usize;
    let centre = f.width as f64 / 2.0;
    let mut found: Vec<(usize, usize, usize)> = Vec::new();
    let mut last_row = None;
    for y in (SEARCH_FROM * h) as usize..((SEARCH_TO * h) as usize).min(f.height) {
        let (l, r) = longest_run(f, y, gap);
        if r - l < (MIN_RULE * h) as usize || ((l + r) as f64 / 2.0 - centre).abs() > OFF_CENTRE * f.width as f64 {
            continue;
        }
        match found.last_mut() {
            Some(rule) if last_row == Some(y - 1) => {
                rule.1 = rule.1.min(l);
                rule.2 = rule.2.max(r);
            }
            _ => found.push((y, l, r)),
        }
        last_row = Some(y);
    }
    found
}

fn line_strength(f: &Frame, y: usize, apart: usize, left: usize, right: usize) -> f64 {
    let lifted = (left..=right)
        .filter(|&x| {
            let around = chroma(pixel(f, x, y - apart)).max(chroma(pixel(f, x, y + apart)));
            chroma(pixel(f, x, y)) - around >= LINE_LIFT
        })
        .count();
    lifted as f64 / (right - left + 1) as f64
}

fn line_above(f: &Frame, rule: (usize, usize, usize)) -> Option<Bar> {
    let (rule_top, left, right) = rule;
    let centre = f.width / 2;
    let half = centre.checked_sub(left)?.max(right.checked_sub(centre)?);
    let (left, right) = (centre.checked_sub(half)?, (centre + half).min(f.width - 1));
    let length = (right - left) as f64;
    let at = |share: f64| (share * length).round() as usize;
    let (left, right) = (left + at(END_CAP), right.checked_sub(at(END_CAP))?);
    let lowest = rule_top.checked_sub(at(LINE_TO))?;
    let highest = rule_top.checked_sub(at(LINE_FROM))?;
    let strengths: Vec<(usize, f64)> = (highest..=lowest)
        .filter(|&y| y >= at(LINE_REFERENCE) && y + at(LINE_REFERENCE) < f.height)
        .map(|y| (y, line_strength(f, y, at(LINE_REFERENCE), left, right)))
        .collect();
    let &(row, best) = strengths.iter().max_by(|a, b| a.1.total_cmp(&b.1))?;
    if best < MIN_LINE || left >= right {
        return None;
    }
    let thick = |y: usize| strengths.iter().any(|&(r, s)| r == y && s >= LINE_SHARE * best);
    let most = at(LINE_THICK).max(1);
    let top = (highest..row).rev().take(most).take_while(|&y| thick(y)).last().unwrap_or(row);
    let bottom = (row + 1..=lowest).take(most).take_while(|&y| thick(y)).last().unwrap_or(row);
    Some(Bar { top, bottom, left, right })
}

pub fn find_bar(f: &Frame) -> Option<Bar> {
    rules(f).into_iter().filter_map(|rule| line_above(f, rule)).max_by_key(|bar| bar.right - bar.left)
}

fn line_colour(f: &Frame, bar: &Bar) -> [i32; 3] {
    median((bar.left..=bar.right).flat_map(|x| (bar.top..=bar.bottom).map(move |y| (x, y))).map(|(x, y)| pixel(f, x, y)).collect())
}

fn coloured(f: &Frame, x: usize, y: usize) -> bool {
    let p = pixel(f, x, y);
    p.iter().max().is_some_and(|&hi| hi > GLYPH_BRIGHT) && chroma(p) > CHROMA as i32
}

fn opened(lit: &[Vec<bool>], r: usize) -> Vec<Vec<bool>> {
    let (h, w) = (lit.len(), lit.first().map_or(0, Vec::len));
    let around = |y: usize, x: usize| (y.saturating_sub(r)..=(y + r).min(h - 1)).flat_map(move |yy| (x.saturating_sub(r)..=(x + r).min(w - 1)).map(move |xx| (yy, xx)));
    let core: Vec<Vec<bool>> = (0..h)
        .map(|y| (0..w).map(|x| y >= r && x >= r && y + r < h && x + r < w && around(y, x).all(|(yy, xx)| lit[yy][xx])).collect())
        .collect();
    (0..h).map(|y| (0..w).map(|x| lit[y][x] && around(y, x).any(|(yy, xx)| core[yy][xx])).collect()).collect()
}

fn sides(f: &Frame, bar: &Bar) -> Vec<(usize, usize, bool)> {
    let reach = bar.px(REACH);
    let line = line_colour(f, bar);
    let backdrop_rows = bar.top.saturating_sub(bar.px(BACKDROP_FROM))..bar.top.saturating_sub(bar.px(BACKDROP_TO));
    let rows: Vec<usize> = (1..=reach)
        .flat_map(|d| [bar.top.checked_sub(d), Some(bar.bottom + d).filter(|&y| y < f.height)])
        .flatten()
        .collect();
    let past: Vec<usize> = (reach + bar.px(PAST_FROM)..=reach + bar.px(PAST_TO))
        .flat_map(|d| [bar.top.checked_sub(d), Some(bar.bottom + d).filter(|&y| y < f.height)])
        .flatten()
        .collect();
    let mut through = Vec::with_capacity(bar.right - bar.left + 1);
    let lit: Vec<Vec<bool>> = (bar.left..=bar.right)
        .map(|x| {
            let backdrop = median(backdrop_rows.clone().map(|y| pixel(f, x, y)).collect());
            let apart = distance(line, backdrop) as f64;
            let like = |y: usize| {
                let p = pixel(f, x, y);
                (distance(p, line) as f64) < LINE_COLOUR * apart && distance(p, backdrop) as f64 >= BACKDROP_SHARE * apart
            };
            through.push(past.iter().any(|&y| like(y)));
            rows.iter().map(|&y| like(y)).collect()
        })
        .collect();
    let columns = lit.len() as f64;
    let across: Vec<bool> = (0..rows.len()).map(|i| lit.iter().filter(|c| c[i]).count() as f64 > ACROSS * columns).collect();
    let gap = bar.px(STROKE_GAP).max(1);
    let joined = |mut on: Vec<usize>| {
        on.sort_unstable();
        on.dedup();
        on.iter().try_fold(0, |reached, &d| if d - reached <= gap { Ok(d) } else { Err(reached) }).unwrap_or_else(|r| r)
    };
    lit.iter()
        .zip(through)
        .map(|(column, through)| {
            let on: Vec<usize> = rows.iter().zip(column).zip(&across).filter(|((_, on), skip)| **on && !**skip).map(|((&y, _), _)| y).collect();
            let up = joined(on.iter().filter(|&&y| y < bar.top).map(|&y| bar.top - y).collect());
            let down = joined(on.iter().filter(|&&y| y > bar.bottom).map(|&y| y - bar.bottom).collect());
            (up, down, through)
        })
        .collect()
}

fn spikes(sided: &[(usize, usize, bool)], bar: &Bar) -> Vec<Spike> {
    let env: Vec<usize> = sided.iter().map(|&(up, down, _)| up.max(down)).collect();
    let (floor, gap, narrow, tall) = (bar.px(MIN_AMPLITUDE), bar.px(MERGE_GAP), bar.px(MIN_WIDTH), bar.px(TALL_SPIKE));
    let mut packets: Vec<(usize, usize)> = Vec::new();
    for (x, _) in env.iter().enumerate().filter(|(_, a)| **a >= floor) {
        match packets.last_mut() {
            Some((_, end)) if x - *end <= gap => *end = x,
            _ => packets.push((x, x)),
        }
    }
    packets
        .into_iter()
        .filter(|&(start, end)| {
            let run = &sided[start..=end];
            let both = run.iter().any(|s| s.0 > 0) && run.iter().any(|s| s.1 > 0) && !run.iter().any(|s| s.2);
            end - start + 1 >= narrow || (both && env[start..=end].iter().any(|&a| a >= tall))
        })
        .map(|(start, end)| Spike {
            at: bar.along((bar.left + start) as f64 + (end - start) as f64 / 2.0),
            width: (end - start + 1) as f64 / bar.length(),
        })
        .collect()
}

fn tips(sided: &[(usize, usize, bool)], bar: &Bar) -> Vec<Tip> {
    let s: Vec<i64> = sided.iter().map(|&(up, down, _)| up as i64 - down as i64).collect();
    let tip = bar.px(TIP) as i64;
    (1..s.len().saturating_sub(1))
        .filter_map(|i| {
            let at = bar.along((bar.left + i) as f64);
            let slot = (at - SLOT_ZERO) / SLOT;
            if s[i] <= -tip && s[i] <= s[i - 1] && s[i] < s[i + 1] {
                Some(Tip { at, slot: slot.round().max(0.0) as usize, up: false })
            } else if s[i] >= tip && s[i] >= s[i - 1] && s[i] > s[i + 1] {
                Some(Tip { at, slot: (slot - 0.5).round().max(0.0) as usize, up: true })
            } else {
                None
            }
        })
        .collect()
}

fn circle(f: &Frame, x: usize, y: usize, r: usize) -> f64 {
    let mut lum: Vec<f64> = (0..HALO_SAMPLES)
        .filter_map(|i| {
            let t = i as f64 * std::f64::consts::TAU / HALO_SAMPLES as f64;
            let (px, py) = ((x as f64 + r as f64 * t.cos()).round(), (y as f64 + r as f64 * t.sin()).round());
            (px >= 0.0 && py >= 0.0 && (px as usize) < f.width && (py as usize) < f.height)
                .then(|| pixel(f, px as usize, py as usize).iter().sum::<i32>() as f64 / 3.0)
        })
        .collect();
    lum.sort_by(f64::total_cmp);
    lum.get(lum.len() / 2).copied().unwrap_or(0.0)
}

fn haloed(f: &Frame, bar: &Bar, x: usize, y: usize) -> bool {
    let ring = (bar.px(HALO_FROM)..=bar.px(HALO_TO)).map(|r| circle(f, x, y, r)).fold(f64::MIN, f64::max);
    let outside: Vec<f64> = (bar.px(OUTSIDE_FROM)..=bar.px(OUTSIDE_TO)).map(|r| circle(f, x, y, r)).collect();
    let outside = outside.iter().sum::<f64>() / outside.len().max(1) as f64;
    ring - outside >= HALO_STEP
}

pub fn icons(f: &Frame, bar: &Bar) -> Vec<Icon> {
    let rows = (bar.bottom + bar.px(ICON_FROM))..(bar.bottom + bar.px(ICON_TO)).min(f.height);
    let height = rows.len();
    let columns = bar.left..=bar.right;
    let needle: Vec<bool> =
        columns.clone().map(|x| rows.clone().filter(|&y| white(f, x, y)).count() as f64 >= NEEDLE_COLUMN * height as f64).collect();
    let colour: Vec<Vec<bool>> = rows.clone().map(|y| columns.clone().map(|x| coloured(f, x, y)).collect()).collect();
    let discs = opened(&colour, bar.px(DISC_OPEN).max(1));
    let top = bar.bottom + bar.px(ICON_FROM);
    let mut lit: Vec<(usize, usize)> = columns
        .clone()
        .flat_map(|x| {
            let (discs, needle) = (&discs, &needle);
            rows.clone()
                .filter(move |&y| (white(f, x, y) && !needle[x - bar.left]) || discs[y - top][x - bar.left])
                .map(move |y| (x, y))
        })
        .collect();
    let reach = bar.px(ICON_GAP).max(1);
    let mut found = Vec::new();
    while let Some(seed) = lit.pop() {
        let mut blob = vec![seed];
        let mut i = 0;
        while i < blob.len() {
            let (x, y) = blob[i];
            let (near, rest): (Vec<_>, Vec<_>) = lit.into_iter().partition(|&(px, py)| px.abs_diff(x) <= reach && py.abs_diff(y) <= reach);
            lit = rest;
            blob.extend(near);
            i += 1;
        }
        let (x0, x1) = (blob.iter().map(|p| p.0).min().unwrap_or(0), blob.iter().map(|p| p.0).max().unwrap_or(0));
        let (y0, y1) = (blob.iter().map(|p| p.1).min().unwrap_or(0), blob.iter().map(|p| p.1).max().unwrap_or(0));
        let big = (blob.len() as f64) >= ICON_PIXELS * bar.length();
        let sized = x1 - x0 + 1 >= bar.px(ICON_MIN) && x1 - x0 < bar.px(ICON_MAX) && y1 - y0 < bar.px(ICON_MAX);
        let x = blob.iter().map(|p| p.0).sum::<usize>() / blob.len();
        let y = blob.iter().map(|p| p.1).sum::<usize>() / blob.len();
        if big && sized && y.abs_diff(bar.bottom + bar.px(ICON_ROW)) <= bar.px(ICON_ROW_SLACK) && haloed(f, bar, x, y) {
            found.push(Icon { at: bar.along(x as f64), x, y });
        }
    }
    found.sort_by(|a, b| a.at.total_cmp(&b.at));
    found
}

pub fn read(f: &Frame) -> Option<Reading> {
    let bar = find_bar(f)?;
    let sided = sides(f, &bar);
    Some(Reading { spikes: spikes(&sided, &bar), tips: tips(&sided, &bar), icons: icons(f, &bar), bar })
}

#[cfg(test)]
mod tests {
    use super::*;

    const BACKGROUND: [u8; 3] = [17, 74, 101];
    const LINE: [u8; 3] = [26, 153, 221];
    const WHITE_STAR: [u8; 3] = [250, 250, 250];

    fn frame(w: usize, h: usize) -> Frame {
        Frame { width: w, height: h, rgb: BACKGROUND.repeat(w * h) }
    }

    fn paint(f: &mut Frame, x: usize, y: usize, c: [u8; 3]) {
        let i = (y * f.width + x) * 3;
        f.rgb[i..i + 3].copy_from_slice(&c);
    }

    fn with_bar(spikes: &[(usize, usize, usize)]) -> Frame {
        let mut f = frame(5120, 1440);
        for x in 2052..=3069 {
            paint(&mut f, x, 1112, LINE);
            paint(&mut f, x, 1113, LINE);
            paint(&mut f, x, 1163, LINE);
        }
        for &(centre, half, amp) in spikes {
            for x in centre - half..=centre + half {
                let d = if x % 2 == 0 { amp } else { amp / 2 };
                for y in 1112 - d..1112 {
                    paint(&mut f, x, y, LINE);
                }
            }
        }
        f
    }

    const FIRST: &[u8] = include_bytes!("../tests/fixtures/fss_first_1980_1000.png");
    const NEBULA: &[u8] = include_bytes!("../tests/fixtures/fss_nebula_1980_1000.png");
    const ZOOMED: &[u8] = include_bytes!("../tests/fixtures/fss_zoomed_1980_1000.png");
    const BACKDROP: &[u8] = include_bytes!("../tests/fixtures/fss_backdrop_1980_1000.png");
    const STAR: &[u8] = include_bytes!("../tests/fixtures/fss_star_1980_1000.png");
    const NEEDLE_SPIKE: &[u8] = include_bytes!("../tests/fixtures/fss_needle_spike_1980_1000.png");

    fn real_capture() -> Frame {
        pasted(FIRST)
    }

    fn pasted(fixture: &[u8]) -> Frame {
        let decoder = png::Decoder::new(std::io::Cursor::new(fixture));
        let mut reader = decoder.read_info().expect("png header");
        let mut crop = vec![0; reader.output_buffer_size()];
        let info = reader.next_frame(&mut crop).expect("png frame");
        let mut f = frame(5120, 1440);
        for y in 0..info.height as usize {
            for x in 0..info.width as usize {
                let i = (y * info.width as usize + x) * 3;
                paint(&mut f, 1980 + x, 1000 + y, [crop[i], crop[i + 1], crop[i + 2]]);
            }
        }
        f
    }

    fn rescale(src: &Frame, width: usize, height: usize) -> Frame {
        let scale = height as f64 / src.height as f64;
        let mut f = frame(width, height);
        for y in 0..height {
            let sy = ((y as f64 + 0.5) / scale) as usize;
            for x in 0..width {
                let sx = src.width as f64 / 2.0 + (x as f64 + 0.5 - width as f64 / 2.0) / scale;
                if sx >= 0.0 && (sx as usize) < src.width && sy < src.height {
                    let i = (sy * src.width + sx as usize) * 3;
                    paint(&mut f, x, y, [src.rgb[i], src.rgb[i + 1], src.rgb[i + 2]]);
                }
            }
        }
        f
    }

    fn rounded(r: &Reading) -> Vec<f64> {
        r.spikes.iter().map(|s| (s.at * 100.0).round() / 100.0).collect()
    }

    #[test]
    fn finds_the_signal_line_above_the_tick_rule_and_trims_its_end_caps() {
        let bar = find_bar(&with_bar(&[])).expect("bar");
        assert_eq!((bar.top, bar.bottom), (1112, 1113));
        assert_eq!((bar.left, bar.right), (2051 + 14, 3069 - 14));
    }

    #[test]
    fn no_bar_outside_the_fss() {
        assert_eq!(read(&frame(5120, 1440)), None);
    }

    #[test]
    fn reports_each_packet_where_it_sits_and_ignores_white_stars() {
        let mut f = with_bar(&[(2300, 20, 24), (2900, 30, 12)]);
        for y in 1090..1100 {
            paint(&mut f, 2600, y, WHITE_STAR);
        }
        let r = read(&f).expect("bar");
        assert_eq!(r.spikes.len(), 2);
        let span = (3055 - 2066) as f64;
        assert!((r.spikes[0].at - (2300 - 2066) as f64 / span).abs() < 0.002);
        assert!((r.spikes[1].at - (2900 - 2066) as f64 / span).abs() < 0.002);
    }

    #[test]
    fn a_flat_bar_has_no_spikes() {
        assert_eq!(read(&with_bar(&[])).expect("bar").spikes, Vec::new());
    }

    #[test]
    fn reads_a_real_capture() {
        let r = read(&real_capture()).expect("bar");
        assert_eq!(rounded(&r), [0.33, 0.36, 0.39, 0.43, 0.78, 0.81]);
    }

    #[test]
    fn every_slot_a_real_capture_lights_lies_in_one_of_its_spikes() {
        let r = read(&real_capture()).expect("bar");
        assert!(!r.tips.is_empty());
        for slot in r.slots() {
            assert!(r.spikes.iter().any(|s| (slot_at(slot) - s.at).abs() <= s.width / 2.0 + SLOT), "slot {slot} lies outside every spike");
        }
    }

    #[test]
    fn a_tip_names_the_slot_of_its_cycle() {
        let mut f = with_bar(&[]);
        let bar = find_bar(&f).expect("bar");
        let x = |share: f64| bar.left + (share * (bar.right - bar.left) as f64).round() as usize;
        let (down, up) = (x(slot_at(100)), x(slot_at(100) + SLOT / 2.0));
        for y in 1114..1114 + 20 {
            paint(&mut f, down, y, LINE);
        }
        for y in 1112 - 20..1112 {
            paint(&mut f, up, y, LINE);
        }
        assert_eq!(read(&f).expect("bar").slots(), [100]);
    }

    #[test]
    fn reads_captures_over_a_nebula_zoomed_in_and_over_the_backdrop() {
        let cases: [Case; 3] = [
            (NEBULA, [0.36, 0.39, 0.43, 0.85], &[]),
            (ZOOMED, [0.36, 0.39, 0.43, 0.85], &[0.42]),
            (BACKDROP, [0.36, 0.39, 0.43, 0.85], &[0.39, 0.42]),
        ];
        for (fixture, spikes, icons) in cases {
            let r = read(&pasted(fixture)).expect("bar");
            assert_eq!(rounded(&r), spikes);
            assert_eq!(icon_at(&r), icons);
        }
    }

    type Case = (&'static [u8], [f64; 4], &'static [f64]);

    fn icon_at(r: &Reading) -> Vec<f64> {
        r.icons.iter().map(|i| (i.at * 100.0).round() / 100.0).collect()
    }

    #[test]
    fn keeps_a_single_body_spike_the_needle_cuts_in_half() {
        let r = read(&pasted(NEEDLE_SPIKE)).expect("bar");
        assert_eq!(rounded(&r), [0.33, 0.36, 0.39, 0.43, 0.49, 0.69, 0.81]);
    }

    #[test]
    fn a_star_on_the_icon_row_has_no_halo_and_is_not_an_icon() {
        let r = read(&pasted(STAR)).expect("bar");
        assert_eq!(icon_at(&r), [0.39, 0.42]);
    }

    #[test]
    fn reads_the_same_bar_at_other_resolutions() {
        let original = real_capture();
        let expected = read(&original).expect("bar");
        for (w, h) in [(3840, 2160), (2560, 1440), (3440, 1440), (1920, 1080), (2560, 1080), (1600, 900)] {
            let scaled = rescale(&original, w, h);
            let r = read(&scaled).unwrap_or_else(|| panic!("no bar at {w}x{h}"));
            if h >= 1080 {
                let near = |a: f64, set: &[Spike]| set.iter().any(|s| (s.at - a).abs() < 0.005);
                assert!(r.spikes.iter().all(|s| near(s.at, &expected.spikes)), "a false spike at {w}x{h}: {:?}", rounded(&r));
                let missed = expected.spikes.iter().filter(|s| !near(s.at, &r.spikes)).count();
                assert!(missed <= 1, "{missed} bands missed at {w}x{h}");
            }
        }
    }

    #[test]
    #[ignore]
    fn reads_every_capture_in_fss_dir() {
        let dir = std::env::var("FSS_DIR").expect("FSS_DIR");
        let mut paths: Vec<_> = std::fs::read_dir(dir).expect("dir").flatten().map(|e| e.path()).collect();
        paths.sort();
        for path in paths.iter().filter(|p| p.extension().is_some_and(|e| e == "png")) {
            let decoder = png::Decoder::new(std::io::BufReader::new(std::fs::File::open(path).expect("open")));
            let mut reader = decoder.read_info().expect("png header");
            let mut rgb = vec![0; reader.output_buffer_size()];
            let info = reader.next_frame(&mut rgb).expect("png frame");
            let part = Frame { width: info.width as usize, height: info.height as usize, rgb };
            let name = path.file_stem().unwrap_or_default().to_string_lossy().to_string();
            let placed: Option<Vec<usize>> = name.split_once("-strip-").map(|(_, tail)| tail.split(['-', 'x']).filter_map(|v| v.parse().ok()).collect());
            let f = match placed.as_deref() {
                Some([x0, y0, w, h]) => {
                    let mut f = frame(*w, *h);
                    for y in 0..part.height {
                        for x in 0..part.width {
                            let i = (y * part.width + x) * 3;
                            paint(&mut f, x0 + x, y0 + y, [part.rgb[i], part.rgb[i + 1], part.rgb[i + 2]]);
                        }
                    }
                    f
                }
                _ => part,
            };
            let r = read(&f);
            let at = |v: Vec<f64>| v.iter().map(|a| (a * 1000.0).round() / 1000.0).collect::<Vec<_>>();
            println!(
                "{} {:?} spikes {:?} icons {:?}",
                path.file_name().unwrap().to_string_lossy(),
                r.as_ref().map(|r| r.bar),
                r.as_ref().map(|r| at(r.spikes.iter().map(|s| s.at).collect())),
                r.map(|r| r.icons.iter().map(|i| ((i.at * 1000.0).round() / 1000.0, i.y as i64 - r.bar.bottom as i64)).collect::<Vec<_>>())
            );
        }
    }
}
