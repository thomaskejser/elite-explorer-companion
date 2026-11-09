use std::collections::VecDeque;

use crate::fss::Frame;

const UI_BOXES: [(f64, f64, f64, f64); 4] =
    [(0.0, 0.0, 0.287, 1.0), (0.716, 0.0, 1.0, 1.0), (0.265, 0.0, 0.580, 0.140), (0.320, 0.860, 0.695, 0.980)];
const BG_STEP: usize = 8;
const BG_SIZE: usize = 25;
const BG_PERCENTILE: usize = 20;
const MIN_PEAK: f32 = 60.0;
const LOW: f32 = 25.0;
const PLATEAU: u8 = 4;
const RAY: usize = 96;
const MIN_DISC: usize = 4;
const MIN_CORE: usize = 5;
const ZONE_GAP: f64 = 0.15;
const ZONE_WIDTH: f64 = 0.6;
const ZONE_MIN: usize = 3;
const HALO_LEVEL: f32 = 0.25;
const PANEL_LEVEL: u8 = 30;
const PANEL_RADIUS: usize = 2;
const PANEL_GROW: usize = 2;
const CYAN_GROW: usize = 6;
const MIN_GIANT_DISC: usize = 6;
const MIN_HALO_RATIO: f64 = 0.5;
const MAX_HALO_RATIO: f64 = 0.8;
const MAX_CROSS: f64 = 1.6;
const MIN_WHITE: u8 = 240;
const MAX_ELONG: f64 = 1.5;
const COLOUR_WINDOW: i64 = 60;
const COLOUR_BACKDROP: f64 = 55.0;
const MIN_HALO_RING: i64 = 2;
const INNER_FROM: f64 = 0.4;
const INNER_TO: f64 = 0.8;
const MIN_INNER_WHITE: f64 = 0.68;
const MIN_WHITE_DISC: usize = 8;
const HOLE_LEVEL: u8 = 16;
const MIN_HOLE_AREA: usize = 6;
const MIN_HOLE_FILL: f64 = 0.6;
const MAX_HOLE_ASPECT: f64 = 1.3;
const HOLE_RING_FROM: f64 = 1.6;
const HOLE_RING_TO: f64 = 3.0;
const HOLE_RING_PAD: f64 = 3.0;
const HOLE_DARK_LEVEL: u8 = 30;
const MAX_HOLE_DARK: f64 = 0.02;
const MIN_HOLE_SURROUND: f64 = 50.0;
const AXES: [(i64, i64); 4] = [(0, -1), (0, 1), (-1, 0), (1, 0)];
const DIAGONALS: [(i64, i64); 4] = [(-1, -1), (-1, 1), (1, -1), (1, 1)];

#[derive(Clone, Debug)]
pub struct Hole {
    pub x: usize,
    pub y: usize,
    pub radius: f64,
}

pub struct Scan {
    pub stars: Vec<Star>,
    pub holes: Vec<Hole>,
}

#[derive(Clone, Debug)]
pub struct Star {
    pub x: usize,
    pub y: usize,
    pub disc: usize,
    pub halo: i64,
    pub cross: f64,
    pub white: u8,
    pub cores: usize,
    pub elong: f64,
    pub blue: f64,
    pub inner_white: f64,
    pub giant: bool,
}

impl Star {
    pub fn white_filled(&self) -> bool {
        self.disc >= MIN_WHITE_DISC && self.inner_white >= MIN_INNER_WHITE
    }
}

struct Grid<T> {
    w: usize,
    h: usize,
    v: Vec<T>,
}

impl<T: Copy> Grid<T> {
    fn new(w: usize, h: usize, fill: T) -> Grid<T> {
        Grid { w, h, v: vec![fill; w * h] }
    }

    fn at(&self, x: usize, y: usize) -> T {
        self.v[y * self.w + x]
    }

    fn set(&mut self, x: usize, y: usize, value: T) {
        self.v[y * self.w + x] = value;
    }
}

pub fn detect(frame: &Frame) -> Vec<Star> {
    scan(frame).stars
}

