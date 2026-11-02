use crate::kdtree::KdTree;
use crate::route::dist;

pub const DEFAULT_OVER: u32 = 1;

pub fn corridor_radius(direct: f64, jump_ly: f64, over: u32) -> f64 {
    let a = ((direct / jump_ly).ceil() + over as f64) * jump_ly / 2.0;
    let c = direct / 2.0;
    (a * a - c * c).max(0.0).sqrt()
}

#[derive(Clone, Debug)]
pub struct ChainHop {
    pub hop: i64,
    pub system: String,
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

pub struct Corridor {
    pub names: Vec<String>,
    pts: Vec<[f64; 3]>,
    start: [f64; 3],
    goal: [f64; 3],
    jump_ly: f64,
    start_name: String,
    goal_name: String,
    direct: f64,
    floor: i64,
    to_goal: Vec<f64>,
    need: Vec<i64>,
    max_limit: i64,
    first: Vec<u32>,
}

impl Corridor {
    pub fn new(
        names: Vec<String>,
        pts: Vec<[f64; 3]>,
        (start, start_name): ([f64; 3], &str),
        (goal, goal_name): ([f64; 3], &str),
        jump_ly: f64,
        over: u32,
    ) -> Corridor {
        let direct = dist(&goal, &start);
        let floor = (direct / jump_ly).ceil() as i64;
        let to_goal: Vec<f64> = pts.iter().map(|p| dist(p, &goal)).collect();
        let need = to_goal.iter().map(|d| (d / jump_ly).ceil() as i64).collect();
        let first = (0..pts.len() as u32).filter(|&i| dist(&pts[i as usize], &start) <= jump_ly).collect();
        Corridor {
            names,
            pts,
            start,
            goal,
            jump_ly,
            start_name: start_name.to_string(),
            goal_name: goal_name.to_string(),
            direct,
            floor,
            to_goal,
            need,
            max_limit: floor + over as i64,
            first,
        }
    }

    fn reach(&self, limit: i64) -> Option<(u32, Vec<i64>)> {
        let n = self.pts.len();
        let mut level = vec![-1i64; n];
        let mut parent = vec![-1i64; n];
        let mut frontier: Vec<u32> =
            self.first.iter().copied().filter(|&i| self.need[i as usize] < limit).collect();
        for &i in &self.first {
            level[i as usize] = 1;
        }
        for k in 2..=limit {
            let mut done: Option<(u32, f64)> = None;
            for &i in &frontier {
                let d = self.to_goal[i as usize];
                if d <= self.jump_ly && done.is_none_or(|(_, b)| d < b) {
                    done = Some((i, d));
                }
            }
            if let Some((i, _)) = done {
                return Some((i, parent));
            }
            if frontier.is_empty() {
                return None;
            }
            let live: Vec<u32> =
                (0..n as u32).filter(|&i| level[i as usize] < 0 && k + self.need[i as usize] <= limit).collect();
            if live.is_empty() {
                return None;
            }
            let tree = KdTree::new(&self.pts, Some(&frontier));
            let near = nearest_parallel(&tree, &self.pts, &live, self.jump_ly);
            let mut fresh = Vec::new();
            for (j, hit) in near.into_iter().enumerate() {
                if let Some(p) = hit {
                    let i = live[j] as usize;
                    parent[i] = p as i64;
                    level[i] = k;
                    fresh.push(live[j]);
                }
            }
            if fresh.is_empty() {
                return None;
            }
            frontier = fresh;
        }
        None
    }

    pub fn solve(&self) -> Option<Vec<ChainHop>> {
        if self.direct <= self.jump_ly {
            return Some(self.hops(&[]));
        }
        for limit in self.floor..=self.max_limit {
            let Some((last, parent)) = self.reach(limit) else { continue };
            let mut chain = Vec::new();
            let mut node = last as i64;
            while node >= 0 {
                chain.push(node as usize);
                node = parent[node as usize];
            }
            chain.reverse();
            return Some(self.hops(&chain));
        }
        None
    }

    pub fn hops(&self, chain: &[usize]) -> Vec<ChainHop> {
        let mut out = Vec::with_capacity(chain.len() + 2);
        let mut push = |name: &str, p: [f64; 3]| {
            let hop = out.len() as i64;
            out.push(ChainHop { hop, system: name.to_string(), x: p[0], y: p[1], z: p[2] });
        };
        push(&self.start_name, self.start);
        for &i in chain {
            push(&self.names[i], self.pts[i]);
        }
        push(&self.goal_name, self.goal);
        out
    }
}

fn nearest_parallel(tree: &KdTree, pts: &[[f64; 3]], live: &[u32], r: f64) -> Vec<Option<u32>> {
    let threads = std::thread::available_parallelism().map_or(4, |n| n.get());
    let chunk = live.len().div_ceil(threads).max(1024);
    std::thread::scope(|s| {
        let handles: Vec<_> = live
            .chunks(chunk)
            .map(|part| {
                s.spawn(move || {
                    part.iter()
                        .map(|&i| tree.nearest_within(&pts[i as usize], r).map(|(p, _)| p))
                        .collect::<Vec<_>>()
                })
            })
            .collect();
        handles.into_iter().flat_map(|h| h.join().expect("nearest-neighbour worker panicked")).collect()
    })
}
