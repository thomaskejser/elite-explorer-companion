pub struct KdTree<'a> {
    pts: &'a [[f64; 3]],
    order: Vec<u32>,
    nodes: Vec<Node>,
    lo: [f64; 3],
    hi: [f64; 3],
}

struct Node {
    lo: u32,
    hi: u32,
    axis: u8,
    split: f64,
    left: u32,
    right: u32,
}

const LEAF: usize = 16;
const STACK: usize = 128;
const NONE: u32 = u32::MAX;

fn d2(a: &[f64; 3], b: &[f64; 3]) -> f64 {
    let dx = a[0] - b[0];
    let dy = a[1] - b[1];
    let dz = a[2] - b[2];
    dx * dx + dy * dy + dz * dz
}

impl<'a> KdTree<'a> {
    pub fn new(pts: &'a [[f64; 3]], subset: Option<&[u32]>) -> KdTree<'a> {
        let order: Vec<u32> = match subset {
            Some(s) => s.to_vec(),
            None => (0..pts.len() as u32).collect(),
        };
        let mut lo = [f64::INFINITY; 3];
        let mut hi = [f64::NEG_INFINITY; 3];
        for &i in &order {
            for a in 0..3 {
                lo[a] = lo[a].min(pts[i as usize][a]);
                hi[a] = hi[a].max(pts[i as usize][a]);
            }
        }
        let mut tree = KdTree { pts, order, nodes: Vec::new(), lo, hi };
        if !tree.order.is_empty() {
            let n = tree.order.len() as u32;
            tree.build(0, n);
        }
        tree
    }

    fn build(&mut self, lo: u32, hi: u32) -> u32 {
        let id = self.nodes.len() as u32;
        self.nodes.push(Node { lo, hi, axis: 0, split: 0.0, left: NONE, right: NONE });
        if (hi - lo) as usize <= LEAF {
            return id;
        }
        let slice = &mut self.order[lo as usize..hi as usize];
        let mut min = [f64::INFINITY; 3];
        let mut max = [f64::NEG_INFINITY; 3];
        for &i in slice.iter() {
            let p = &self.pts[i as usize];
            for a in 0..3 {
                min[a] = min[a].min(p[a]);
                max[a] = max[a].max(p[a]);
            }
        }
        let axis = (0..3).max_by(|&a, &b| (max[a] - min[a]).total_cmp(&(max[b] - min[b]))).unwrap();
        let mid = slice.len() / 2;
        let pts = self.pts;
        slice.select_nth_unstable_by(mid, |&a, &b| pts[a as usize][axis].total_cmp(&pts[b as usize][axis]));
        let split = pts[slice[mid] as usize][axis];
        let left = self.build(lo, lo + mid as u32);
        let right = self.build(lo + mid as u32, hi);
        let node = &mut self.nodes[id as usize];
        node.axis = axis as u8;
        node.split = split;
        node.left = left;
        node.right = right;
        id
    }

    pub fn within(&self, q: &[f64; 3], r: f64, out: &mut Vec<u32>) {
        if self.nodes.is_empty() {
            return;
        }
        let r2 = r * r;
        let mut stack = [0u32; STACK];
        let mut top = 1;
        while top > 0 {
            top -= 1;
            let id = stack[top];
            let node = &self.nodes[id as usize];
            if node.left == NONE {
                for &i in &self.order[node.lo as usize..node.hi as usize] {
                    if d2(&self.pts[i as usize], q) <= r2 {
                        out.push(i);
                    }
                }
                continue;
            }
            let diff = q[node.axis as usize] - node.split;
            if diff - r <= 0.0 {
                stack[top] = node.left;
                top += 1;
            }
            if diff + r >= 0.0 {
                stack[top] = node.right;
                top += 1;
            }
        }
    }

    fn outside(&self, q: &[f64; 3], r: f64) -> bool {
        (0..3).any(|a| q[a] < self.lo[a] - r || q[a] > self.hi[a] + r)
    }

    pub fn nearest_within(&self, q: &[f64; 3], r: f64) -> Option<(u32, f64)> {
        if self.nodes.is_empty() || self.outside(q, r) {
            return None;
        }
        let mut best: Option<(u32, f64)> = None;
        let mut best2 = r * r;
        let mut stack = [(0u32, 0.0f64); STACK];
        let mut top = 1;
        while top > 0 {
            top -= 1;
            let (id, bound) = stack[top];
            if bound > best2 {
                continue;
            }
            let node = &self.nodes[id as usize];
            if node.left == NONE {
                for &i in &self.order[node.lo as usize..node.hi as usize] {
                    let d = d2(&self.pts[i as usize], q);
                    if d <= best2 && best.is_none_or(|(_, b)| d < b) {
                        best2 = d;
                        best = Some((i, d));
                    }
                }
                continue;
            }
            let diff = q[node.axis as usize] - node.split;
            let (near, far) = if diff < 0.0 { (node.left, node.right) } else { (node.right, node.left) };
            stack[top] = (far, diff * diff);
            stack[top + 1] = (near, 0.0);
            top += 2;
        }
        best.map(|(i, d)| (i, d.sqrt()))
    }
}