pub fn scan(frame: &Frame) -> Scan {
    let (w, h) = (frame.width, frame.height);
    let px = |x: usize, y: usize| {
        let i = (y * w + x) * 3;
        [frame.rgb[i], frame.rgb[i + 1], frame.rgb[i + 2]]
    };
    let mut lum = Grid::new(w, h, 0u8);
    for y in 0..h {
        for x in 0..w {
            let [r, g, b] = px(x, y);
            lum.set(x, y, r.max(g).max(b));
        }
    }
    let mask = ui_mask(frame, &lum);
    let bg = background(&lum, &mask);
    let mut res = Grid::new(w, h, 0f32);
    for (i, r) in res.v.iter_mut().enumerate() {
        *r = lum.v[i] as f32 - bg.v[i] as f32;
    }
    let mut label = Grid::new(w, h, 0u32);
    let mut stars = Vec::new();
    let mut next = 0u32;
    let mut queue = VecDeque::new();
    for sy in 0..h {
        for sx in 0..w {
            if label.at(sx, sy) != 0 || mask.at(sx, sy) || res.at(sx, sy) < LOW {
                continue;
            }
            next += 1;
            let mut pixels = Vec::new();
            label.set(sx, sy, next);
            queue.push_back((sx, sy));
            while let Some((x, y)) = queue.pop_front() {
                pixels.push((x, y));
                for (nx, ny) in neighbours(x, y, w, h) {
                    if label.at(nx, ny) == 0 && !mask.at(nx, ny) && res.at(nx, ny) >= LOW {
                        label.set(nx, ny, next);
                        queue.push_back((nx, ny));
                    }
                }
            }
            stars.extend(measure(frame, &lum, &bg, &res, &pixels));
        }
    }
    let holes = black_holes(&lum, &mask);
    Scan { stars, holes }
}

fn black_holes(lum: &Grid<u8>, mask: &Grid<bool>) -> Vec<Hole> {
    let (w, h) = (lum.w, lum.h);
    let mut seen = Grid::new(w, h, false);
    let mut holes = Vec::new();
    let mut queue = VecDeque::new();
    for sy in 0..h {
        for sx in 0..w {
            if seen.at(sx, sy) || lum.at(sx, sy) > HOLE_LEVEL {
                continue;
            }
            seen.set(sx, sy, true);
            queue.push_back((sx, sy));
            let mut pixels = Vec::new();
            while let Some((x, y)) = queue.pop_front() {
                pixels.push((x, y));
                for (nx, ny) in neighbours(x, y, w, h) {
                    if !seen.at(nx, ny) && lum.at(nx, ny) <= HOLE_LEVEL {
                        seen.set(nx, ny, true);
                        queue.push_back((nx, ny));
                    }
                }
            }
            if let Some(hole) = hole_at(lum, mask, &pixels) {
                holes.push(hole);
            }
        }
    }
    holes
}

fn hole_at(lum: &Grid<u8>, mask: &Grid<bool>, pixels: &[(usize, usize)]) -> Option<Hole> {
    let area = pixels.len();
    if area < MIN_HOLE_AREA {
        return None;
    }
    let (x0, x1) = (pixels.iter().map(|p| p.0).min()?, pixels.iter().map(|p| p.0).max()?);
    let (y0, y1) = (pixels.iter().map(|p| p.1).min()?, pixels.iter().map(|p| p.1).max()?);
    let (bw, bh) = ((x1 - x0 + 1) as f64, (y1 - y0 + 1) as f64);
    if (area as f64) / (bw * bh) < MIN_HOLE_FILL || bw.max(bh) > MAX_HOLE_ASPECT * bw.min(bh) + 1.0 {
        return None;
    }
    let y = (pixels.iter().map(|p| p.1 as f64).sum::<f64>() / area as f64) as usize;
    let x = (pixels.iter().map(|p| p.0 as f64).sum::<f64>() / area as f64) as usize;
    if mask.at(x, y) {
        return None;
    }
    let radius = (area as f64 / std::f64::consts::PI).sqrt();
    let reach = (HOLE_RING_TO * radius) as usize + 4;
    if y < reach || x < reach || y + reach >= lum.h || x + reach >= lum.w {
        return None;
    }
    let mut ring = Vec::new();
    let r = reach as i64;
    for dy in -r..=r {
        for dx in -r..=r {
            let d = ((dy * dy + dx * dx) as f64).sqrt();
            if d >= HOLE_RING_FROM * radius && d <= HOLE_RING_TO * radius + HOLE_RING_PAD {
                ring.push(lum.at((x as i64 + dx) as usize, (y as i64 + dy) as usize) as f64);
            }
        }
    }
    let dark = ring.iter().filter(|&&v| v <= HOLE_DARK_LEVEL as f64).count() as f64 / ring.len().max(1) as f64;
    if dark > MAX_HOLE_DARK || median(&mut ring) < MIN_HOLE_SURROUND {
        return None;
    }
    Some(Hole { x, y, radius })
}

