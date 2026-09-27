"""The overlay's two sounds, synthesised, played without blocking the UI.

*** WHY THERE IS NO .WAV IN THE REPO. *** A sound here is eight lines of arithmetic and
a stdlib `wave` writer, so shipping one as bytes would add a binary blob to a repository
of text for no gain -- and a blob nobody can diff is exactly the thing that rots. Each
is written once into the user's temp directory on first use and reused thereafter, under
a name carrying a digest of the numbers that made it: change a tone or a decay and the
file name changes with it, so a cached wav can never go on playing the old sound.

*** IT MUST NOT BLOCK THE TK LOOP, AND THAT RULES OUT THE OBVIOUS CALL. ***
`winsound.Beep()` is synchronous: a 250 ms tone freezes the overlay for 250 ms, on the
same thread that is drawing the thing the sound is announcing. `PlaySound` with
SND_ASYNC hands the buffer to the OS mixer and returns immediately, which is the only
behaviour acceptable inside a HUD that repaints on every jump.

Non-Windows and any failure at all degrade to silence. A missing sound device, a locked
temp directory, an OS that has no `winsound` -- none of them is a reason for the overlay
to stop telling you about a black hole, so every path here swallows its exception and
returns False.
"""
import hashlib
import math
import pathlib
import struct
import tempfile
import wave
from typing import NamedTuple

try:                                                          # Windows only
    import winsound
except ImportError:                                           # pragma: no cover
    winsound = None

RATE = 44100


class Sound(NamedTuple):
    """One synthesised sound: the tones it stacks, and the envelope over all of them.

    Each tone is (hertz, gain, delay) -- the delay lets a tone enter after the one
    below it, which is what makes two notes read as one chime rather than as a chord.
    """
    name: str
    tones: tuple
    duration: float
    amplitude: float
    attack: float                # seconds to full volume; a hard edge is what makes a
                                 # beep harsh, so no sound here starts at full scale
    decay: float                 # exponential decay constant; higher falls away faster


# THE CONFIRM CHIME. A perfect fifth (E6 over A5) rather than an octave or a fourth: it
# reads as a chime rather than a doorbell. 260 ms total, under the time it takes to read
# the system name it accompanies, and peak amplitude 0.22 of full scale because this
# plays while the game is playing -- an alert that talks over the ship is one the
# commander turns off.
CONFIRM = Sound(name="confirm", tones=((880.0, 1.0, 0.0), (1320.0, 0.6, 0.03)),
                duration=0.26, amplitude=0.22, attack=0.012, decay=5.0)

# THE CLIPBOARD TICK, AND IT HAS TO BE THE GENTLEST THING HERE. Every cursor move copies,
# so this is by far the most frequent sound the overlay makes and the only one that can
# be heard several times a second. It is the chime's root note ALONE -- same voice, so
# the two belong to one instrument -- at under half its amplitude and a third of its
# length, which leaves it a soft tick rather than a second alert.
COPIED = Sound(name="copied", tones=((880.0, 1.0, 0.0),),
               duration=0.09, amplitude=0.10, attack=0.008, decay=14.0)


def _path(sound):
    """-> the temp file this exact sound belongs in. The digest is what makes it exact."""
    digest = hashlib.sha1(repr(tuple(sound)).encode()).hexdigest()[:8]
    return pathlib.Path(tempfile.gettempdir()) / f"ed_overlay_{sound.name}_{digest}.wav"


def _render(sound, path):
    """Write `sound` to `path`. Stacked sine tones, soft attack, exponential decay."""
    # Normalised by the gains that went in, so adding a tone cannot clip the sum.
    total = sum(gain for _hz, gain, _delay in sound.tones)
    out = bytearray()
    for i in range(int(RATE * sound.duration)):
        t = i / RATE
        # Attack ramps in, decay falls away; multiplying them gives a plucked shape with
        # no click at either end. A raw sine that starts at full amplitude pops.
        env = min(t / sound.attack, 1.0) * math.exp(-sound.decay * t)
        s = 0.0
        for hz, gain, delay in sound.tones:
            enter = min(t / delay, 1.0) if delay else 1.0
            s += gain * math.sin(2 * math.pi * hz * t) * enter
        value = max(-1.0, min(1.0, s / total)) * env * sound.amplitude
        out += struct.pack("<h", int(value * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(out))


def play(sound, enabled=True):
    """Play `sound`, asynchronously. Returns True if it was handed off.

    Silence is always an acceptable outcome: every sound here announces something the
    screen is already showing, so no failure is worth an exception reaching the caller.
    """
    if not enabled or winsound is None:
        return False
    try:
        path = _path(sound)
        if not path.exists() or path.stat().st_size == 0:
            _render(sound, path)
        winsound.PlaySound(str(path),
                           winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
        return True
    except Exception:                                          # noqa: BLE001
        return False


def chime(enabled=True):
    """The confirm chime: the game has just revealed a rare object."""
    return play(CONFIRM, enabled)


def copied(enabled=True):
    """The clipboard tick: a system name has just been handed to the clipboard."""
    return play(COPIED, enabled)
