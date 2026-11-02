use std::sync::atomic::{AtomicBool, Ordering};

static ON: AtomicBool = AtomicBool::new(false);

pub fn enable(on: bool) {
    ON.store(on, Ordering::Relaxed);
}

pub fn enabled() -> bool {
    ON.load(Ordering::Relaxed)
}

pub enum V {
    None,
    Int(i64),
    Float(f64),
    Bool(bool),
    Text(String),
}

impl From<i64> for V {
    fn from(v: i64) -> V {
        V::Int(v)
    }
}

impl From<usize> for V {
    fn from(v: usize) -> V {
        V::Int(v as i64)
    }
}

impl From<bool> for V {
    fn from(v: bool) -> V {
        V::Bool(v)
    }
}

impl From<f64> for V {
    fn from(v: f64) -> V {
        V::Float(v)
    }
}

impl From<&str> for V {
    fn from(v: &str) -> V {
        V::Text(v.to_string())
    }
}

impl From<String> for V {
    fn from(v: String) -> V {
        V::Text(v)
    }
}

impl<T: Into<V>> From<Option<T>> for V {
    fn from(v: Option<T>) -> V {
        v.map_or(V::None, Into::into)
    }
}

fn render(v: &V) -> String {
    match v {
        V::None => "-".into(),
        V::Int(i) => i.to_string(),
        V::Float(f) => format!("{f:.4}"),
        V::Bool(b) => if *b { "True".into() } else { "False".into() },
        V::Text(t) if t.contains(' ') => format!("'{t}'"),
        V::Text(t) => t.clone(),
    }
}

pub fn say(tag: &str, fields: Vec<(&str, V)>) {
    if !enabled() {
        return;
    }
    let body: Vec<String> = fields.iter().map(|(k, v)| format!("{k}={}", render(v))).collect();
    crate::log::say(&format!("TRACE {} {tag:<14} {}", crate::log::utc_hms(), body.join("  ")));
}

#[macro_export]
macro_rules! trace {
    ($tag:expr $(, $k:ident = $v:expr)* $(,)?) => {
        if $crate::trace::enabled() {
            $crate::trace::say(&$tag, vec![$((stringify!($k), $crate::trace::V::from($v))),*]);
        }
    };
}
