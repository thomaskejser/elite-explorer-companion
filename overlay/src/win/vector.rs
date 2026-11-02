use crate::theme::{FSS_ICON_DISC, FSS_ICON_HALO_R, FSS_ICON_RING_ALPHA, FSS_ICON_RING_R, FSS_ICON_RING_W, Rgb, SIGNAL_PEN_DIV};

const SUB: i32 = 4;

#[derive(Clone, Debug)]
pub enum Shape {
    Line([f64; 2], [f64; 2], f64),
    Disc([f64; 2], f64),
    Ring([f64; 2], f64, f64),
    Polygon(Vec<[f64; 2]>),
}

#[derive(Clone, Debug)]
pub struct Icon {
    pub shapes: Vec<Shape>,
    pub rgb: Rgb,
    pub alpha: f64,
}

impl Shape {
    fn holds(&self, p: [f64; 2]) -> bool {
        let dist2 = |c: [f64; 2]| (p[0] - c[0]).powi(2) + (p[1] - c[1]).powi(2);
        match self {
            Shape::Line(a, b, w) => {
                let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
                let len2 = dx * dx + dy * dy;
                let t = if len2 > 0.0 { (((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2).clamp(0.0, 1.0) } else { 0.0 };
                dist2([a[0] + t * dx, a[1] + t * dy]) <= w * w / 4.0
            }
            Shape::Disc(c, r) => dist2(*c) <= r * r,
            Shape::Ring(c, r, w) => (dist2(*c).sqrt() - r).abs() <= w / 2.0,
            Shape::Polygon(corners) => {
                let mut inside = false;
                for (i, a) in corners.iter().enumerate() {
                    let b = corners[(i + 1) % corners.len()];
                    if (a[1] > p[1]) != (b[1] > p[1]) && p[0] < a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]) {
                        inside = !inside;
                    }
                }
                inside
            }
        }
    }

    fn bounds(&self) -> [f64; 4] {
        match self {
            Shape::Line(a, b, w) => [a[0].min(b[0]) - w, a[1].min(b[1]) - w, a[0].max(b[0]) + w, a[1].max(b[1]) + w],
            Shape::Disc(c, r) => [c[0] - r, c[1] - r, c[0] + r, c[1] + r],
            Shape::Ring(c, r, w) => [c[0] - r - w, c[1] - r - w, c[0] + r + w, c[1] + r + w],
            Shape::Polygon(corners) => corners.iter().fold([f64::MAX, f64::MAX, f64::MIN, f64::MIN], |b, q| {
                [b[0].min(q[0]), b[1].min(q[1]), b[2].max(q[0]), b[3].max(q[1])]
            }),
        }
    }
}

impl Icon {
    fn new(shapes: Vec<Shape>, rgb: Rgb) -> Icon {
        Icon { shapes, rgb, alpha: 1.0 }
    }

    pub fn coverage(&self, x: i32, y: i32) -> f64 {
        let mut hit = 0;
        for sy in 0..SUB {
            for sx in 0..SUB {
                let p = [x as f64 + (sx as f64 + 0.5) / SUB as f64, y as f64 + (sy as f64 + 0.5) / SUB as f64];
                if self.shapes.iter().any(|s| s.holds(p)) {
                    hit += 1;
                }
            }
        }
        hit as f64 / (SUB * SUB) as f64
    }

    pub fn bounds(&self) -> Option<[i32; 4]> {
        let b = self.shapes.iter().map(Shape::bounds).reduce(|a, b| [a[0].min(b[0]), a[1].min(b[1]), a[2].max(b[2]), a[3].max(b[3])])?;
        Some([b[0].floor() as i32, b[1].floor() as i32, b[2].ceil() as i32 + 1, b[3].ceil() as i32 + 1])
    }

