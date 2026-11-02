use crate::kdtree::KdTree;

const MAX_VISITED: usize = 2_000_000;
pub const MAX_ROUTE_LY: f64 = 10_000.0;
const START_LEGS: f64 = 3.0;

pub fn dist(a: &[f64; 3], b: &[f64; 3]) -> f64 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

pub fn plan(
    xyz: &[[f64; 3]],
    start: &[f64; 3],
    dest: &[f64; 3],
    plain_range: f64,
    boosted_range: f64,
) -> Option<Vec<usize>> {
    let reach = plain_range * START_LEGS;
    if dist(dest, start) <= reach {
        return Some(Vec::new());
    }
    if xyz.is_empty() {
        return None;
    }
    let tree = KdTree::new(xyz, None);
    let mut parent: Vec<i64> = vec![-1; xyz.len()];
    let mut first = Vec::new();
    tree.within(start, reach, &mut first);
    if first.is_empty() {
        return None;
    }
    first.sort_unstable();
    for &i in &first {
        parent[i as usize] = -2;
    }
    let mut visited = first.len();
    let mut frontier = first;
    let mut hits = Vec::new();
    while !frontier.is_empty() {
        let mut best: Option<(u32, f64)> = None;
        for &i in &frontier {
            let d = dist(&xyz[i as usize], dest);
            if d <= boosted_range && best.is_none_or(|(_, b)| d < b) {
                best = Some((i, d));
            }
        }
        if let Some((last, _)) = best {
            let mut path = Vec::new();
            let mut node = last as i64;
            while node != -2 {
                path.push(node as usize);
                node = parent[node as usize];
            }
            path.reverse();
            return Some(path);
        }
        if visited > MAX_VISITED {
            return None;
        }
        let mut fresh: Vec<(u32, u32)> = Vec::new();
        let mut any = false;
        for &src in &frontier {
            hits.clear();
            tree.within(&xyz[src as usize], boosted_range, &mut hits);
            any |= !hits.is_empty();
            for &h in &hits {
                if parent[h as usize] == -1 {
                    fresh.push((h, src));
                }
            }
        }
        if !any || fresh.is_empty() {
            return None;
        }
        fresh.sort_by_key(|&(h, _)| h);
        fresh.dedup_by_key(|&mut (h, _)| h);
        for &(h, src) in &fresh {
            parent[h as usize] = src as i64;
        }
        frontier = fresh.into_iter().map(|(h, _)| h).collect();
        visited += frontier.len();
    }
    None
}
