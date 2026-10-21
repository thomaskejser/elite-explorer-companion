use std::path::Path;
use std::sync::Mutex;

use windows::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Input::KeyboardAndMouse::{
    GetAsyncKeyState, VIRTUAL_KEY, VK_CONTROL, VK_ESCAPE, VK_LCONTROL, VK_LMENU, VK_LSHIFT, VK_LWIN, VK_MENU,
    VK_RCONTROL, VK_RMENU, VK_RSHIFT, VK_RWIN, VK_SHIFT,
};
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, HHOOK, KBDLLHOOKSTRUCT, SetWindowsHookExW, UnhookWindowsHookEx, WH_KEYBOARD_LL, WM_KEYDOWN,
    WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Action {
    NextTable,
    PrevTable,
    NextRow,
    PrevRow,
    MarkWrong,
    NeutronRoute,
    AliasRouted,
}

pub const BINDINGS: [(&str, Action); 7] = [
    ("page down", Action::NextTable),
    ("page up", Action::PrevTable),
    ("down", Action::NextRow),
    ("up", Action::PrevRow),
    ("shift+backspace", Action::MarkWrong),
    ("shift+n", Action::NeutronRoute),
    ("shift+a", Action::AliasRouted),
];

pub fn description(action: Action) -> &'static str {
    match action {
        Action::PrevTable => "previous table",
        Action::NextTable => "next table",
        Action::PrevRow => "previous row",
        Action::NextRow => "next row",
        Action::MarkWrong => "mark the selected row as not existing",
        Action::NeutronRoute => "neutron route to the selected row (again to clear)",
        Action::AliasRouted => "the selected row is the plotted route's destination, renamed",
    }
}

fn setting_key(action: Action) -> &'static str {
    match action {
        Action::NextTable => "next_table",
        Action::PrevTable => "previous_table",
        Action::NextRow => "next_row",
        Action::PrevRow => "previous_row",
        Action::MarkWrong => "mark_wrong",
        Action::NeutronRoute => "neutron_route",
        Action::AliasRouted => "alias_routed",
    }
}

