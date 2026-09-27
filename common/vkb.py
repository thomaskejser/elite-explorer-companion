import os
import struct
from textwrap import wrap

try:
    from pywinusb import hid
except ImportError:
    hid = None

VENDOR_ID = 0x231D
STECS = 0x0136
GUNFIGHTER = 0x0126

LED_REPORT_ID = 0x59
LED_REPORT_LEN = 129
LED_SET_OP_CODE = bytes.fromhex("59a50a")
REPORT_SLOTS = 30

COLOR1, COLOR2, COLOR1_d_2, COLOR2_d_1, COLOR1_p_2 = range(5)
OFF, CONSTANT, SLOW_BLINK, FAST_BLINK, ULTRA_BLINK = range(5)

LEDS = {STECS: (1, 2, 3), GUNFIGHTER: (1, 2, 3)}
DEAD_LED = 9


def to_vkb(color):
    c = str(color).lstrip("#")
    c = [x + x for x in c] if len(c) == 3 else wrap(c, 2)
    return [round(min(int(x, 16), 255) / 255.0 * 7) for x in c[:3]]


def from_vkb(color):
    return "#" + "".join("%02x" % round(min(int(c), 7) / 7.0 * 255) for c in color)


def config(led, color1="#000", color2="#000", color_mode=COLOR1, led_mode=CONSTANT):
    fields = [color_mode, led_mode, *to_vkb(color2)[::-1], *to_vkb(color1)[::-1]]
    packed = 0
    for f in fields:
        packed = (packed << 3) | (f & 7)
    return struct.pack(">B", led) + packed.to_bytes(3, "little")


def unpack(buf):
    packed = int.from_bytes(buf[1:], "little")
    clm, lem, b2, g2, r2, b1, g1, r1 = [(packed >> s) & 7 for s in range(21, -1, -3)]
    return dict(led=buf[0], color_mode=clm, led_mode=lem,
                color1=from_vkb([r1, g1, b1]), color2=from_vkb([r2, g2, b2]))


def checksum(slots, body):
    chk = 0xFFFF
    for i in range((slots + 1) * 3):
        chk ^= body[i]
        for _ in range(8):
            low = chk & 1
            chk >>= 1
            if low:
                chk ^= 0xA001
    return struct.pack("<H", chk)


class Throttle:
    """The VKB LEDs, or nothing at all when no VKB is plugged in.

    Every method is a no-op returning False if the device is absent, so callers never
    have to ask. `paint` takes one colour per LED, left to right.

    The device applies only the prefix of a report its checksum covers, so each report
    is padded out to full length with configs for an LED id the hardware does not
    drive. Overrides hold until the device is power-cycled: `off` darkens the LEDs
    rather than handing them back to the VKB profile.
    """

    def __init__(self, product_id=STECS):
        self.product_id = product_id
        self.leds = LEDS.get(product_id, (1, 2, 3))
        self._device = None
        self._looked = False

    @property
    def present(self):
        return self._find() is not None

    def paint(self, *colors, led_mode=CONSTANT):
        if len(colors) == 1 and isinstance(colors[0], (list, tuple)):
            colors = colors[0]
        return self.apply([config(led, color1=color, led_mode=led_mode)
                           for led, color in zip(self.leds, colors)
                           if color is not None])

    def show(self, states):
        """Set every LED at once from [(colour, led_mode)], None colour meaning dark.

        *** A REPORT REPLACES THE DEVICE'S WHOLE TABLE. *** An LED left out of one goes
        dark, so anything driving more than a single light has to send them together.
        """
        return self.apply([
            config(led, color1=color or "#000", led_mode=mode if color else OFF)
            for led, (color, mode) in zip(self.leds, states)])

    def blink(self, *colors, led_mode=SLOW_BLINK):
        return self.paint(*colors, led_mode=led_mode)

    def off(self):
        return self.apply([config(led, led_mode=OFF) for led in self.leds])

    def read(self):
        device = self._open()
        if device is None:
            return []
        try:
            data = bytes(self._report(device).get(False))
            if data[:3] != LED_SET_OP_CODE:
                return []
            count, data = data[7], data[8:]
            live = [unpack(data[i * 4:i * 4 + 4]) for i in range(count)]
            return [c for c in live if c["led"] in self.leds]
        except Exception:
            self._forget()
            return []
        finally:
            self._close(device)

    def apply(self, configs):
        if not configs:
            return False
        device = self._open()
        if device is None:
            return False
        try:
            configs = list(configs)
            configs += [config(DEAD_LED, led_mode=OFF)] * (REPORT_SLOTS - len(configs))
            body = os.urandom(2) + struct.pack(">B", len(configs)) + b"".join(configs)
            cmd = LED_SET_OP_CODE + checksum(len(configs), body) + body
            self._report(device).send(cmd + b"\x00" * (LED_REPORT_LEN - len(cmd)))
            return True
        except Exception:
            self._forget()
            return False
        finally:
            self._close(device)

    @staticmethod
    def _report(device):
        return [r for r in device.find_feature_reports()
                if r.report_id == LED_REPORT_ID][0]

    def _find(self):
        if self._looked:
            return self._device
        self._looked = True
        if hid is not None:
            try:
                self._device = next(
                    (d for d in hid.HidDeviceFilter(vendor_id=VENDOR_ID).get_devices()
                     if d.product_id == self.product_id), None)
            except Exception:
                self._device = None
        return self._device

    def _forget(self):
        self._device, self._looked = None, False

    def _open(self):
        device = self._find()
        if device is None:
            return None
        try:
            if not device.is_opened():
                device.open()
            return device
        except Exception:
            self._forget()
            return None

    @staticmethod
    def _close(device):
        try:
            device.close()
        except Exception:
            pass
