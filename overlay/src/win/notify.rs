use std::f64::consts::PI;
use std::sync::OnceLock;

use windows::Win32::Media::Audio::{PlaySoundW, SND_ASYNC, SND_MEMORY, SND_NODEFAULT};
use windows::core::PCWSTR;

const RATE: u32 = 44_100;

struct Sound {
    tones: &'static [(f64, f64, f64)],
    duration: f64,
    amplitude: f64,
    attack: f64,
    decay: f64,
}

const CONFIRM: Sound = Sound {
    tones: &[(880.0, 1.0, 0.0), (1320.0, 0.6, 0.03)],
    duration: 0.26,
    amplitude: 0.22,
    attack: 0.012,
    decay: 5.0,
};

const COPIED: Sound =
    Sound { tones: &[(880.0, 1.0, 0.0)], duration: 0.09, amplitude: 0.10, attack: 0.008, decay: 14.0 };

fn render(sound: &Sound) -> Vec<u8> {
    let total: f64 = sound.tones.iter().map(|t| t.1).sum();
    let frames = (RATE as f64 * sound.duration) as u32;
    let mut pcm = Vec::with_capacity(frames as usize * 2);
    for i in 0..frames {
        let t = i as f64 / RATE as f64;
        let env = (t / sound.attack).min(1.0) * (-sound.decay * t).exp();
        let mut s = 0.0;
        for &(hz, gain, delay) in sound.tones {
            let enter = if delay != 0.0 { (t / delay).min(1.0) } else { 1.0 };
            s += gain * (2.0 * PI * hz * t).sin() * enter;
        }
        let value = (s / total).clamp(-1.0, 1.0) * env * sound.amplitude;
        pcm.extend_from_slice(&((value * 32767.0) as i16).to_le_bytes());
    }
    let mut wav = Vec::with_capacity(44 + pcm.len());
    wav.extend_from_slice(b"RIFF");
    wav.extend_from_slice(&(36 + pcm.len() as u32).to_le_bytes());
    wav.extend_from_slice(b"WAVEfmt ");
    wav.extend_from_slice(&16u32.to_le_bytes());
    wav.extend_from_slice(&1u16.to_le_bytes());
    wav.extend_from_slice(&1u16.to_le_bytes());
    wav.extend_from_slice(&RATE.to_le_bytes());
    wav.extend_from_slice(&(RATE * 2).to_le_bytes());
    wav.extend_from_slice(&2u16.to_le_bytes());
    wav.extend_from_slice(&16u16.to_le_bytes());
    wav.extend_from_slice(b"data");
    wav.extend_from_slice(&(pcm.len() as u32).to_le_bytes());
    wav.extend_from_slice(&pcm);
    wav
}

fn play(cache: &'static OnceLock<Vec<u8>>, sound: &Sound, enabled: bool) -> bool {
    if !enabled {
        return false;
    }
    let wav = cache.get_or_init(|| render(sound));
    unsafe { PlaySoundW(PCWSTR(wav.as_ptr() as *const u16), None, SND_MEMORY | SND_ASYNC | SND_NODEFAULT).as_bool() }
}

pub fn chime(enabled: bool) -> bool {
    static WAV: OnceLock<Vec<u8>> = OnceLock::new();
    play(&WAV, &CONFIRM, enabled)
}

pub fn copied(enabled: bool) -> bool {
    static WAV: OnceLock<Vec<u8>> = OnceLock::new();
    play(&WAV, &COPIED, enabled)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sounds_are_byte_identical_to_python() {
        let digest = |s: &Sound| sha1_smol::Sha1::from(render(s)).digest().to_string();
        assert_eq!(render(&CONFIRM).len(), 22976);
        assert_eq!(digest(&CONFIRM), "6e70faaa36d7478fdab6adba1d41c58577bf3725");
        assert_eq!(render(&COPIED).len(), 7982);
        assert_eq!(digest(&COPIED), "2cce08134f5a85c6208942495459b679c2fda36d");
    }
}