fn neighbours(x: usize, y: usize, w: usize, h: usize) -> impl Iterator<Item = (usize, usize)> {
    let mut out = [(usize::MAX, usize::MAX); 4];
    if x > 0 {
        out[0] = (x - 1, y);
    }
    if x + 1 < w {
        out[1] = (x + 1, y);
    }
    if y > 0 {
        out[2] = (x, y - 1);
    }
    if y + 1 < h {
        out[3] = (x, y + 1);
    }
    out.into_iter().filter(|p| p.0 != usize::MAX)
}

fn measure(frame: &Frame, lum: &Grid<u8>, bg: &Grid<u8>, res: &Grid<f32>, pixels: &[(usize, usize)]) -> Vec<Star> {
    let Some(top) = pixels.iter().map(|&(x, y)| lum.at(x, y)).max() else { return Vec::new() };
    let (x0, x1) = (pixels.iter().map(|p| p.0).min().unwrap_or(0), pixels.iter().map(|p| p.0).max().unwrap_or(0));
    let (y0, y1) = (pixels.iter().map(|p| p.1).min().unwrap_or(0), pixels.iter().map(|p| p.1).max().unwrap_or(0));
    let bg_max = (y0..=y1).flat_map(|y| (x0..=x1).map(move |x| (x, y))).map(|(x, y)| bg.at(x, y)).max().unwrap_or(0);
    if (top as f32 - bg_max as f32) < MIN_PEAK {
        return Vec::new();
    }
    let floor = top.saturating_sub(PLATEAU);
    let plateau: Vec<(usize, usize)> = pixels.iter().copied().filter(|&(x, y)| lum.at(x, y) >= floor).collect();
    let inner = inner_core(&plateau, x0, y0, x1 - x0 + 1, y1 - y0 + 1);
    let groups = core_groups(&inner, x0, y0, x1 - x0 + 1, y1 - y0 + 1);
    let big: Vec<&[(usize, usize)]> = groups.iter().filter(|g| g.len() >= MIN_CORE).map(Vec::as_slice).collect();
    let cores = big.len();
    let targets = if big.is_empty() { vec![inner.as_slice()] } else { big };
    targets.into_iter().filter_map(|core| star_at(frame, res, core, cores)).collect()
}

