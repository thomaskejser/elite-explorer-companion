use std::time::{SystemTime, UNIX_EPOCH};

use windows::Win32::Devices::DeviceAndDriverInstallation::{
    DIGCF_DEVICEINTERFACE, DIGCF_PRESENT, SP_DEVICE_INTERFACE_DATA, SP_DEVICE_INTERFACE_DETAIL_DATA_W,
    SetupDiDestroyDeviceInfoList, SetupDiEnumDeviceInterfaces, SetupDiGetClassDevsW,
    SetupDiGetDeviceInterfaceDetailW,
};
use windows::Win32::Devices::HumanInterfaceDevice::{
    HIDD_ATTRIBUTES, HIDP_CAPS, HidD_FreePreparsedData, HidD_GetAttributes, HidD_GetHidGuid,
    HidD_GetPreparsedData, HidD_SetFeature, HidP_GetCaps, PHIDP_PREPARSED_DATA,
};
use windows::Win32::Foundation::{CloseHandle, GENERIC_READ, GENERIC_WRITE, HANDLE};
use windows::Win32::Storage::FileSystem::{
    CreateFileW, FILE_FLAGS_AND_ATTRIBUTES, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
};
use windows::core::PCWSTR;

const VENDOR_ID: u16 = 0x231D;
const STECS: u16 = 0x0136;

const LED_REPORT_LEN: usize = 129;
const LED_SET_OP_CODE: [u8; 3] = [0x59, 0xa5, 0x0a];
const REPORT_SLOTS: usize = 30;
const DEAD_LED: u8 = 9;

pub const OFF: u8 = 0;
pub const CONSTANT: u8 = 1;
pub const FAST_BLINK: u8 = 3;
const COLOR1: u8 = 0;

fn to_vkb(color: &str) -> [u8; 3] {
    let c = color.trim_start_matches('#');
    let expand: String = if c.len() == 3 { c.chars().flat_map(|x| [x, x]).collect() } else { c.to_string() };
    let mut out = [0u8; 3];
    for (i, slot) in out.iter_mut().enumerate() {
        let v = u32::from_str_radix(&expand[i * 2..i * 2 + 2], 16).unwrap_or(0).min(255);
        *slot = (v as f64 / 255.0 * 7.0).round() as u8;
    }
    out
}

pub fn from_vkb(color: [u8; 3]) -> String {
    let c = |v: u8| crate::theme::round_half_even(v.min(7) as f64 / 7.0 * 255.0) as u8;
    format!("#{:02x}{:02x}{:02x}", c(color[0]), c(color[1]), c(color[2]))
}

fn config(led: u8, color1: &str, led_mode: u8) -> [u8; 4] {
    let c1 = to_vkb(color1);
    let c2 = to_vkb("#000");
    let fields = [COLOR1, led_mode, c2[2], c2[1], c2[0], c1[2], c1[1], c1[0]];
    let mut packed: u32 = 0;
    for f in fields {
        packed = (packed << 3) | (f as u32 & 7);
    }
    let b = packed.to_le_bytes();
    [led, b[0], b[1], b[2]]
}

fn checksum(slots: usize, body: &[u8]) -> [u8; 2] {
    let mut chk: u16 = 0xFFFF;
    for &byte in &body[..(slots + 1) * 3] {
        chk ^= byte as u16;
        for _ in 0..8 {
            let low = chk & 1;
            chk >>= 1;
            if low != 0 {
                chk ^= 0xA001;
            }
        }
    }
    chk.to_le_bytes()
}

fn noise() -> [u8; 2] {
    let seed = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.subsec_nanos());
    [(seed >> 8) as u8, seed as u8]
}

fn report(states: &[(u8, Option<String>, u8)], noise: [u8; 2]) -> Vec<u8> {
    let mut configs: Vec<[u8; 4]> = states
        .iter()
        .map(|(led, color, mode)| match color {
            Some(c) => config(*led, c, *mode),
            None => config(*led, "#000", OFF),
        })
        .collect();
    while configs.len() < REPORT_SLOTS {
        configs.push(config(DEAD_LED, "#000", OFF));
    }
    let mut body = vec![noise[0], noise[1], configs.len() as u8];
    for c in &configs {
        body.extend_from_slice(c);
    }
    let mut cmd = LED_SET_OP_CODE.to_vec();
    cmd.extend_from_slice(&checksum(configs.len(), &body));
    cmd.extend_from_slice(&body);
    cmd.resize(LED_REPORT_LEN, 0);
    cmd
}

struct Wide(Vec<u16>);

pub struct Throttle {
    pub leds: [u8; 3],
    product_id: u16,
    path: Option<Wide>,
    looked: bool,
}

impl Throttle {
    pub fn new() -> Throttle {
        Throttle { leds: [1, 2, 3], product_id: STECS, path: None, looked: false }
    }

    pub fn present(&mut self) -> bool {
        self.find();
        self.path.is_some()
    }

