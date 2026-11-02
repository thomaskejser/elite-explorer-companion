use windows::Win32::Foundation::{POINT, RECT};
use windows::Win32::Graphics::Gdi::{
    BI_RGB, BITMAPINFO, BITMAPINFOHEADER, BitBlt, ClientToScreen, CreateCompatibleBitmap, CreateCompatibleDC,
    DIB_RGB_COLORS, DeleteDC, DeleteObject, GetDC, GetDIBits, ReleaseDC, SRCCOPY, SelectObject,
};
use windows::Win32::UI::WindowsAndMessaging::{FindWindowW, GetClientRect, GetForegroundWindow, GetSystemMetrics, SM_CYSCREEN};
use windows::core::w;

use crate::fss::Frame;

pub fn game_height() -> Option<i32> {
    let game = unsafe { FindWindowW(None, w!("Elite - Dangerous (CLIENT)")) }.ok()?;
    let mut client = RECT::default();
    unsafe { GetClientRect(game, &mut client) }.ok()?;
    Some(client.bottom - client.top).filter(|h| *h > 0)
}

pub fn screen_height() -> i32 {
    unsafe { GetSystemMetrics(SM_CYSCREEN) }
}

pub fn grab_game() -> Result<(Frame, (i32, i32)), String> {
    let game = unsafe { FindWindowW(None, w!("Elite - Dangerous (CLIENT)")) }.map_err(|_| "the game window is not open")?;
    if unsafe { GetForegroundWindow() } != game {
        return Err("the game is not in the foreground".into());
    }
    let mut client = RECT::default();
    let mut origin = POINT::default();
    unsafe {
        GetClientRect(game, &mut client).map_err(|e| e.to_string())?;
        if !ClientToScreen(game, &mut origin).as_bool() {
            return Err("cannot place the game window on screen".into());
        }
    }
    let (w, h) = (client.right - client.left, client.bottom - client.top);
    if w <= 0 || h <= 0 {
        return Err("the game window has no area".into());
    }
    let mut bgra = vec![0u8; w as usize * h as usize * 4];
    let copied = unsafe {
        let screen = GetDC(None);
        let mem = CreateCompatibleDC(Some(screen));
        let bitmap = CreateCompatibleBitmap(screen, w, h);
        let old = SelectObject(mem, bitmap.into());
        let blitted = BitBlt(mem, 0, 0, w, h, Some(screen), origin.x, origin.y, SRCCOPY).is_ok();
        SelectObject(mem, old);
        let mut info = BITMAPINFO {
            bmiHeader: BITMAPINFOHEADER {
                biSize: size_of::<BITMAPINFOHEADER>() as u32,
                biWidth: w,
                biHeight: -h,
                biPlanes: 1,
                biBitCount: 32,
                biCompression: BI_RGB.0,
                ..Default::default()
            },
            ..Default::default()
        };
        let lines = GetDIBits(mem, bitmap, 0, h as u32, Some(bgra.as_mut_ptr().cast()), &mut info, DIB_RGB_COLORS);
        let _ = DeleteObject(bitmap.into());
        let _ = DeleteDC(mem);
        ReleaseDC(None, screen);
        blitted && lines == h
    };
    if !copied {
        return Err("the screen copy failed".into());
    }
    let rgb = bgra.as_chunks::<4>().0.iter().flat_map(|p| [p[2], p[1], p[0]]).collect();
    Ok((Frame { width: w as usize, height: h as usize, rgb }, (origin.x, origin.y)))
}