fn star_at(frame: &Frame, res: &Grid<f32>, core: &[(usize, usize)], cores: usize) -> Option<Star> {
    let (w, h) = (res.w, res.h);
    let n = core.len() as f64;
    let my = core.iter().map(|p| p.1 as f64).sum::<f64>() / n;
    let mx = core.iter().map(|p| p.0 as f64).sum::<f64>() / n;
    let elong = if core.len() > 2 {
        let (mut syy, mut sxx, mut sxy) = (0.0, 0.0, 0.0);
        for &(x, y) in core {
            let (dy, dx) = (y as f64 - my, x as f64 - mx);
            syy += dy * dy;
            sxx += dx * dx;
            sxy += dx * dy;
        }
        let d = n - 1.0;
        let (a, c, b) = (syy / d + 0.25, sxx / d + 0.25, sxy / d);
        let mid = (a + c) / 2.0;
        let spread = ((a - c) * (a - c) / 4.0 + b * b).sqrt();
        ((mid + spread) / (mid - spread)).sqrt()
    } else {
        1.0
    };
    let (y, x) = (my.round_ties_even() as usize, mx.round_ties_even() as usize);
    if y < RAY || x < RAY || y >= h - RAY || x >= w - RAY {
        return None;
    }
    let peak = res.at(x, y);
    if peak < MIN_PEAK {
        return None;
    }
    let axes: Vec<Vec<f32>> = AXES.iter().map(|&(dy, dx)| ray(res, x, y, dy, dx)).collect();
    let diags: Vec<Vec<f32>> = DIAGONALS.iter().map(|&(dy, dx)| ray(res, x, y, dy, dx)).collect();
    let disc = median4(diags.iter().map(|d| run_length(d, peak - (PLATEAU as f32) * 2.0) as f64)) as usize;
    if disc < MIN_DISC {
        return None;
    }
    let start = disc + 1usize.max((disc as f64 * ZONE_GAP) as usize);
    let end = (start + ZONE_MIN.max((disc as f64 * ZONE_WIDTH) as usize)).min(RAY + 1);
    let zone_mean = |r: &Vec<f32>| if start < end { r[start..end].iter().map(|&v| v as f64).sum::<f64>() / (end - start) as f64 } else { f64::NAN };
    let halo = median4(diags.iter().map(|d| run_length(d, peak * HALO_LEVEL) as f64)) as i64 - disc as i64;
    let cross = median4(axes.iter().map(zone_mean)) / median4(diags.iter().map(zone_mean)).max(1.0);
    let i = (y * w + x) * 3;
    let white = frame.rgb[i].min(frame.rgb[i + 1]).min(frame.rgb[i + 2]);
    let giant = disc >= MIN_GIANT_DISC
        && halo as f64 / disc as f64 >= MIN_HALO_RATIO
        && halo as f64 / disc as f64 <= MAX_HALO_RATIO
        && cross < MAX_CROSS
        && white >= MIN_WHITE
        && elong < MAX_ELONG;
    let blue = halo_blue(frame, x, y, disc, halo);
    let inner_white = inner_white(frame, x, y, disc);
    Some(Star { x, y, disc, halo, cross, white, cores, elong, blue, inner_white, giant })
}

fn halo_blue(frame: &Frame, x: usize, y: usize, disc: usize, halo: i64) -> f64 {
    let outer = disc as f64 + halo.max(MIN_HALO_RING) as f64;
    let mut backdrop: [Vec<f64>; 3] = [Vec::new(), Vec::new(), Vec::new()];
    let mut ring = Vec::new();
    for dy in -COLOUR_WINDOW..=COLOUR_WINDOW {
        for dx in -COLOUR_WINDOW..=COLOUR_WINDOW {
            let r = ((dy * dy + dx * dx) as f64).sqrt();
            let i = ((y as i64 + dy) as usize * frame.width + (x as i64 + dx) as usize) * 3;
            let p = [frame.rgb[i] as f64, frame.rgb[i + 1] as f64, frame.rgb[i + 2] as f64];
            if r > COLOUR_BACKDROP {
                for c in 0..3 {
                    backdrop[c].push(p[c]);
                }
            }
            if r > disc as f64 && r <= outer {
                ring.push(p);
            }
        }
    }
    let base: Vec<f64> = backdrop.iter_mut().map(|v| median(v)).collect();
    let mut glow = [0.0; 3];
    for p in &ring {
        for c in 0..3 {
            glow[c] += (p[c] - base[c]).max(0.0);
        }
    }
    glow[2] / (glow[0] + glow[1] + glow[2]).max(1.0)
}

