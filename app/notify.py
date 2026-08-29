"""The confirm chime. One sound, synthesised, played without blocking the UI.

*** WHY THERE IS NO .WAV IN THE REPO. *** The sound is eight lines of arithmetic and a
stdlib `wave` writer, so shipping it as bytes would add a binary blob to a repository of
text for no gain -- and a blob nobody can diff is exactly the thing that rots. It is
written once into the user's temp directory on first use and reused thereafter.

*** IT MUST NOT BLOCK THE TK LOOP, AND THAT RULES OUT THE OBVIOUS CALL. ***
`winsound.Beep()` is synchronous: a 250 ms tone freezes the overlay for 250 ms, on the
same thread that is drawing the confirmation the sound is announcing. `PlaySound` with
SND_ASYNC hands the buffer to the OS mixer and returns immediately, which is the only
behaviour acceptable inside a HUD that repaints on every jump.

Non-Windows and any failure at all degrade to silence. A missing sound device, a locked
temp directory, an OS that has no `winsound` -- none of them is a reason for the overlay
to stop telling you about a black hole, so every path here swallows its exception and
returns False.
"""
import math
import pathlib
import struct
import tempfile
import wave

try:                                                          # Windows only
    import winsound
except ImportError:                                           # pragma: no cover
    winsound = None

# SUBTLE, and these numbers are what make it so. A perfect fifth (E6 over A5) rather than
# an octave or a fourth: it reads as a chime rather than a doorbell. 260 ms total, which
# is under the time it takes to read the system name it accompanies. Peak amplitude 0.22
# of full scale, because this plays while the game is playing and an alert that talks over
# the ship is one the commander turns off.
RATE = 44100
DURATION = 0.26
TONES = (880.0, 1320.0)          # A5 and E6
AMPLITUDE = 0.22
ATTACK = 0.012                   # seconds to full volume; longer than a click, shorter
                                 # than a swell -- a hard edge is what makes a beep harsh
DECAY = 5.0                      # exponential decay constant; higher falls away faster

_PATH = pathlib.Path(tempfile.gettempdir()) / "ed_overlay_confirm.wav"


def _render(path):
    """Write the chime to `path`. Two sine tones, soft attack, exponential decay."""
    frames = int(RATE * DURATION)
    out = bytearray()
    for i in range(frames):
        t = i / RATE
        # Attack ramps in, decay falls away; multiplying them gives a plucked shape with
        # no click at either end. A raw sine that starts at full amplitude pops.
        env = min(t / ATTACK, 1.0) * math.exp(-DECAY * t)
        # The fifth enters a touch later and quieter, so the two are heard as one chime
        # rather than as a chord struck twice.
        s = math.sin(2 * math.pi * TONES[0] * t)
        s += 0.6 * math.sin(2 * math.pi * TONES[1] * t) * min(t / 0.03, 1.0)
        out += struct.pack("<h", int(max(-1.0, min(1.0, s / 1.6)) * env * AMPLITUDE
                                     * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(out))


def chime(enabled=True):
    """Play the confirm chime, asynchronously. Returns True if it was handed off.

    Silence is always an acceptable outcome: this announces something the screen is
    already showing, so no failure here is worth an exception reaching the caller.
    """
    if not enabled or winsound is None:
        return False
    try:
        if not _PATH.exists() or _PATH.stat().st_size == 0:
            _render(_PATH)
        winsound.PlaySound(str(_PATH),
                           winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
        return True
    except Exception:                                          # noqa: BLE001
        return False