    pub fn paint(&self, pixels: &mut [u32], width: i32, height: i32, opacity: u8) {
        let Some([x0, y0, x1, y1]) = self.bounds() else { return };
        let Rgb(r, g, b) = self.rgb;
        for y in y0.max(0)..y1.min(height) {
            for x in x0.max(0)..x1.min(width) {
                let cov = self.coverage(x, y);
                if cov <= 0.0 {
                    continue;
                }
                let s = opacity as f64 / 255.0 * self.alpha * cov;
                let p = &mut pixels[(y * width + x) as usize];
                let blend = |src: u8, shift: u32| ((src as f64 * s) + ((*p >> shift) & 0xff) as f64 * (1.0 - s)).round() as u32;
                *p = blend(255, 24) << 24 | blend(r, 16) << 16 | blend(g, 8) << 8 | blend(b, 0);
            }
        }
    }
}

pub fn dna(centre: [f64; 2], size: f64, rgb: Rgb) -> Icon {
    const STEPS: usize = 48;
    const AMPLITUDE: f64 = 0.24;
    const RUNGS: [f64; 5] = [0.08, 0.37, 0.5, 0.63, 0.92];
    let len = size * 0.92;
    let amp = size * AMPLITUDE;
    let pen = (size / 17.0).max(1.0);
    let axis = [std::f64::consts::FRAC_1_SQRT_2, -std::f64::consts::FRAC_1_SQRT_2];
    let across = [std::f64::consts::FRAC_1_SQRT_2, std::f64::consts::FRAC_1_SQRT_2];
    let at = |t: f64, side: f64| {
        let along = (t - 0.5) * len;
        let off = side * amp * (2.0 * std::f64::consts::PI * t).cos();
        [centre[0] + along * axis[0] + off * across[0], centre[1] + along * axis[1] + off * across[1]]
    };
    let mut shapes = Vec::new();
    for side in [1.0, -1.0] {
        for k in 0..STEPS {
            shapes.push(Shape::Line(at(k as f64 / STEPS as f64, side), at((k + 1) as f64 / STEPS as f64, side), pen));
        }
    }
    for t in RUNGS {
        shapes.push(Shape::Line(at(t, 0.8), at(t, -0.8), pen * 0.8));
    }
    Icon::new(shapes, rgb)
}

pub fn volcano(centre: [f64; 2], size: f64, cone: Rgb, fire: Rgb) -> Vec<Icon> {
    let p = |x: f64, y: f64| [centre[0] + x * size, centre[1] + y * size];
    let mountain = Shape::Polygon(vec![p(-0.48, 0.44), p(-0.14, 0.02), p(-0.05, 0.09), p(0.05, 0.09), p(0.14, 0.02), p(0.48, 0.44)]);
    let balls = [(-0.02, -0.14, 0.05), (0.1, -0.27, 0.07), (0.0, -0.41, 0.08)];
    vec![
        Icon::new(vec![mountain], cone),
        Icon::new(balls.iter().map(|&(x, y, r)| Shape::Disc(p(x, y), (r * size).max(0.7))).collect(), fire),
    ]
}

pub fn body(centre: [f64; 2], ring_r: f64, rgb: Rgb, signal: bool) -> Vec<Icon> {
    let scale = |r: f64| ring_r * r / FSS_ICON_RING_R;
    let halo = Icon { alpha: FSS_ICON_RING_ALPHA, ..Icon::new(vec![Shape::Ring(centre, scale(FSS_ICON_HALO_R), scale(FSS_ICON_RING_W).max(1.0))], rgb) };
    let disc = scale(FSS_ICON_DISC);
    let inner = if signal {
        let pen = (ring_r / SIGNAL_PEN_DIV as f64).max(1.0);
        let bars = [(-disc * 2.0 / 3.0, disc * 0.45), (0.0, disc * 0.8), (disc * 2.0 / 3.0, disc * 0.45)];
        bars.iter().map(|&(dx, h)| Shape::Line([centre[0] + dx, centre[1] - h], [centre[0] + dx, centre[1] + h], pen)).collect()
    } else {
        vec![Shape::Disc(centre, disc)]
    };
    vec![halo, Icon::new(inner, rgb)]
}

