use std::cell::RefCell;
use std::rc::Rc;
use std::time::Instant;

struct State {
    totals: Vec<(&'static str, f64, u32)>,
    depth: u32,
}

#[derive(Clone)]
pub struct Phases {
    slow_ms: Option<f64>,
    prefix: &'static str,
    state: Rc<RefCell<State>>,
}

pub struct PhaseGuard {
    phases: Phases,
    name: &'static str,
    t0: Instant,
}

pub struct SpanGuard {
    phases: Phases,
    label: &'static str,
    t0: Instant,
    outer: bool,
}

impl Phases {
    pub fn new(slow_ms: i64, prefix: &'static str) -> Phases {
        Phases {
            slow_ms: (slow_ms >= 0).then_some(slow_ms as f64),
            prefix,
            state: Rc::new(RefCell::new(State { totals: Vec::new(), depth: 0 })),
        }
    }

    pub fn phase(&self, name: &'static str) -> PhaseGuard {
        PhaseGuard { phases: self.clone(), name, t0: Instant::now() }
    }

    pub fn span(&self, label: &'static str) -> SpanGuard {
        let mut s = self.state.borrow_mut();
        let outer = s.depth == 0;
        if outer {
            s.depth = 1;
            s.totals.clear();
        }
        SpanGuard { phases: self.clone(), label, t0: Instant::now(), outer }
    }

    fn report(&self, label: &str, total: f64) -> String {
        let s = self.state.borrow();
        let parts: Vec<String> = s
            .totals
            .iter()
            .map(|(name, secs, n)| {
                let ms = secs * 1000.0;
                if *n > 1 { format!("{name} {ms:.0} x{n}") } else { format!("{name} {ms:.0}") }
            })
            .collect();
        format!("{}SLOW {label} {total:.0} ms | {}", self.prefix, parts.join("  "))
    }
}

impl Drop for PhaseGuard {
    fn drop(&mut self) {
        if self.phases.slow_ms.is_none() {
            return;
        }
        let dt = self.t0.elapsed().as_secs_f64();
        let mut s = self.phases.state.borrow_mut();
        match s.totals.iter_mut().find(|(n, _, _)| *n == self.name) {
            Some(entry) => {
                entry.1 += dt;
                entry.2 += 1;
            }
            None => s.totals.push((self.name, dt, 1)),
        }
    }
}

impl Drop for SpanGuard {
    fn drop(&mut self) {
        if !self.outer {
            return;
        }
        self.phases.state.borrow_mut().depth = 0;
        let Some(slow) = self.phases.slow_ms else { return };
        let total = self.t0.elapsed().as_secs_f64() * 1000.0;
        if total >= slow {
            crate::log::say(&self.phases.report(self.label, total));
        }
    }
}