fn inner_white(frame: &Frame, x: usize, y: usize, disc: usize) -> f64 {
    let (lo, hi) = (disc as f64 * INNER_FROM, disc as f64 * INNER_TO);
    let mut sum = [0.0; 3];
    let mut n = 0.0;
    for dy in -COLOUR_WINDOW..=COLOUR_WINDOW {
        for dx in -COLOUR_WINDOW..=COLOUR_WINDOW {
            let r = ((dy * dy + dx * dx) as f64).sqrt();
            if r < lo || r >= hi {
                continue;
            }
            let i = ((y as i64 + dy) as usize * frame.width + (x as i64 + dx) as usize) * 3;
            for c in 0..3 {
                sum[c] += frame.rgb[i + c] as f64;
            }
            n += 1.0;
        }
    }
    if n == 0.0 {
        return 1.0;
    }
    let mean = sum.map(|s| s / n);
    mean.iter().cloned().fold(f64::MAX, f64::min) / mean.iter().cloned().fold(0.0, f64::max).max(1.0)
}

fn median(v: &mut [f64]) -> f64 {
    v.sort_by(|a, b| a.total_cmp(b));
    let n = v.len();
    if n % 2 == 1 { v[n / 2] } else { (v[n / 2 - 1] + v[n / 2]) / 2.0 }
}

fn inner_core(plateau: &[(usize, usize)], x0: usize, y0: usize, bw: usize, bh: usize) -> Vec<(usize, usize)> {
    let mut on = Grid::new(bw, bh, false);
    for &(x, y) in plateau {
        on.set(x - x0, y - y0, true);
    }
    let mut depth = Grid::new(bw, bh, 0usize);
    for y in 0..bh {
        for x in 0..bw {
            if on.at(x, y) {
                let left = if x > 0 { depth.at(x - 1, y) } else { 0 };
                let up = if y > 0 { depth.at(x, y - 1) } else { 0 };
                depth.set(x, y, left.min(up) + 1);
            }
        }
    }
    for y in (0..bh).rev() {
        for x in (0..bw).rev() {
            if on.at(x, y) {
                let right = if x + 1 < bw { depth.at(x + 1, y) } else { 0 };
                let down = if y + 1 < bh { depth.at(x, y + 1) } else { 0 };
                depth.set(x, y, depth.at(x, y).min(right.min(down) + 1));
            }
        }
    }
    let deepest = plateau.iter().map(|&(x, y)| depth.at(x - x0, y - y0)).max().unwrap_or(0);
    let floor = 1usize.max(deepest.div_ceil(2));
    plateau.iter().copied().filter(|&(x, y)| depth.at(x - x0, y - y0) >= floor).collect()
}

fn core_groups(plateau: &[(usize, usize)], x0: usize, y0: usize, bw: usize, bh: usize) -> Vec<Vec<(usize, usize)>> {
    let mut on = Grid::new(bw, bh, false);
    for &(x, y) in plateau {
        on.set(x - x0, y - y0, true);
    }
    let mut seen = Grid::new(bw, bh, false);
    let mut groups = Vec::new();
    let mut queue = VecDeque::new();
    for &(px, py) in plateau {
        let (sx, sy) = (px - x0, py - y0);
        if seen.at(sx, sy) {
            continue;
        }
        seen.set(sx, sy, true);
        queue.push_back((sx, sy));
        let mut group = Vec::new();
        while let Some((x, y)) = queue.pop_front() {
            group.push((x + x0, y + y0));
            for (nx, ny) in neighbours(x, y, bw, bh) {
                if on.at(nx, ny) && !seen.at(nx, ny) {
                    seen.set(nx, ny, true);
                    queue.push_back((nx, ny));
                }
            }
        }
        groups.push(group);
    }
    groups
}

fn median4(values: impl Iterator<Item = f64>) -> f64 {
    let mut v: Vec<f64> = values.collect();
    v.sort_by(|a, b| a.total_cmp(b));
    (v[1] + v[2]) / 2.0
}

fn ray(res: &Grid<f32>, x: usize, y: usize, dy: i64, dx: i64) -> Vec<f32> {
    (0..=RAY)
        .map(|r| {
            let k = if dy == 0 || dx == 0 { r as i64 } else { (r as f64 / 1.4142).round_ties_even() as i64 };
            let (yy, xx) = (y as i64 + dy * k, x as i64 + dx * k);
            if (0..res.h as i64).contains(&yy) && (0..res.w as i64).contains(&xx) { res.at(xx as usize, yy as usize) } else { 0.0 }
        })
        .collect()
}