fn index(action: Action) -> usize {
    BINDINGS.iter().position(|(_, a)| *a == action).expect("every action has a default binding")
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Key {
    Shift,
    Ctrl,
    Alt,
    Win,
    Vk(u16),
}

const MODIFIERS: [(Key, &str); 4] = [(Key::Shift, "shift"), (Key::Ctrl, "ctrl"), (Key::Alt, "alt"), (Key::Win, "win")];

const NAMED: [(u16, &str); 36] = [
    (0x08, "backspace"),
    (0x09, "tab"),
    (0x0D, "enter"),
    (0x13, "pause"),
    (0x14, "caps lock"),
    (0x1B, "escape"),
    (0x20, "space"),
    (0x21, "page up"),
    (0x22, "page down"),
    (0x23, "end"),
    (0x24, "home"),
    (0x25, "left"),
    (0x26, "up"),
    (0x27, "right"),
    (0x28, "down"),
    (0x2C, "print screen"),
    (0x2D, "insert"),
    (0x2E, "delete"),
    (0x6A, "num *"),
    (0x6B, "num +"),
    (0x6D, "num -"),
    (0x6E, "num ."),
    (0x6F, "num /"),
    (0x90, "num lock"),
    (0x91, "scroll lock"),
    (0xBA, ";"),
    (0xBB, "="),
    (0xBC, ","),
    (0xBD, "-"),
    (0xBE, "."),
    (0xBF, "/"),
    (0xC0, "`"),
    (0xDB, "["),
    (0xDC, "\\"),
    (0xDD, "]"),
    (0xDE, "'"),
];

fn key_name(key: Key) -> String {
    if let Some((_, name)) = MODIFIERS.iter().find(|(k, _)| *k == key) {
        return name.to_string();
    }
    let Key::Vk(vk) = key else { unreachable!() };
    if let Some((_, name)) = NAMED.iter().find(|(v, _)| *v == vk) {
        return name.to_string();
    }
    match vk {
        0x30..=0x39 | 0x41..=0x5A => ((vk as u8) as char).to_ascii_lowercase().to_string(),
        0x60..=0x69 => format!("num {}", vk - 0x60),
        0x70..=0x87 => format!("f{}", vk - 0x6F),
        _ => format!("vk {vk:#04x}"),
    }
}

fn parse_key(word: &str) -> Option<Key> {
    let word = word.trim().to_lowercase();
    if let Some((k, _)) = MODIFIERS.iter().find(|(_, n)| *n == word) {
        return Some(*k);
    }
    if let Some((vk, _)) = NAMED.iter().find(|(_, n)| *n == word) {
        return Some(Key::Vk(*vk));
    }
    let b = word.as_bytes();
    if b.len() == 1 && (b[0].is_ascii_lowercase() || b[0].is_ascii_digit()) {
        return Some(Key::Vk(b[0].to_ascii_uppercase() as u16));
    }
    if let Some(n) = word.strip_prefix("num ").and_then(|n| n.parse::<u16>().ok()).filter(|n| *n <= 9) {
        return Some(Key::Vk(0x60 + n));
    }
    if let Some(n) = word.strip_prefix('f').and_then(|n| n.parse::<u16>().ok()).filter(|n| (1..=24).contains(n)) {
        return Some(Key::Vk(0x6F + n));
    }
    word.strip_prefix("vk ").and_then(|h| u16::from_str_radix(h.trim_start_matches("0x"), 16).ok()).map(Key::Vk)
}

fn chord_name(chord: &[Key]) -> String {
    let mut parts: Vec<String> =
        MODIFIERS.iter().filter(|(k, _)| chord.contains(k)).map(|(_, n)| n.to_string()).collect();
    parts.extend(chord.iter().filter(|k| matches!(k, Key::Vk(_))).map(|k| key_name(*k)));
    parts.join("+")
}

fn parse_chord(text: &str) -> Option<Vec<Key>> {
    let keys = text.split('+').map(parse_key).collect::<Option<Vec<Key>>>()?;
    let plain = keys.iter().filter(|k| matches!(k, Key::Vk(_))).count();
    (plain == 1).then_some(keys)
}

fn key_word(part: &str) -> String {
    match part {
        "page up" => "Pg Up".into(),
        "page down" => "Pg Down".into(),
        other => {
            let mut c = other.chars();
            c.next().map(|f| f.to_uppercase().collect::<String>() + c.as_str()).unwrap_or_default()
        }
    }
}

pub fn key_label(chord: &str) -> String {
    let words: Vec<String> = chord.split('+').map(key_word).collect();
    format!("[{}]", words.join("+"))
}

pub fn binding(action: Action) -> String {
    chord_name(&SLOTS.lock().unwrap().chords[index(action)])
}

#[derive(Clone, Debug, PartialEq)]
pub enum Rebound {
    Set { action: Action, chord: String, swapped: Option<Action> },
    Cancelled(Action),
}

struct Slots {
    pending: Option<Action>,
    wrong: bool,
    route: bool,
    alias: bool,
    pressed: Vec<Key>,
    chords: [Vec<Key>; BINDINGS.len()],
    capture: Option<Action>,
    rebound: Option<Rebound>,
}

impl Slots {
    const fn new() -> Slots {
        Slots {
            pending: None,
            wrong: false,
            route: false,
            alias: false,
            pressed: Vec::new(),
            chords: [const { Vec::new() }; BINDINGS.len()],
            capture: None,
            rebound: None,
        }
    }

    fn set_defaults(&mut self) {
        for (i, (text, _)) in BINDINGS.iter().enumerate() {
            self.chords[i] = parse_chord(text).expect("a default binding that does not parse");
        }
    }

    fn assign(&mut self, action: Action, chord: Vec<Key>) -> Option<Action> {
        let i = index(action);
        let same = |c: &Vec<Key>| c.len() == chord.len() && c.iter().all(|k| chord.contains(k));
        let other = (0..self.chords.len()).find(|&j| j != i && same(&self.chords[j]));
        if let Some(j) = other {
            self.chords[j] = std::mem::take(&mut self.chords[i]);
        }
        self.chords[i] = chord;
        other.map(|j| BINDINGS[j].1)
    }
}

static SLOTS: Mutex<Slots> = Mutex::new(Slots::new());
static HOOK: Mutex<isize> = Mutex::new(0);

fn normalise(vk: u16) -> Key {
    let v = VIRTUAL_KEY(vk);
    if v == VK_LSHIFT || v == VK_RSHIFT || v == VK_SHIFT {
        Key::Shift
    } else if v == VK_LCONTROL || v == VK_RCONTROL || v == VK_CONTROL {
        Key::Ctrl
    } else if v == VK_LMENU || v == VK_RMENU || v == VK_MENU {
        Key::Alt
    } else if v == VK_LWIN || v == VK_RWIN {
        Key::Win
    } else {
        Key::Vk(vk)
    }
}

fn still_down(k: Key) -> bool {
    let vk = match k {
        Key::Shift => VK_SHIFT,
        Key::Ctrl => VK_CONTROL,
        Key::Alt => VK_MENU,
        Key::Win => return unsafe { GetAsyncKeyState(VK_LWIN.0 as i32) < 0 || GetAsyncKeyState(VK_RWIN.0 as i32) < 0 },
        Key::Vk(v) => VIRTUAL_KEY(v),
    };
    unsafe { GetAsyncKeyState(vk.0 as i32) < 0 }
}

fn on_key(vk: u16, down: bool) {
    record(&mut SLOTS.lock().unwrap(), normalise(vk), down, still_down);
}

fn record(s: &mut Slots, key: Key, down: bool, held: fn(Key) -> bool) {
    if !down {
        s.pressed.retain(|k| *k != key);
        return;
    }
    s.pressed.retain(|k| *k == key || held(*k));
    if !s.pressed.contains(&key) {
        s.pressed.push(key);
    }
    if let Some(action) = s.capture {
        if !matches!(key, Key::Vk(_)) {
            return;
        }
        s.capture = None;
        let alone = s.pressed.len() == 1;
        s.rebound = Some(if key == Key::Vk(VK_ESCAPE.0) && alone {
            Rebound::Cancelled(action)
        } else {
            let chord = s.pressed.clone();
            let name = chord_name(&chord);
            let swapped = s.assign(action, chord);
            Rebound::Set { action, chord: name, swapped }
        });
        return;
    }
    let fired = (0..BINDINGS.len()).find(|&i| {
        let c = &s.chords[i];
        !c.is_empty() && c.len() == s.pressed.len() && c.iter().all(|k| s.pressed.contains(k))
    });
    match fired.map(|i| BINDINGS[i].1) {
        Some(Action::MarkWrong) => s.wrong = true,
        Some(Action::NeutronRoute) => s.route = true,
        Some(Action::AliasRouted) => s.alias = true,
        Some(a) => s.pending = Some(a),
        None => {}
    }
}

pub fn load_bindings(path: &Path) -> Vec<String> {
    let mut s = SLOTS.lock().unwrap();
    s.set_defaults();
    let Ok(text) = std::fs::read_to_string(path) else { return Vec::new() };
    let saved: serde_json::Value = match serde_json::from_str(&text) {
        Ok(v) => v,
        Err(e) => return vec![format!("{} is not valid JSON ({e}); using the default keys", path.display())],
    };
    let mut warnings = Vec::new();
    for (_, action) in BINDINGS {
        let Some(value) = saved.get(setting_key(action)) else { continue };
        match value.as_str().and_then(parse_chord) {
            Some(chord) => s.chords[index(action)] = chord,
            None => warnings.push(format!(
                "{}: {} = {value} is not a key this overlay knows; kept {}",
                path.display(),
                setting_key(action),
                chord_name(&s.chords[index(action)])
            )),
        }
    }
    warnings
}

pub fn save_bindings(path: &Path) -> std::io::Result<()> {
    let s = SLOTS.lock().unwrap();
    let map: serde_json::Map<String, serde_json::Value> = BINDINGS
        .iter()
        .enumerate()
        .map(|(i, (_, a))| (setting_key(*a).to_string(), serde_json::Value::String(chord_name(&s.chords[i]))))
        .collect();
    drop(s);
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    std::fs::write(path, serde_json::to_string_pretty(&serde_json::Value::Object(map))? + "\n")
}

pub fn begin_capture(action: Action) {
    let mut s = SLOTS.lock().unwrap();
    s.capture = Some(action);
    s.rebound = None;
}

pub fn cancel_capture() -> bool {
    SLOTS.lock().unwrap().capture.take().is_some()
}

pub fn capturing() -> Option<Action> {
    SLOTS.lock().unwrap().capture
}

pub fn take_rebound() -> Option<Rebound> {
    SLOTS.lock().unwrap().rebound.take()
}

unsafe extern "system" fn hook_proc(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 {
        let info = unsafe { &*(lparam.0 as *const KBDLLHOOKSTRUCT) };
        let msg = wparam.0 as u32;
        if msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN {
            on_key(info.vkCode as u16, true);
        } else if msg == WM_KEYUP || msg == WM_SYSKEYUP {
            on_key(info.vkCode as u16, false);
        }
    }
    unsafe { CallNextHookEx(None, code, wparam, lparam) }
}

pub fn register() -> Result<(), String> {
    unsafe {
        let module = GetModuleHandleW(None).map_err(|e| e.to_string())?;
        let hook = SetWindowsHookExW(WH_KEYBOARD_LL, Some(hook_proc), Some(module.into()), 0)
            .map_err(|e| e.to_string())?;
        *HOOK.lock().unwrap() = hook.0 as isize;
    }
    Ok(())
}

pub fn unregister() {
    let mut h = HOOK.lock().unwrap();
    if *h != 0 {
        unsafe {
            let _ = UnhookWindowsHookEx(HHOOK(*h as *mut _));
        }
        *h = 0;
    }
}

pub fn take() -> Option<Action> {
    SLOTS.lock().unwrap().pending.take()
}

pub fn take_wrong() -> bool {
    std::mem::take(&mut SLOTS.lock().unwrap().wrong)
}

pub fn take_route() -> bool {
    std::mem::take(&mut SLOTS.lock().unwrap().route)
}

pub fn take_alias() -> bool {
    std::mem::take(&mut SLOTS.lock().unwrap().alias)
}

#[cfg(test)]
mod tests {
    use super::*;
    use windows::Win32::UI::Input::KeyboardAndMouse::{VK_BACK, VK_DOWN, VK_F5, VK_NEXT, VK_PRIOR, VK_UP};

    fn slots() -> Slots {
        let mut s = Slots::new();
        s.set_defaults();
        s
    }

    fn held(_: Key) -> bool {
        true
    }

    fn press(s: &mut Slots, vk: u16) {
        record(s, normalise(vk), true, held);
    }

    fn release(s: &mut Slots, vk: u16) {
        record(s, normalise(vk), false, held);
    }

    #[test]
    fn a_bare_arrow_moves_and_a_chord_does_not() {
        let mut s = slots();
        press(&mut s, VK_DOWN.0);
        assert_eq!(s.pending.take(), Some(Action::NextRow));
        release(&mut s, VK_DOWN.0);
        press(&mut s, VK_LSHIFT.0);
        press(&mut s, VK_DOWN.0);
        assert_eq!(s.pending, None);
    }

    #[test]
    fn shift_chords_get_their_own_slots() {
        let mut s = slots();
        press(&mut s, VK_RSHIFT.0);
        press(&mut s, b'N' as u16);
        assert!(s.route);
        release(&mut s, b'N' as u16);
        press(&mut s, VK_BACK.0);
        assert!(s.wrong);
        release(&mut s, VK_BACK.0);
        press(&mut s, b'A' as u16);
        assert!(s.alias);
        assert_eq!(s.pending, None);
    }

    #[test]
    fn a_letter_alone_or_with_another_key_held_fires_nothing() {
        let mut s = slots();
        press(&mut s, b'N' as u16);
        assert!(!s.route);
        release(&mut s, b'N' as u16);
        press(&mut s, b'W' as u16);
        press(&mut s, VK_UP.0);
        assert_eq!(s.pending, None);
    }

    #[test]
    fn key_repeat_fires_again_and_last_press_wins() {
        let mut s = slots();
        press(&mut s, VK_NEXT.0);
        press(&mut s, VK_NEXT.0);
        assert_eq!(s.pending, Some(Action::NextTable));
        release(&mut s, VK_NEXT.0);
        press(&mut s, VK_PRIOR.0);
        assert_eq!(s.pending, Some(Action::PrevTable));
    }

    #[test]
    fn a_captured_key_rebinds_and_fires_nothing() {
        let mut s = slots();
        s.capture = Some(Action::NextRow);
        press(&mut s, VK_LSHIFT.0);
        press(&mut s, VK_F5.0);
        assert_eq!(s.pending, None);
        assert_eq!(s.rebound, Some(Rebound::Set { action: Action::NextRow, chord: "shift+f5".into(), swapped: None }));
        release(&mut s, VK_F5.0);
        release(&mut s, VK_LSHIFT.0);
        press(&mut s, VK_DOWN.0);
        assert_eq!(s.pending, None);
        release(&mut s, VK_DOWN.0);
        press(&mut s, VK_LSHIFT.0);
        press(&mut s, VK_F5.0);
        assert_eq!(s.pending, Some(Action::NextRow));
    }

    #[test]
    fn a_taken_key_swaps_with_its_owner() {
        let mut s = slots();
        s.capture = Some(Action::NextRow);
        press(&mut s, VK_UP.0);
        assert_eq!(
            s.rebound,
            Some(Rebound::Set { action: Action::NextRow, chord: "up".into(), swapped: Some(Action::PrevRow) })
        );
        assert_eq!(chord_name(&s.chords[index(Action::PrevRow)]), "down");
    }

    #[test]
    fn escape_alone_cancels_and_keeps_the_binding() {
        let mut s = slots();
        s.capture = Some(Action::NextTable);
        press(&mut s, VK_ESCAPE.0);
        assert_eq!(s.rebound, Some(Rebound::Cancelled(Action::NextTable)));
        assert_eq!(chord_name(&s.chords[index(Action::NextTable)]), "page down");
    }

    #[test]
    fn chords_round_trip_through_their_names() {
        for text in ["page down", "shift+backspace", "ctrl+alt+f12", "num 7", "shift+;", "win+x"] {
            assert_eq!(chord_name(&parse_chord(text).unwrap()), text);
        }
        assert!(parse_chord("shift").is_none());
        assert!(parse_chord("a+b").is_none());
        assert!(parse_chord("hyperspace").is_none());
    }

    #[test]
    fn labels_read_as_keycaps() {
        assert_eq!(key_label("page down"), "[Pg Down]");
        assert_eq!(key_label("shift+backspace"), "[Shift+Backspace]");
        assert_eq!(key_label("shift+n"), "[Shift+N]");
    }
}
