use std::sync::Mutex;

use windows::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::UI::Input::KeyboardAndMouse::{
    GetAsyncKeyState, VIRTUAL_KEY, VK_BACK, VK_CONTROL, VK_DOWN, VK_LCONTROL, VK_LMENU, VK_LSHIFT, VK_LWIN,
    VK_MENU, VK_NEXT, VK_PRIOR, VK_RCONTROL, VK_RMENU, VK_RSHIFT, VK_RWIN, VK_SHIFT, VK_UP,
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

fn label_of(action: Action) -> String {
    key_label(BINDINGS.iter().find(|(_, a)| *a == action).unwrap().0)
}

pub type Segment = (String, crate::theme::Role);

pub fn help_segments() -> Vec<Vec<Vec<Segment>>> {
    use crate::theme::Role::{Dim, Keycap};
    let pair = |a: Action, b: Action| format!("{} / {}", label_of(a), label_of(b));
    vec![
        vec![
            vec![(pair(Action::PrevTable, Action::NextTable), Keycap)],
            vec![("Table".into(), Dim)],
            vec![(label_of(Action::MarkWrong), Keycap)],
            vec![("No such system".into(), Dim)],
        ],
        vec![
            vec![(pair(Action::PrevRow, Action::NextRow), Keycap)],
            vec![("Row".into(), Dim)],
            vec![(label_of(Action::NeutronRoute), Keycap)],
            vec![("Neutron route".into(), Dim)],
        ],
        vec![
            vec![],
            vec![],
            vec![(label_of(Action::AliasRouted), Keycap)],
            vec![("Same system, renamed".into(), Dim)],
        ],
        vec![vec![("The highlighted row is copied".into(), Dim)], vec![], vec![], vec![]],
    ]
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Key {
    Shift,
    Ctrl,
    Alt,
    Win,
    Vk(u16),
}

struct Slots {
    pending: Option<Action>,
    wrong: bool,
    route: bool,
    alias: bool,
    pressed: Vec<Key>,
}

static SLOTS: Mutex<Slots> =
    Mutex::new(Slots { pending: None, wrong: false, route: false, alias: false, pressed: Vec::new() });
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

fn chord(action: Action) -> &'static [Key] {
    const PGDN: Key = Key::Vk(VK_NEXT.0);
    const PGUP: Key = Key::Vk(VK_PRIOR.0);
    const DOWN: Key = Key::Vk(VK_DOWN.0);
    const UP: Key = Key::Vk(VK_UP.0);
    match action {
        Action::NextTable => &[PGDN],
        Action::PrevTable => &[PGUP],
        Action::NextRow => &[DOWN],
        Action::PrevRow => &[UP],
        Action::MarkWrong => &[Key::Shift, Key::Vk(VK_BACK.0)],
        Action::NeutronRoute => &[Key::Shift, Key::Vk(b'N' as u16)],
        Action::AliasRouted => &[Key::Shift, Key::Vk(b'A' as u16)],
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
    let fired = BINDINGS.iter().map(|(_, a)| *a).find(|a| {
        let c = chord(*a);
        c.len() == s.pressed.len() && c.iter().all(|k| s.pressed.contains(k))
    });
    match fired {
        Some(Action::MarkWrong) => s.wrong = true,
        Some(Action::NeutronRoute) => s.route = true,
        Some(Action::AliasRouted) => s.alias = true,
        Some(a) => s.pending = Some(a),
        None => {}
    }
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

    fn slots() -> Slots {
        Slots { pending: None, wrong: false, route: false, alias: false, pressed: Vec::new() }
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
    fn labels_read_like_the_python_help_bar() {
        assert_eq!(key_label("page down"), "[Pg Down]");
        assert_eq!(key_label("shift+backspace"), "[Shift+Backspace]");
        assert_eq!(key_label("shift+n"), "[Shift+N]");
    }
}