pub fn ring(centre: [f64; 2], r: f64, width: f64, rgb: Rgb) -> Icon {
    Icon::new(vec![Shape::Ring(centre, r, width)], rgb)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::theme::*;

    #[test]
    fn a_round_stroke_covers_its_inside_fully_and_its_edge_partly() {
        let icon = Icon::new(vec![Shape::Disc([5.0, 5.0], 3.0)], Rgb(255, 255, 255));
        assert_eq!(icon.coverage(4, 4), 1.0);
        assert_eq!(icon.coverage(0, 0), 0.0);
        let edge = icon.coverage(7, 4);
        assert!(edge > 0.0 && edge < 1.0, "{edge}");
    }

    #[test]
    fn a_polygon_holds_its_inside_only() {
        let icon = Icon::new(vec![Shape::Polygon(vec![[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])], Rgb(1, 1, 1));
        assert_eq!(icon.coverage(1, 1), 1.0);
        assert_eq!(icon.coverage(5, 1), 0.0);
    }

    #[test]
    fn painting_blends_into_premultiplied_pixels() {
        let icon = Icon::new(vec![Shape::Disc([1.0, 1.0], 5.0)], Rgb(255, 0, 0));
        let mut pixels = vec![0u32; 4];
        icon.paint(&mut pixels, 2, 2, 255);
        assert!(pixels.iter().all(|p| *p == 0xffff_0000));
        let faint = Icon { alpha: 0.5, ..icon };
        let mut pixels = vec![0u32; 4];
        faint.paint(&mut pixels, 2, 2, 255);
        assert!(pixels.iter().all(|p| *p == 0x8080_0000));
    }

    #[test]
    #[ignore]
    fn preview_icons() {
        let out = std::env::var("ICON_PREVIEW").expect("ICON_PREVIEW=<png path>");
        let zoom: i32 = std::env::var("ICON_ZOOM").ok().and_then(|z| z.parse().ok()).unwrap_or(8);
        let sizes = [19.0, 48.0];
        let cell = 60;
        let draw: Vec<Box<dyn Fn([f64; 2], f64) -> Vec<Icon>>> = vec![
            Box::new(|c, s| vec![dna(c, s, EXO_DNA)]),
            Box::new(|c, s| volcano(c, s, GEO_CONE, GEO_VOLCANO)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_ROCK, false)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_ICE, false)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_GAS, false)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_EARTH, false)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_ICE, true)),
        ];
        let (w, h) = (cell * draw.len() as i32, cell * sizes.len() as i32);
        let mut pixels = vec![0xff05_060au32; (w * h) as usize];
        for (row, s) in sizes.iter().enumerate() {
            for (col, f) in draw.iter().enumerate() {
                let c = [(col as i32 * cell + cell / 2) as f64, (row as i32 * cell + cell / 2) as f64];
                for icon in f(c, *s) {
                    icon.paint(&mut pixels, w, h, 217);
                }
            }
        }
        let (zw, zh) = (w * zoom, h * zoom);
        let mut rgb = Vec::with_capacity((zw * zh * 3) as usize);
        for y in 0..zh {
            for x in 0..zw {
                let p = pixels[((y / zoom) * w + x / zoom) as usize];
                rgb.extend([(p >> 16) as u8, (p >> 8) as u8, p as u8]);
            }
        }
        let file = std::fs::File::create(out).unwrap();
        let mut enc = png::Encoder::new(std::io::BufWriter::new(file), zw as u32, zh as u32);
        enc.set_color(png::ColorType::Rgb);
        enc.set_depth(png::BitDepth::Eight);
        enc.write_header().unwrap().write_image_data(&rgb).unwrap();
    }
}