    pub fn show(&mut self, states: &[(Option<String>, u8)]) -> bool {
        let full: Vec<(u8, Option<String>, u8)> =
            self.leds.iter().zip(states).map(|(led, (c, m))| (*led, c.clone(), *m)).collect();
        self.apply(&report(&full, noise()))
    }

    pub fn off(&mut self) -> bool {
        let full: Vec<(u8, Option<String>, u8)> = self.leds.iter().map(|l| (*l, None, OFF)).collect();
        self.apply(&report(&full, noise()))
    }

    fn apply(&mut self, cmd: &[u8]) -> bool {
        self.find();
        let Some(path) = &self.path else { return false };
        let ok = unsafe { send(&path.0, cmd) };
        if !ok {
            self.path = None;
            self.looked = false;
        }
        ok
    }

    fn find(&mut self) {
        if self.looked {
            return;
        }
        self.looked = true;
        self.path = unsafe { find_device(self.product_id) }.map(Wide);
    }
}

unsafe fn open(path: &[u16], access: u32) -> Option<HANDLE> {
    unsafe {
        CreateFileW(
            PCWSTR(path.as_ptr()),
            access,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAGS_AND_ATTRIBUTES(0),
            None,
        )
        .ok()
    }
}

unsafe fn send(path: &[u16], cmd: &[u8]) -> bool {
    unsafe {
        let Some(h) = open(path, GENERIC_READ.0 | GENERIC_WRITE.0).or_else(|| open(path, 0)) else {
            return false;
        };
        let ok = HidD_SetFeature(h, cmd.as_ptr() as *const _, cmd.len() as u32);
        let _ = CloseHandle(h);
        ok
    }
}

unsafe fn find_device(product_id: u16) -> Option<Vec<u16>> {
    unsafe {
        let guid = HidD_GetHidGuid();
        let set = SetupDiGetClassDevsW(Some(&guid), PCWSTR::null(), None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
            .ok()?;
        let mut found = None;
        let mut index = 0;
        loop {
            let mut iface = SP_DEVICE_INTERFACE_DATA {
                cbSize: std::mem::size_of::<SP_DEVICE_INTERFACE_DATA>() as u32,
                ..Default::default()
            };
            if SetupDiEnumDeviceInterfaces(set, None, &guid, index, &mut iface).is_err() {
                break;
            }
            index += 1;
            let mut needed = 0u32;
            let _ = SetupDiGetDeviceInterfaceDetailW(set, &iface, None, 0, Some(&mut needed), None);
            if needed == 0 {
                continue;
            }
            let mut buf = vec![0u64; (needed as usize).div_ceil(8)];
            let detail = buf.as_mut_ptr() as *mut SP_DEVICE_INTERFACE_DETAIL_DATA_W;
            (*detail).cbSize = std::mem::size_of::<SP_DEVICE_INTERFACE_DETAIL_DATA_W>() as u32;
            if SetupDiGetDeviceInterfaceDetailW(set, &iface, Some(detail), needed, None, None).is_err() {
                continue;
            }
            let start = std::ptr::addr_of!((*detail).DevicePath) as *const u16;
            let mut path = Vec::new();
            let mut i = 0;
            loop {
                let c = *start.add(i);
                path.push(c);
                if c == 0 {
                    break;
                }
                i += 1;
            }
            if matches_led_interface(&path, product_id) {
                found = Some(path);
                break;
            }
        }
        let _ = SetupDiDestroyDeviceInfoList(set);
        found
    }
}

unsafe fn matches_led_interface(path: &[u16], product_id: u16) -> bool {
    unsafe {
        let Some(h) = open(path, 0) else { return false };
        let mut attrs = HIDD_ATTRIBUTES { Size: std::mem::size_of::<HIDD_ATTRIBUTES>() as u32, ..Default::default() };
        let mut ok = HidD_GetAttributes(h, &mut attrs) && attrs.VendorID == VENDOR_ID && attrs.ProductID == product_id;
        if ok {
            let mut pre = PHIDP_PREPARSED_DATA::default();
            ok = HidD_GetPreparsedData(h, &mut pre);
            if ok {
                let mut caps = HIDP_CAPS::default();
                ok = HidP_GetCaps(pre, &mut caps).is_ok() && caps.FeatureReportByteLength as usize >= LED_REPORT_LEN;
                let _ = HidD_FreePreparsedData(pre);
            }
        }
        let _ = CloseHandle(h);
        ok
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn report_matches_the_python_wire_format() {
        let states = vec![(1, Some("#00ff00".to_string()), CONSTANT), (2, None, OFF), (3, Some("#0000ff".to_string()), FAST_BLINK)];
        let hex: String = report(&states, [0x12, 0x34]).iter().map(|b| format!("{b:02x}")).collect();
        let want = concat!(
            "59a50a392712341e013800040200000003c0010c0900000009000000090000000900000009000000",
            "09000000090000000900000009000000090000000900000009000000090000000900000009000000",
            "09000000090000000900000009000000090000000900000009000000090000000900000009000000",
            "090000000900000000",
        );
        assert_eq!(hex, want);
    }
}