fn run_length(profile: &[f32], level: f32) -> usize {
    profile.iter().position(|&v| v < level).unwrap_or(profile.len())
}

fn ui_mask(frame: &Frame, lum: &Grid<u8>) -> Grid<bool> {
    let (w, h) = (lum.w, lum.h);
    let mut mask = Grid::new(w, h, false);
    for (fx0, fy0, fx1, fy1) in UI_BOXES {
        let (x0, x1) = ((fx0 * w as f64) as usize, ((fx1 * w as f64) as usize).min(w));
        let (y0, y1) = ((fy0 * h as f64) as usize, ((fy1 * h as f64) as usize).min(h));
        for y in y0..y1 {
            for x in x0..x1 {
                mask.set(x, y, true);
            }
        }
    }
    let mut cyan = Grid::new(w, h, false);
    for (i, c) in cyan.v.iter_mut().enumerate() {
        let (r, g, b) = (frame.rgb[i * 3] as i32, frame.rgb[i * 3 + 1] as i32, frame.rgb[i * 3 + 2] as i32);
        *c = g > 140 && b > 140 && g - r > 70 && b - r > 70;
    }
    let cyan = grow(&cyan, CYAN_GROW);
    let small = subsample(lum);
    let mut dark = Grid::new(small.w, small.h, false);
    for (d, &v) in dark.v.iter_mut().zip(&small.v) {
        *d = v < PANEL_LEVEL;
    }
    let opened = dilate_box(&erode_box(&dark, PANEL_RADIUS), PANEL_RADIUS);
    let closed = erode_box(&dilate_box(&opened, PANEL_RADIUS), PANEL_RADIUS);
    let panel = grow(&closed, PANEL_GROW);
    for y in 0..h {
        for x in 0..w {
            if cyan.at(x, y) || panel.at(x / BG_STEP, y / BG_STEP) {
                mask.set(x, y, true);
            }
        }
    }
    mask
}

fn subsample<T: Copy + Default>(g: &Grid<T>) -> Grid<T> {
    let (sw, sh) = (g.w.div_ceil(BG_STEP), g.h.div_ceil(BG_STEP));
    let mut out = Grid::new(sw, sh, T::default());
    for y in 0..sh {
        for x in 0..sw {
            out.set(x, y, g.at(x * BG_STEP, y * BG_STEP));
        }
    }
    out
}

fn grow(g: &Grid<bool>, steps: usize) -> Grid<bool> {
    let mut dist = Grid::new(g.w, g.h, usize::MAX / 2);
    for y in 0..g.h {
        for x in 0..g.w {
            let mut d = if g.at(x, y) { 0 } else { usize::MAX / 2 };
            if x > 0 {
                d = d.min(dist.at(x - 1, y) + 1);
            }
            if y > 0 {
                d = d.min(dist.at(x, y - 1) + 1);
            }
            dist.set(x, y, d);
        }
    }
    for y in (0..g.h).rev() {
        for x in (0..g.w).rev() {
            let mut d = dist.at(x, y);
            if x + 1 < g.w {
                d = d.min(dist.at(x + 1, y) + 1);
            }
            if y + 1 < g.h {
                d = d.min(dist.at(x, y + 1) + 1);
            }
            dist.set(x, y, d);
        }
    }
    let mut out = Grid::new(g.w, g.h, false);
    for (o, &d) in out.v.iter_mut().zip(&dist.v) {
        *o = d <= steps;
    }
    out
}

fn erode_box(g: &Grid<bool>, r: usize) -> Grid<bool> {
    box_filter(g, r, true)
}

fn dilate_box(g: &Grid<bool>, r: usize) -> Grid<bool> {
    box_filter(g, r, false)
}

