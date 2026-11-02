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


fn arc(c: [f64; 2], r: f64, from: f64, to: f64, pen: f64) -> Vec<Shape> {
    const STEPS: usize = 16;
    let at = |t: f64| {
        let a = (from + (to - from) * t).to_radians();
        [c[0] + r * a.cos(), c[1] - r * a.sin()]
    };
    (0..STEPS).map(|k| Shape::Line(at(k as f64 / STEPS as f64), at((k + 1) as f64 / STEPS as f64), pen)).collect()
}

pub fn flag(centre: [f64; 2], size: f64, pole: Rgb, cloth: Rgb) -> Vec<Icon> {
    let p = |x: f64, y: f64| [centre[0] + x * size, centre[1] + y * size];
    let pen = (size / 10.0).max(1.0);
    vec![
        Icon::new(vec![Shape::Line(p(-0.22, 0.45), p(-0.22, -0.45), pen), Shape::Line(p(-0.4, 0.45), p(0.0, 0.45), pen)], pole),
        Icon::new(vec![Shape::Polygon(vec![p(-0.2, -0.45), p(0.42, -0.27), p(-0.2, -0.08)])], cloth),
    ]
}

pub fn genus(name: &str, centre: [f64; 2], size: f64, rgb: Rgb) -> Icon {
    let p = |x: f64, y: f64| [centre[0] + x * size, centre[1] + y * size];
    let pen = (size / 11.0).max(1.0);
    let line = |a: [f64; 2], b: [f64; 2]| Shape::Line(a, b, pen);
    let dot = |x: f64, y: f64, r: f64| Shape::Disc(p(x, y), r * size);
    let shapes: Vec<Shape> = match name {
        "Bacterium" => vec![dot(-0.2, 0.15, 0.13), dot(0.12, 0.2, 0.11), dot(0.0, -0.12, 0.14), dot(0.25, -0.18, 0.09), dot(-0.27, -0.2, 0.08)],
        "Fungoida" => {
            let mut v = vec![line(p(0.0, 0.42), p(0.0, -0.02))];
            v.push(Shape::Polygon((0..=12).map(|k| {
                let a = std::f64::consts::PI * k as f64 / 12.0;
                p(-0.4 * a.cos(), -0.02 - 0.34 * a.sin())
            }).collect()));
            v
        }
        "Stratum" => [-0.22, 0.02, 0.26]
            .iter()
            .flat_map(|&y| (0..4).map(move |k| (y, k)))
            .map(|(y, k)| {
                let x0 = -0.42 + k as f64 * 0.21;
                let dy = if k % 2 == 0 { -0.05 } else { 0.05 };
                line(p(x0, y + dy), p(x0 + 0.21, y - dy))
            })
            .collect(),
        "Tussock" => [-0.4, -0.2, 0.0, 0.2, 0.4].iter().map(|&x| line(p(0.0, 0.42), p(x, -0.42 + x.abs() * 0.5))).collect(),
        "Osseus" => vec![
            line(p(0.0, 0.42), p(0.0, -0.1)),
            line(p(0.0, 0.05), p(-0.3, -0.25)),
            line(p(0.0, -0.1), p(0.28, -0.38)),
            line(p(-0.3, -0.25), p(-0.36, -0.42)),
            line(p(-0.15, -0.1), p(-0.05, -0.38)),
        ],
        "Concha" => {
            let mut v = arc(p(0.0, 0.3), 0.42 * size, 0.0, 180.0, pen);
            v.push(line(p(-0.42, 0.3), p(0.42, 0.3)));
            v.extend([45.0f64, 90.0, 135.0].iter().map(|a| {
                let (c, s2) = (a.to_radians().cos(), a.to_radians().sin());
                line(p(0.0, 0.3), p(0.42 * c, 0.3 - 0.42 * s2))
            }));
            v
        }
        "Cactoida" => vec![
            line(p(0.0, 0.42), p(0.0, -0.42)),
            line(p(0.0, 0.08), p(-0.28, 0.08)),
            line(p(-0.28, 0.08), p(-0.28, -0.22)),
            line(p(0.0, -0.08), p(0.26, -0.08)),
            line(p(0.26, -0.08), p(0.26, -0.32)),
        ],
        "Frutexa" => vec![
            line(p(0.0, 0.42), p(0.0, -0.1)),
            line(p(0.0, 0.15), p(-0.25, -0.1)),
            line(p(0.0, 0.05), p(0.25, -0.15)),
            dot(0.0, -0.22, 0.12),
            dot(-0.28, -0.18, 0.1),
            dot(0.28, -0.24, 0.1),
        ],
        "Aleoida" => [-0.42, -0.2, 0.0, 0.2, 0.42]
            .iter()
            .map(|&x| Shape::Polygon(vec![p(x - 0.07, 0.42), p(x * 0.9, -0.42 + x.abs() * 0.6), p(x + 0.07, 0.42)]))
            .collect(),
        "Clypeus" => {
            let mut v = arc(p(0.0, 0.25), 0.4 * size, 0.0, 180.0, pen);
            v.push(line(p(-0.45, 0.25), p(0.45, 0.25)));
            v.push(dot(0.0, 0.05, 0.1));
            v
        }
        "Fonticulua" => {
            let mut v = vec![line(p(0.0, 0.42), p(0.0, -0.3))];
            v.extend(arc(p(-0.2, -0.05), 0.22 * size, 20.0, 160.0, pen));
            v.extend(arc(p(0.2, -0.05), 0.22 * size, 20.0, 160.0, pen));
            v
        }
        "Recepta" => vec![
            Shape::Polygon(vec![p(-0.38, -0.25), p(0.38, -0.25), p(0.18, 0.2), p(-0.18, 0.2)]),
            line(p(0.0, 0.2), p(0.0, 0.42)),
            line(p(-0.22, 0.42), p(0.22, 0.42)),
        ],
        "Tubus" => vec![
            line(p(-0.27, 0.42), p(-0.27, -0.1)),
            line(p(0.0, 0.42), p(0.0, -0.4)),
            line(p(0.27, 0.42), p(0.27, -0.22)),
            dot(-0.27, -0.12, 0.08),
            dot(0.0, -0.42, 0.08),
            dot(0.27, -0.24, 0.08),
        ],
        "Electricae" => vec![
            line(p(0.12, -0.45), p(-0.15, 0.0)),
            line(p(-0.15, 0.0), p(0.12, 0.0)),
            line(p(0.12, 0.0), p(-0.12, 0.45)),
        ],
        "Fumerola" => vec![
            Shape::Polygon(vec![p(-0.42, 0.42), p(-0.1, 0.05), p(0.1, 0.05), p(0.42, 0.42)]),
            dot(0.0, -0.12, 0.09),
            dot(0.08, -0.3, 0.07),
            dot(-0.06, -0.43, 0.06),
        ],
        "Brain Tree" => vec![line(p(0.0, 0.42), p(0.0, 0.0)), dot(0.0, -0.15, 0.27)],
        "Crystalline Shards" => vec![
            Shape::Polygon(vec![p(-0.2, 0.42), p(-0.32, 0.0), p(-0.2, -0.42), p(-0.08, 0.0)]),
            Shape::Polygon(vec![p(0.15, 0.42), p(0.03, 0.08), p(0.15, -0.25), p(0.27, 0.08)]),
        ],
        "Sinuous Tubers" => {
            let mut v = arc(p(0.0, -0.2), 0.2 * size, -90.0, 90.0, pen);
            v.extend(arc(p(0.0, 0.2), 0.2 * size, 90.0, 270.0, pen));
            v
        }
        "Bark Mound" => vec![Shape::Polygon(
            (0..=12)
                .map(|k| {
                    let a = std::f64::consts::PI * k as f64 / 12.0;
                    p(-0.45 * a.cos(), 0.3 - 0.4 * a.sin())
                })
                .collect(),
        )],
        "Anemone" => {
            let mut v = vec![dot(0.0, 0.15, 0.2)];
            v.extend([30.0f64, 70.0, 110.0, 150.0].iter().map(|a| {
                let (c, s2) = (a.to_radians().cos(), a.to_radians().sin());
                line(p(0.2 * c, 0.15 - 0.2 * s2), p(0.45 * c, 0.15 - 0.55 * s2))
            }));
            v
        }
        "Radicoida" => vec![
            line(p(0.0, -0.42), p(0.0, 0.1)),
            line(p(0.0, 0.1), p(-0.3, 0.42)),
            line(p(0.0, 0.1), p(0.3, 0.42)),
            line(p(0.0, 0.1), p(0.0, 0.42)),
        ],
        "Amphora Plant" => vec![Shape::Polygon(vec![
            p(-0.12, -0.42),
            p(0.12, -0.42),
            p(0.08, -0.25),
            p(0.32, 0.05),
            p(0.2, 0.42),
            p(-0.2, 0.42),
            p(-0.32, 0.05),
            p(-0.08, -0.25),
        ])],
        _ => return dna(centre, size, rgb),
    };
    Icon::new(shapes, rgb)
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

    const GENERA: [&str; 22] = [
        "Aleoida", "Amphora Plant", "Anemone", "Bacterium", "Bark Mound", "Brain Tree", "Cactoida", "Clypeus",
        "Concha", "Crystalline Shards", "Electricae", "Fonticulua", "Frutexa", "Fumerola", "Fungoida", "Osseus",
        "Radicoida", "Recepta", "Sinuous Tubers", "Stratum", "Tubus", "Tussock",
    ];

    #[test]
    #[ignore]
    fn preview_icons() {
        let out = std::env::var("ICON_PREVIEW").expect("ICON_PREVIEW=<png path>");
        let zoom: i32 = std::env::var("ICON_ZOOM").ok().and_then(|z| z.parse().ok()).unwrap_or(8);
        let sizes = [19.0, 48.0];
        let cell = 60;
        let mut draw: Vec<Box<dyn Fn([f64; 2], f64) -> Vec<Icon>>> = vec![
            Box::new(|c, s| flag(c, s, CLOCK_TEXT, FIRST_FOOTFALL)),
            Box::new(|c, s| vec![dna(c, s, EXO_DNA)]),
            Box::new(|c, s| volcano(c, s, GEO_CONE, GEO_VOLCANO)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_ROCK, false)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_ICE, false)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_GAS, false)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_EARTH, false)),
            Box::new(|c, s| body(c, s * 0.45, FSS_ICON_ICE, true)),
        ];
        draw.extend(GENERA.iter().map(|g| Box::new(move |c, s| vec![genus(g, c, s, genus_rgb(g))]) as Box<dyn Fn([f64; 2], f64) -> Vec<Icon>>));
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