fn box_filter(g: &Grid<bool>, r: usize, erode: bool) -> Grid<bool> {
    let mut out = Grid::new(g.w, g.h, false);
    for y in 0..g.h {
        for x in 0..g.w {
            let mut all = true;
            let mut any = false;
            for dy in -(r as i64)..=r as i64 {
                for dx in -(r as i64)..=r as i64 {
                    let (yy, xx) = (y as i64 + dy, x as i64 + dx);
                    let v = (0..g.h as i64).contains(&yy) && (0..g.w as i64).contains(&xx) && g.at(xx as usize, yy as usize);
                    all &= v;
                    any |= v;
                }
            }
            out.set(x, y, if erode { all } else { any });
        }
    }
    out
}

fn background(lum: &Grid<u8>, mask: &Grid<bool>) -> Grid<u8> {
    let mut small = subsample(lum);
    let hidden = subsample(mask);
    let mut shown: Vec<u8> = small.v.iter().zip(&hidden.v).filter(|(_, h)| !**h).map(|(v, _)| *v).collect();
    if !shown.is_empty() {
        let mid = shown.len() / 2;
        let fill = *shown.select_nth_unstable(mid).1;
        for (v, &h) in small.v.iter_mut().zip(&hidden.v) {
            if h {
                *v = fill;
            }
        }
    }
    let filtered = percentile_filter(&small);
    let (w, h) = (lum.w, lum.h);
    let mut out = Grid::new(w, h, 0u8);
    for y in 0..h {
        for x in 0..w {
            out.set(x, y, filtered.at(x / BG_STEP, y / BG_STEP));
        }
    }
    out
}

fn reflect(i: i64, n: usize) -> usize {
    let n = n as i64;
    let mut i = i;
    loop {
        if i < 0 {
            i = -i - 1;
        } else if i >= n {
            i = 2 * n - i - 1;
        } else {
            return i as usize;
        }
    }
}

fn percentile_filter(g: &Grid<u8>) -> Grid<u8> {
    let half = (BG_SIZE / 2) as i64;
    let rank = BG_SIZE * BG_SIZE * BG_PERCENTILE / 100;
    let mut out = Grid::new(g.w, g.h, 0u8);
    for y in 0..g.h {
        let rows: Vec<usize> = (-half..=half).map(|d| reflect(y as i64 + d, g.h)).collect();
        let mut hist = [0usize; 256];
        for dx in -half..=half {
            let xx = reflect(dx, g.w);
            for &yy in &rows {
                hist[g.at(xx, yy) as usize] += 1;
            }
        }
        for x in 0..g.w {
            if x > 0 {
                let (gone, come) = (reflect(x as i64 - 1 - half, g.w), reflect(x as i64 + half, g.w));
                for &yy in &rows {
                    hist[g.at(gone, yy) as usize] -= 1;
                    hist[g.at(come, yy) as usize] += 1;
                }
            }
            let mut seen = 0;
            for (v, &n) in hist.iter().enumerate() {
                seen += n;
                if seen > rank {
                    out.set(x, y, v as u8);
                    break;
                }
            }
        }
    }
    out
}

pub fn read_png(path: &std::path::Path) -> Result<Frame, String> {
    let file = std::fs::File::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut decoder = png::Decoder::new(std::io::BufReader::new(file));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder.read_info().map_err(|e| e.to_string())?;
    let mut buf = vec![0; reader.output_buffer_size()];
    let info = reader.next_frame(&mut buf).map_err(|e| e.to_string())?;
    let (w, h) = (info.width as usize, info.height as usize);
    let channels = info.color_type.samples();
    let rgb = match channels {
        3 => buf[..w * h * 3].to_vec(),
        4 => buf[..w * h * 4].as_chunks::<4>().0.iter().flat_map(|p| [p[0], p[1], p[2]]).collect(),
        n => return Err(format!("{}: {n} channels per pixel, expected 3 or 4", path.display())),
    };
    Ok(Frame { width: w, height: h, rgb })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reflect_mirrors_the_edge_pixel() {
        assert_eq!(reflect(-1, 5), 0);
        assert_eq!(reflect(-2, 5), 1);
        assert_eq!(reflect(5, 5), 4);
        assert_eq!(reflect(6, 5), 3);
    }

    #[test]
    fn a_round_soft_disc_is_a_giant_and_a_cross_is_not() {
        let (w, h) = (1400, 400);
        let mut rgb = vec![80u8; w * h * 3];
        let mut put = |x: usize, y: usize, v: f64| {
            let i = (y * w + x) * 3;
            let v = (80.0 + v).min(255.0) as u8;
            for c in 0..3 {
                rgb[i + c] = rgb[i + c].max(v);
            }
        };
        for y in 0..h {
            for x in 0..w {
                let r = ((x as f64 - 560.0).powi(2) + (y as f64 - 200.0).powi(2)).sqrt();
                put(x, y, if r <= 12.0 { 255.0 } else { 175.0 * (-(r - 12.0) / 6.0).exp() });
                let (dx, dy) = ((x as f64 - 840.0).abs(), (y as f64 - 200.0).abs());
                let core = (dx * dx + dy * dy).sqrt() <= 12.0;
                let arm = (dx <= 2.0 && dy <= 60.0) || (dy <= 2.0 && dx <= 60.0);
                if core || arm {
                    put(x, y, 255.0);
                }
            }
        }
        let stars = detect(&Frame { width: w, height: h, rgb });
        let at = |x: usize| stars.iter().find(|s| s.x.abs_diff(x) <= 2 && s.y.abs_diff(200) <= 2).expect("star found");
        assert!(at(560).giant, "{:?}", at(560));
        assert!(!at(840).giant, "{:?}", at(840));
    }

    #[test]
    fn a_black_disc_on_the_map_is_a_hole_and_a_black_panel_is_not() {
        let (w, h) = (1400, 400);
        let mut rgb = vec![90u8; w * h * 3];
        for y in 0..h {
            for x in 0..w {
                let disc = ((x as f64 - 560.0).powi(2) + (y as f64 - 200.0).powi(2)).sqrt() <= 7.0;
                let panel = (780..900).contains(&x) && (150..250).contains(&y);
                if disc || panel {
                    let i = (y * w + x) * 3;
                    rgb[i..i + 3].fill(0);
                }
            }
        }
        let holes = scan(&Frame { width: w, height: h, rgb }).holes;
        assert_eq!(holes.len(), 1, "{holes:?}");
        assert!(holes[0].x.abs_diff(560) <= 1 && holes[0].y.abs_diff(200) <= 1, "{:?}", holes[0]);
    }

    #[test]
    #[ignore]
    fn writes_the_captures_detections_for_the_bench() {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../log/fss/galaxy");
        let out = dir.join("analysis");
        std::fs::create_dir_all(&out).expect("analysis dir");
        let mut pngs: Vec<_> = std::fs::read_dir(&dir).expect("captures").filter_map(|e| e.ok()).map(|e| e.path()).filter(|p| p.extension().is_some_and(|x| x == "png")).collect();
        pngs.sort();
        for png in pngs {
            let started = std::time::Instant::now();
            let found = scan(&read_png(&png).expect("png"));
            let stars = found.stars;
            let mut csv = String::from("x,y,disc,halo,cross,white,cores,elong,blue,inner_white,giant
");
            for s in &stars {
                csv += &format!(
                    "{},{},{},{},{:.4},{},{},{:.4},{:.4},{:.4},{}
",
                    s.x, s.y, s.disc, s.halo, s.cross, s.white, s.cores, s.elong, s.blue, s.inner_white, s.giant
                );
            }
            let name = png.file_stem().unwrap().to_string_lossy().to_string();
            std::fs::write(out.join(format!("{name}-rust.csv")), csv).expect("write");
            let holes: String = std::iter::once("x,y,radius
".to_string())
                .chain(found.holes.iter().map(|h| format!("{},{},{:.4}
", h.x, h.y, h.radius)))
                .collect();
            std::fs::write(out.join(format!("{name}-rust-holes.csv")), holes).expect("write");
            println!("{name}: {} stars, {} giant, {} ms", stars.len(), stars.iter().filter(|s| s.giant).count(), started.elapsed().as_millis());
        }
    }
}
