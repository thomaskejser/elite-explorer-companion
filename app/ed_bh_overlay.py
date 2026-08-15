#!/usr/bin/env python3
"""Transparent, always-on-top ROUTE overlay for the BH/WR router, with global hotkeys.

Draws the current target list on top of Elite Dangerous. On every jump it recollects
the unvisited black-hole / Wolf-Rayet candidates within --radius (default 1000 ly),
takes the nearest --topn (default 12) and shows them BEST ODDS FIRST -- ties going to
predicted systems, then to the nearer one.
`--sort route` instead solves the shortest path through them and shows leg/cumulative
distance, which is the older behaviour.

The clipboard is never written to on its own. Copying is always something you did:
a hotkey or a [copy] button. The route re-solves on every jump, so an automatic copy
would overwrite whatever you had there at a moment you did not choose.

If fewer than --topn targets are in radius the list is extended with the nearest ones
beyond it, so you always get a full set; extended entries are marked `+` and are ranked
as their own block, so `+` keeps meaning "outside your radius".

Systems you have visited (per your journals, plus a persistent store) never appear.

Global hotkeys (work even while the game is focused):
  F1 .. F12                 -> copy waypoint 1..12  (--fn-prefix adds a modifier)
  <prefix>+1 .. <prefix>+9  -> copy waypoint 1..9   (fallback; --hotkey-prefix)
  <prefix>+0                -> copy waypoint 10
  alt+F1 .. alt+F12         -> copy confirmed-BH/WR find 1..12
  ctrl+F1 .. ctrl+F3        -> copy the best system in the richest adjacent SECTOR 1..3
  alt+P                     -> toggle PREDICTED ONLY mode
  alt+N                     -> copy the best neutron star toward the F1 target
  alt+U                     -> copy the nearest DSSA carrier's SYSTEM
(paste into the in-game galaxy-map search). --interactive also gives [copy] buttons.
The alt keys are actions rather than waypoints, so they carry their own modifier
(--action-prefix). Bare F10 is Elite's own screenshot key and F12 is Steam's, so if
either matters to you pass --fn-prefix ctrl+alt (or --suppress to keep the press from
reaching the game).

NOTE: screen overlay only -- Elite has NO API to place markers on the in-game map.
Run Elite in Borderless or Windowed mode; overlays cannot draw over exclusive fullscreen.

Usage:
  python ed_bh_overlay.py                          # click-through HUD + hotkeys
  python ed_bh_overlay.py --interactive            # + clickable [copy] buttons / draggable
  python ed_bh_overlay.py --radius 2000 --topn 10
  python ed_bh_overlay.py --hotkey-prefix shift    # SHIFT+digit (may clash w/ game binds)
  python ed_bh_overlay.py --x 30 --y 60 --pos X Y Z

Needs: python + duckdb + numpy + tkinter (+ `keyboard` for hotkeys).
"""
import tkinter as tk
import argparse, sys, os, json, pathlib, time
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ed_router as core
try:
    import keyboard
except Exception:
    keyboard = None

KEY = "#010101"
FG, HEAD, DIM, OK, WARN = "#39ff14", "#8fd0ff", "#aaaaaa", "#ffd700", "#ff9955"
# Elite Dangerous HUD palette: amber line-work, hostile red for destructive actions.
ED_AMBER, ED_AMBER_HOT = "#ff7100", "#ffb000"
ED_RED, ED_RED_HOT = "#d63a1e", "#ff6a4a"
CONFIRM = "#ffffff"      # arrival star confirmed to be the hunted type

# F1..F12 -> waypoints 1..12. Function keys are the primary binding because there are
# exactly twelve of them and they need no modifier, so one keypress copies a waypoint;
# --topn defaults to 12 to fill them. The prefix+digit hotkeys still work as a fallback
# (see _register_hotkeys) but only reach waypoints 1-10.
HOTKEYS = [f"F{i}" for i in range(1, 13)]


class Overlay:
    def __init__(self, a):
        self.a = a
        self.items = []          # list of dicts, one per displayed waypoint
        self.header = ""
        self.found = []
        self.found_total = 0
        self._alert_line = ""    # sticks until the next find; the sound is transient
        # Catalogued points of interest (phenomena, green giants) share the candidate
        # search radius unless overridden, so one --radius governs everything the HUD
        # is willing to route to.
        self.poi_radius = a.nsp_radius if a.nsp_radius is not None else a.radius
        self._rate_countdown = 0     # 0 = recount on the next clock tick
        self.session_visits = 0
        # Notable stellar phenomena in the system you are STANDING IN -- a different
        # concern from the catalogue above, and keyed by the journal's SystemAddress so
        # a re-emission burst about somewhere else cannot leak in. `_nsp_burst` counts
        # signals per timestamp: the game re-sends the whole list at once, so repeats
        # across bursts are the same clouds seen again, while several in ONE burst are
        # several clouds. Colonia reports 2 every time.
        self.sysaddr = None
        self._nsp_burst = {}
        self._nsp_armed = False  # the first journal read is catch-up: show, do not sound
        # Hunting mode. Predicted systems appear in no catalogue at all, so nobody else
        # can be flying to one and its existence is still an open question; catalogued
        # ones usually carry better odds, because being in the spine means their boxel
        # is better sampled. The two do not rank against each other sensibly, so this
        # switches between them instead of trying to mix them in one list.
        self.pred_only = bool(a.predicted_only)

        # Key column. Every row a key can act on is labelled with that key, so the
        # width has to fit the longest label in use -- "F12" for a waypoint, but
        # "alt+F12" for a confirmed find, and longer again if --action-prefix is
        # changed. Derived rather than fixed, so a custom prefix stays aligned instead
        # of ragged.
        #
        # The confirmed finds get the F-keys under the action prefix rather than a
        # second bare set: they are the same "pick row N" gesture as the route list,
        # against a list that sits alongside it rather than replacing it.
        self.FOUND_KEYS = [f"{a.action_prefix}+{k}" for k in HOTKEYS]
        # ctrl+F1.. for the adjacent sectors: the same "pick row N" gesture as the
        # waypoints (bare F-keys) and the confirmed finds (alt+F-keys), under a third
        # modifier. --sector-prefix changes it if ctrl+F clashes with an in-game bind.
        self.SECTOR_KEYS = [f"{a.sector_prefix}+{k}"
                            for k in HOTKEYS[:max(0, a.sector_n)]]
        self.ROW_KEYS = {"neutron": f"{a.action_prefix}+N", "dssa": f"{a.action_prefix}+U"}
        self.KEY_W = max(len(k) for k in
                         HOTKEYS + self.FOUND_KEYS + self.SECTOR_KEYS
                         + list(self.ROW_KEYS.values()) + [self._mode_key()])
        self.ROW_PREFIX_W = self.KEY_W + 2          # "[" + key + "]"
        self.carriers = []
        self.neutron = []
        self.sectors = []            # richest adjacent sectors, alt+1..3
        self.sector_total = 0        # how many neighbours held anything at all
        self.top_target = None       # (name, xyz) of the F1 row; aims the neutron search
        self.region_line = ""
        self.nav_line = ""
        self.note = ""
        self._nav_dest = None
        self._announced_arrival = None
        self._navroute_mtime = None
        self._pending = None
        self._manual_pos = a.x is not None and a.y is not None   # explicit --x/--y wins

        r = self.root = tk.Tk()
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-alpha", a.opacity)
        r.config(bg=KEY)
        try:
            r.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        if self._manual_pos:
            r.geometry(f"+{a.x}+{a.y}")
        self.font = ("Consolas", a.font)
        self.icon_px = a.icon_size if a.icon_size else max(18, a.font + 9)
        if keyboard:
            fk = f"{a.fn_prefix}+F1-F12" if a.fn_prefix else "F1-F12"
            hk = f"[{fk} = copy waypoint]"
        else:
            hk = "[install 'keyboard' for hotkeys]"
        # Top row: title on the left, session telemetry and the wall clock on the
        # right. The clock is packed FIRST so it stays hard against the right edge --
        # the session text changes width as the rate does, and packing it afterwards
        # would let it shove the clock around.
        top = tk.Frame(r, bg=KEY)
        top.pack(anchor="w", fill="x")
        small = ("Consolas", a.font - 2)
        self.clock = tk.Label(top, text="", font=small, fg=HEAD, bg=KEY)
        self.clock.pack(side="right", padx=(8, 2))
        self.session = tk.Label(top, text="", font=small, fg=DIM, bg=KEY)
        self.session.pack(side="right")
        self.bar = tk.Label(top, text=f"::: BH/WR route {'(drag) ' if a.interactive else ''}{hk} :::",
                            font=small, fg=HEAD, bg=KEY)
        self.bar.pack(side="left")
        if a.interactive:
            for w in (top, self.bar, self.session, self.clock):
                w.bind("<Button-1>", self._start)
                w.bind("<B1-Motion>", self._drag)
        self.body = tk.Frame(r, bg=KEY)
        self.body.pack(anchor="w", fill="x")
        self.status = tk.Label(r, text="", font=self.font, fg=OK, bg=KEY)
        self.status.pack(anchor="w")
        if not a.interactive:
            self.text = tk.Label(self.body, text="loading candidates...", justify="left",
                                 font=self.font, fg=FG, bg=KEY)
            self.text.pack(anchor="w")
            r.after(200, self._clickthrough)

        core.SOUND_ENABLED = a.sound
        core.SOUND_FILE = a.alert_sound

        # data
        if not a.include_visited:
            core.load_visited_from_journals(a.journal_dir)
            core.load_visited_store()
            core.save_visited_store()
        if not a.include_wrong:
            core.load_wrong_store()
        core.load_starclass_store()
        core.harvest_starclass_from_journals(a.journal_dir)
        core.save_starclass_store()
        core.load_starpos_store()
        core.load_confirmed_store()
        core.load_carrier_gone_store()
        core.load_poi_seen_store()
        core.load_observations()
        self.T = core.load_targets(a.bh_codes)

        self._register_hotkeys()
        self.path = None
        self.offset = 0
        self.pos = None
        self.sys = "?"
        r.after(400, self.tick)
        r.after(120, self._poll_hotkey)
        self._clock_tick()

    # ---- clock and session throughput ----
    # Its own 1-second loop, not part of the render: renders only happen on journal
    # events, and a clock that advanced when you jumped would be worse than none.
    CLOCK_MS = 1000
    RATE_EVERY = 10          # ticks between recounts; the journal scan is ~4 ms

    def _clock_tick(self):
        try:
            self.clock.config(text=time.strftime("%H:%M:%S"))
            if self._rate_countdown <= 0:
                self._rate_countdown = self.RATE_EVERY
                self.session.config(text=self._session_text())
            self._rate_countdown -= 1
        except tk.TclError:
            return                                   # window is going away
        self.root.after(self.CLOCK_MS, self._clock_tick)

    def _session_text(self):
        """'<n> sys/hr  up H:MM' for the GAME's session, or a note if it is not up.

        Deliberately measured against the game's process, not this app's: leaving the
        overlay running between sessions would otherwise divide by dead time and
        report a rate you never actually flew.
        """
        s = core.game_session()
        if not s:
            return "game not running"
        up = core.game_uptime_s() or 0.0
        arrivals, distinct = core.jumps_since(self.a.journal_dir, s[1])
        self.session_visits = distinct
        h, m = int(up // 3600), int(up % 3600 // 60)
        if up < 120:
            return f"{distinct} sys  up {h}:{m:02d}"   # a rate off 90 s means nothing
        return f"{distinct / (up / 3600):.1f} sys/hr  up {h}:{m:02d}"

    # ---- hotkeys ----
    def _register_hotkeys(self):
        """Bind F1..F12 (and the legacy prefix+digit) to the waypoint copies.

        Both sets are registered so neither has to be chosen: F-keys cover all twelve
        waypoints with a single press, digits cover the first ten and survive any
        function-key clash with the game. Every binding is registered individually --
        one key failing (Windows can refuse an already-hooked combo) must not take the
        rest down with it.
        """
        if not keyboard:
            return
        pre = f"{self.a.fn_prefix}+" if self.a.fn_prefix else ""
        failed = []
        for i, k in enumerate(HOTKEYS):
            try:
                keyboard.add_hotkey(f"{pre}{k.lower()}", self._set_pending, args=(i,),
                                    suppress=self.a.suppress)
            except Exception:
                failed.append(k)
        for d in range(10):
            try:
                # digit 0 is waypoint 10, matching how the keyboard row reads
                keyboard.add_hotkey(f"{self.a.hotkey_prefix}+{d}", self._set_pending,
                                    args=(9 if d == 0 else d - 1,), suppress=self.a.suppress)
            except Exception:
                failed.append(str(d))
        # Actions rather than waypoints, so they get their own prefix: the HUD is
        # click-through by default, which makes a key the only way to reach any of them
        # while the game has focus.
        for key, action in self.ACTIONS.items():
            try:
                keyboard.add_hotkey(f"{self.a.action_prefix}+{key}", self._set_pending,
                                    args=(action,), suppress=self.a.suppress)
            except Exception:
                failed.append(f"{self.a.action_prefix}+{key}")
        for i, k in enumerate(self.FOUND_KEYS):     # confirmed finds: alt+F1..alt+F12
            try:
                keyboard.add_hotkey(k.lower(), self._set_pending, args=(("found", i),),
                                    suppress=self.a.suppress)
            except Exception:
                failed.append(k)
        for i, k in enumerate(self.SECTOR_KEYS):    # adjacent sectors: ctrl+F1..
            try:
                keyboard.add_hotkey(k.lower(), self._set_pending, args=(("sector", i),),
                                    suppress=self.a.suppress)
            except Exception:
                failed.append(k)
        if failed:
            print(f"[hotkeys unavailable: {', '.join(failed)}] "
                  f"(try running as admin, or --fn-prefix ctrl+alt)")

    def _set_pending(self, i):
        """Store the waypoint index or action NAME; the tkinter work happens on the
        main thread.

        `keyboard` fires this on its own hook thread, and tkinter is not thread-safe,
        so touching the clipboard here would be a cross-thread call into Tk.
        """
        self._pending = i

    # action-prefix key -> method name. Kept as a table so the key list, the bindings
    # and the on-screen hints cannot drift apart.
    ACTIONS = {"p": "toggle_pred_only",
               "n": "copy_nearest_neutron",
               "u": "copy_nearest_dssa"}

    def _poll_hotkey(self):
        if self._pending is not None:
            i, self._pending = self._pending, None
            if isinstance(i, str):                      # a named action
                getattr(self, i)()
            elif isinstance(i, tuple):                  # (table, row)
                which, j = i
                rows = self.found if which == "found" else self.sectors
                if 0 <= j < len(rows):
                    self.copy(rows[j]["name"])
                    if which == "sector":
                        s = rows[j]
                        self.status.config(
                            text=f"sector {s['sector']}: {s['exp']:.1f} expected BH/WR "
                                 f"in {s['n_sys']:,} predicted -> {s['name']}")
                else:
                    label = "confirmed find" if which == "found" else "adjacent sector"
                    self.status.config(text=f"(no {label} {j + 1})")
            elif 0 <= i < len(self.items):
                self.copy(self.items[i]["name"])
            else:
                self.status.config(text=f"(no waypoint {i + 1})")
        self.root.after(120, self._poll_hotkey)

    # ---- window helpers ----
    def _clickthrough(self):
        try:
            import ctypes
            GWL, LAYERED, TRANSP = -20, 0x80000, 0x20
            h = ctypes.windll.user32.GetParent(self.root.winfo_id())
            s = ctypes.windll.user32.GetWindowLongW(h, GWL)
            ctypes.windll.user32.SetWindowLongW(h, GWL, s | LAYERED | TRANSP)
        except Exception:
            pass

    def _start(self, e):
        self._ox, self._oy = e.x, e.y

    def _drag(self, e):
        self._manual_pos = True          # stop re-anchoring once you place it yourself
        self.root.geometry(f"+{self.root.winfo_x()+e.x-self._ox}+{self.root.winfo_y()+e.y-self._oy}")

    def _screen_rect(self):
        """(left, top, right, bottom) to anchor against.

        Default is the full screen, which is what you want in-game: Elite in
        Borderless covers the taskbar, so anchoring to the work area would leave a
        taskbar-sized gap. --work-area anchors to the usable desktop instead, so the
        HUD clears the taskbar when you are not in the game.
        """
        if self.a.work_area and sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class RECT(ctypes.Structure):
                    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]
                r = RECT()
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
                    return r.left, r.top, r.right, r.bottom
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _reposition(self):
        """Re-anchor after every render -- the panel's height changes with the number
        of waypoints, so a bottom/right anchor has to be recomputed each time."""
        if self._manual_pos:
            return
        try:
            self.root.update_idletasks()
            w, h = self.root.winfo_width(), self.root.winfo_height()
            left, top, right, bottom = self._screen_rect()
            m = self.a.margin
            x = left + m if self.a.anchor in ("tl", "bl") else max(left, right - w - m)
            y = top + m if self.a.anchor in ("tl", "tr") else max(top, bottom - h - m)
            self.root.geometry(f"+{int(x)}+{int(y)}")
        except tk.TclError:
            pass

    def copy(self, name):
        """Put `name` on the clipboard. Only ever reached from a hotkey or a button."""
        if not core.copy_to_clipboard(name):       # Win32 first; survives app exit
            self.root.clipboard_clear()
            self.root.clipboard_append(name)
            self.root.update()
        self.status.config(text=f"copied: {name}")

    # ---- ED-style icon buttons ----
    def _icon(self, parent, kind, command, hint):
        """A flat, chamfered line-art icon drawn on a canvas -- Elite's HUD idiom,
        rather than a native Tk button. The canvas background is the transparency
        key, so only the strokes are visible over the game.
        """
        s = self.icon_px
        c = tk.Canvas(parent, width=s, height=s, bg=KEY, highlightthickness=0,
                      bd=0, takefocus=0, cursor="hand2")
        col = ED_AMBER if kind == "copy" else ED_RED
        hot = ED_AMBER_HOT if kind == "copy" else ED_RED_HOT
        w = max(1, s // 9)

        def P(*pts):
            return [v * s for pt in pts for v in pt]

        if kind == "copy":
            # two offset plates with a chamfered top-right corner (ED panel motif);
            # the front plate is filled with the key colour so it occludes the back
            back = c.create_polygon(*P((.34, .07), (.84, .07), (.94, .17), (.94, .58), (.34, .58)),
                                    outline=col, fill="", width=w)
            front = c.create_polygon(*P((.07, .40), (.57, .40), (.67, .50), (.67, .93), (.07, .93)),
                                     outline=col, fill=KEY, width=w)
            parts = [back, front]
        else:
            # hostile-red cross inside chamfered brackets
            a, b = .22, .78
            parts = [
                c.create_line(*P((a, a), (b, b)), fill=col, width=w + 1, capstyle="projecting"),
                c.create_line(*P((b, a), (a, b)), fill=col, width=w + 1, capstyle="projecting"),
                c.create_line(*P((.06, .26), (.06, .06), (.26, .06)), fill=col, width=w),
                c.create_line(*P((.74, .94), (.94, .94), (.94, .74)), fill=col, width=w),
            ]

        def recolour(colour):
            for it in parts:
                if c.type(it) == "polygon":
                    c.itemconfig(it, outline=colour)
                else:
                    c.itemconfig(it, fill=colour)

        c.bind("<Enter>", lambda _e: (recolour(hot), self.status.config(text=hint)))
        c.bind("<Leave>", lambda _e: recolour(col))
        c.bind("<Button-1>", lambda _e: command())
        return c

    def mark_wrong(self, name):
        """Tag a system as not actually existing, then re-route around it."""
        core.mark_wrong(name)
        if self.pos:
            self.recompute()
            self.render()
        self.status.config(text=f"WRONG: {name[:30]}  ({len(core.WRONG):,} tagged)")

    def toggle_pred_only(self):
        """Switch between hunting only uncatalogued systems and hunting everything."""
        self.pred_only = not self.pred_only
        if self.pos:
            self.recompute()
            self.render()
        self.status.config(text="PREDICTED ONLY: systems in no catalogue"
                                if self.pred_only else
                                "ALL: predicted + catalogued")

    def copy_nearest_neutron(self):
        """Copy the best neutron star for an FSD supercharge toward the F1 target.

        Resolved on demand rather than read off the drawn table, so the key works even
        with --neutron-n 0 or before the first render.
        """
        if not self.pos:
            self.status.config(text="(no position yet)")
            return
        ns = core.nearest_neutron(np.asarray(self.pos, dtype=np.float64), 1,
                                  target=self.top_target[1] if self.top_target else None)
        if not ns:
            self.status.config(text="(no neutron data -- run scripts/build_neutron.py)")
            return
        nm, dist = ns[0]
        self.copy(nm)
        toward = f" toward {self.top_target[0][:24]}" if self.top_target else ""
        self.status.config(text=f"neutron {dist:,.0f} ly{toward}: {nm}")

    def copy_nearest_dssa(self):
        """Copy the SYSTEM of the nearest DSSA carrier.

        The system name is what you paste into the galaxy map; the callsign is only
        useful once you are there. DSSA carriers are parked long-term, which is why
        they get their own key -- an ordinary UC carrier may well have moved.
        """
        if not self.pos:
            self.status.config(text="(no position yet)")
            return
        C = core.load_carriers()
        picks = core.nearest_carriers(np.asarray(self.pos, dtype=np.float64), 1,
                                      require_uc=True, dssa_only=True)
        if not C or not picks:
            self.status.config(text="(no DSSA carrier available)")
            return
        i, dist = picks[0]
        system = str(C["system"][i])
        self.copy(system)
        self.status.config(text=f"DSSA {C['callsign'][i]} {dist:,.0f} ly: {system}")

    def mark_carrier_gone(self, callsign, system):
        """Tag a carrier as no longer there, and immediately offer the next one.

        You only ever learn this by arriving at an empty system, so the recompute is
        the point: the replacement is on screen before you close the galaxy map.
        """
        core.mark_carrier_gone(callsign)
        if self.pos:
            self.recompute()
            self.render()
        self.status.config(text=f"GONE: {callsign} @ {system[:22]}  "
                                f"({len(core.CARRIER_GONE):,} tagged)")

    # ---- routing ----
    def recompute(self):
        pos = np.asarray(self.pos, dtype=np.float64)
        # Read the plotted route FIRST: it is what reveals the arrival-star classes,
        # and the mask below depends on them. Reading it afterwards would leave the
        # rule-out one cycle behind the probabilities, so a system would visibly drop
        # to 0% while still sitting in the list.
        nav = core.read_navroute(self.a.journal_dir)
        # NavRoute reports exact StarPos for every hop; fold it in before ranking so a
        # predicted system stops routing on its boxel centroid the moment we know better
        core.apply_starpos(self.T)
        mask = core.available_mask(self.T, self.a.rule_out_below, self.a.keep_secondary,
                                   self.pred_only)
        route, n_in_radius, n_ext, n_trunc = core.select_targets(
            pos, self.T, mask, self.a.radius, self.a.topn,
            self.a.route_ms / 1000.0, self.a.max_nodes, sort=self.a.sort)
        total_in_radius = int(
            (np.linalg.norm(self.T["xyz"][mask] - pos[None, :], axis=1) <= self.a.radius).sum())

        self.items = []
        ranked = self.a.sort != "route"
        prev, cum = pos, 0.0
        for i, gi in enumerate(route, 1):
            p = self.T["xyz"][gi]
            if ranked:
                # not a path, so the only meaningful distance is the one from YOU
                leg, cum = float(np.linalg.norm(p - pos)), None
            else:
                leg = float(np.linalg.norm(p - prev))
                cum += leg
            pb, pw = core.effective_prob(self.T, gi)
            nm = str(self.T["name"][gi])
            cls = core.STARCLASS.get(nm)
            st, stlabel = core.target_status(nm, str(self.T["mc"][gi]))
            self.items.append({
                "name": nm,
                "mc": str(self.T["mc"][gi]),
                "leg": leg, "cum": cum,
                "approx": bool(self.T["approx"][gi]) if self.T.get("approx") is not None else False,
                "conf": cls if core.classify_star(cls) else None,
                "prob": min(1.0, pb + pw), "p_bh": pb, "p_wr": pw,
                "p_hr": float(self.T["p_hr"][gi]) if self.T.get("p_hr") is not None else 0.0,
                "pred": self.T["source"][gi] != "unscanned",
                "ext": i > n_in_radius,
                "status": st, "status_label": stlabel,
            })
            prev = p

        # ---- catalogued points of interest take the top slots -------------------
        # A black hole is a probability; a reported phenomenon or green giant is a
        # certainty, and the only thing here no model could have found for you. So these
        # go above the ranked targets rather than into them, and they leave the list for
        # good once you have been (core.note_poi_seen, on arrival).
        #
        # Searched to the SAME radius as the candidates, and shown in BOTH modes. Both
        # follow from one fact: you get the codex credit however many commanders arrived
        # first, so neither "is it catalogued" nor a tighter range than a
        # 12%-probability black hole means anything for them.
        poi = core.nearest_poi(pos, self.poi_radius, self.a.nsp_n) if self.a.nsp_n else []
        # The label ('NSP' / 'GGG') goes in the Mass column: the boxel mass code gates
        # BH/WR odds and these rows have none, so the slot is free and it is the one
        # column wide enough to say what the row IS. Conf stays empty -- it means
        # "confirmed arrival-star class", and neither of these is a star.
        self.items = [{
            "name": nm, "mc": label,
            "leg": d, "cum": None, "approx": False,
            "conf": None, "prob": 0.0, "p_bh": 0.0, "p_wr": 0.0,
            "pred": False, "ext": False, "nsp": True, "kinds": kinds,
            "status": "poi", "status_label": kinds.replace("_", " ").replace("+", ", "),
        } for nm, d, label, kinds in poi] + self.items
        if self.a.topn:
            self.items = self.items[:self.a.topn]

        # the F1 target: what the neutron search aims at, so a supercharge advances
        # the trip instead of spending its boost on the diversion that earned it.
        # Taken from the list rather than from `route`, so it follows whatever F1
        # actually shows -- a phenomenon when one is up there, the top candidate
        # otherwise.
        self.top_target = None
        if self.items:
            top = self.items[0]
            xyz = (core.poi_xyz(top["name"]) if top.get("nsp")
                   else self.T["xyz"][route[0]])
            if xyz is not None:
                self.top_target = (top["name"], xyz)

        rid, rname, votes, rdist = core.region_of(pos)
        n_region = core.region_target_count(self.T, mask, rid)
        conf = "" if votes >= 5 else f" ~{votes}/5"
        self.region_line = (f"region: {rname}{conf}   |   {n_region:,} target(s) in region"
                            if rname else "")
        self.header = f"@ {self.sys}   {total_in_radius:,} target(s) within {self.a.radius:,.0f} ly"
        if not route:
            self.note = "no unvisited targets remain"
        elif total_in_radius == 0:
            self.note = f"nothing in radius -> nearest {len(route)} beyond it"
        elif n_ext:
            self.note = f"only {n_in_radius} in radius -> {n_ext} more added beyond (+)"
        else:
            self.note = ""
        if n_trunc:
            self.note = (self.note + "; " if self.note else "") + f"{n_trunc:,} beyond --max-nodes not routed"

        # ---- where to go NEXT: the richest adjacent sectors --------------------
        # The waypoint list answers "what should I scan here". This answers "which way
        # should I be heading", which the waypoint list cannot: it ranks single systems,
        # so it can never say that the space next door is worth more than the space
        # you are in. Ordered by how many predicted -- uncatalogued -- systems each
        # neighbour holds; see core.adjacent_sector_targets for why not by expected rares.
        allsec = core.adjacent_sector_targets(pos, self.T, mask) if self.a.sector_n else []
        self.sector_total = len(allsec)
        self.sectors = allsec[:self.a.sector_n]

        # ---- confirmed BH/WR you still owe a trip to ----
        # Deliberately NOT filtered by radius or by the candidate pool: the whole
        # point is that these turn up when you cannot divert, and must still be here
        # weeks later. See core.CONFIRMED_STORE.
        if core.sync_confirmed(self.T):
            core.save_confirmed_store()
        # a reveal usually lands while you are in the galaxy map with the HUD behind
        # it, so this is announced out loud rather than only drawn
        for nm, kind in core.drain_new_confirmed():
            core.alert(kind)
            self._alert_line = f"*** {kind} DETECTED: {nm} ***"
        core.log_observations(self.T)     # feeds scripts/analyse_observations.py
        todo = core.pending_confirmed(pos, self.pred_only)
        self.found_total = len(todo)
        self.found = [{"name": n, "rec": rec, "dist": d}
                      for n, rec, d in todo[:self.a.found_n]] if self.a.found_n else []

        # ---- nearest Universal Cartographics carrier ----
        # The copy button copies the SYSTEM, not the carrier: the system name is what
        # you paste into the galaxy map to route there.
        self.carriers = []
        C = core.load_carriers()
        if C:
            picks = core.nearest_carriers(pos, self.a.carrier_n, require_uc=True)
            got_dssa = any(C["is_dssa"][i] for i, _d in picks)
            if self.a.carrier_dssa and not got_dssa:
                # DSSA carriers are parked long-term, so always offer the nearest one
                picks += core.nearest_carriers(pos, 1, require_uc=True, dssa_only=True)
            for i, dist in picks:
                self.carriers.append({
                    "callsign": str(C["callsign"][i]), "cname": str(C["name"][i]),
                    "system": str(C["system"][i]), "dist": dist,
                    "moved": str(C["last_moved"][i])[:10],
                    "dssa": bool(C["is_dssa"][i]),
                })

        # ---- confirmed neutron stars, aimed at the F1 target (FSD supercharge) ----
        self.neutron = []
        if self.a.neutron_n:
            self.neutron = core.nearest_neutron(
                pos, self.a.neutron_n,
                target=self.top_target[1] if self.top_target else None)

        # ---- plotted-route progress + auto-advance ----
        self.nav_line = ""
        if nav:
            self._nav_dest = nav["destination"]
            prog = core.navroute_progress(nav, self.sys, pos)
            nxt = self.items[0]["name"] if self.items else None
            if prog:
                i, tot, rem = prog
                if self.sys == nav["destination"]:
                    # arrived: the target is now visited, so the route has already
                    # re-solved past it -- name the new head so F1 gets you the next one
                    self.nav_line = f"ARRIVED {nav['destination'][:26]}  ->  next: {nxt or '-'}"
                else:
                    match = "" if nxt == nav["destination"] else "  (OFF-ROUTE)"
                    self.nav_line = (f"plotted: {i}/{tot} jumps -> {nav['destination'][:24]}"
                                     f"  {rem:,.0f} ly left{match}")

        # The clipboard is yours. Nothing here writes to it: copying happens only when
        # you press a hotkey or click a copy button, so the app can never overwrite
        # something you put there yourself while it re-solves in the background.

    # ---- rendering ----
    # every table below renders through core.star_row, so a system looks the same
    # wherever it appears and the columns line up when the tables are stacked
    NAME_W = 24

    def _row_text(self, i, it):
        return core.star_row(
            it["name"], it["leg"], it["p_bh"], it["p_wr"],
            predicted=it["pred"], conf=it.get("conf"), approx=it.get("approx"),
            ext=it["ext"], mass=it["mc"], p_hr=it.get("p_hr", 0.0), name_w=self.NAME_W,
            extra=f"{it['cum']:>9,.0f}" if it["cum"] is not None else "")

    def _row_colour(self, it):
        # A confirmed primary is highlighted, but a known non-target primary is NOT
        # demoted: the mass code gates the system, so the black hole may be a
        # secondary, and a primary black hole is an equally good first discovery.
        if it.get("nsp"):
            return ED_AMBER_HOT      # a certainty, not odds -- and it expires when seen
        if it["status"] == "primary":
            return CONFIRM
        return DIM if it["ext"] else FG

    # interactive layout: one grid for header AND rows, so the column header lines up
    # with the text column no matter how wide the [copy]/[wrong] buttons render.
    COL_TEXT = 3        # hotkey=0, copy=1, wrong=2, text=3

    @property
    def HDR(self):
        """Column header, shared with every sub-table so the columns line up."""
        return core.star_header(self.NAME_W,
                                extra="" if self.a.sort != "route" else f"{'cum':>9}")

    @property
    def nsp_line(self):
        """Phenomena in the system you are standing in, or '' if there are none.

        The count is the largest single burst, not the total seen: repeats across
        bursts are the same clouds re-announced.
        """
        if not self._nsp_burst:
            return ""
        n = max(self._nsp_burst.values())
        return ("** NOTABLE STELLAR PHENOMENA HERE" + (f" x{n}" if n > 1 else "")
                + " -- in the nav panel **")

    def _banner(self, g, r, text, colour):
        """A full-width line above the table, spanning the key/copy/retire columns."""
        tk.Label(g, text=text, font=self.font, fg=colour, bg=KEY
                 ).grid(row=r, column=0, columnspan=self.COL_TEXT + 1, sticky="w")
        return r + 1

    def render(self):
        if not self.a.interactive:
            self.text.config(text=self._plain())
            self._reposition()
            return
        for w in self.body.winfo_children():
            w.destroy()
        g, r = self.body, 0
        r = self._banner(g, r, self.header, HEAD)
        if self._alert_line:
            r = self._banner(g, r, self._alert_line, CONFIRM)
        # mode switch: click it, or press the key when the HUD is click-through
        r = self._grid_row(g, r, self._mode_text(),
                           CONFIRM if self.pred_only else DIM, key=self._mode_key(),
                           on_click=self.toggle_pred_only,
                           hint="click to switch between uncatalogued-only and everything")
        if self.nsp_line:
            r = self._banner(g, r, self.nsp_line, CONFIRM)
        if self.region_line:
            r = self._banner(g, r, self.region_line, ED_AMBER_HOT)
        if self.nav_line:
            r = self._banner(g, r, self.nav_line,
                             CONFIRM if self.nav_line.startswith("ARRIVED") else ED_AMBER)
        if self.note:
            r = self._banner(g, r, f"! {self.note}", WARN)
        tk.Label(g, text=self.HDR, font=self.font, fg=DIM, bg=KEY
                 ).grid(row=r, column=self.COL_TEXT, sticky="w"); r += 1
        if not self.items:
            tk.Label(g, text="(none)", font=self.font, fg=DIM, bg=KEY
                     ).grid(row=r, column=self.COL_TEXT, sticky="w")
            self._reposition()
            return
        for i, it in enumerate(self.items):
            r = self._grid_row(g, r, self._row_text(i, it), self._row_colour(it),
                               key=HOTKEYS[i] if i < len(HOTKEYS) else "-",
                               copy=it["name"], copy_hint=f"copy {it['name'][:28]}",
                               retire=lambda x=it["name"]: self.mark_wrong(x),
                               retire_hint=f"mark WRONG: {it['name'][:24]}")

        # ---- confirmed BH/WR, not yet visited (white: these are certain) ----
        r = self._grid_table(
            g, r, self._found_header(), CONFIRM, self.found,
            lambda it, i: (self._found_row(it), CONFIRM, it["name"],
                           f"copy {it['name'][:28]}",
                           lambda x=it["name"]: self.mark_wrong(x),
                           f"drop from the found list: {it['name'][:24]}",
                           self._found_key(i)))

        # ---- richest adjacent sectors: copy the way IN, nothing to retire ----
        r = self._grid_table(
            g, r, self._sector_header(), ED_AMBER_HOT, self.sectors,
            lambda s, i: (self._sector_row(s), ED_AMBER_HOT, s["name"],
                          f"copy {s['name'][:26]} -- the closest predicted system "
                          f"in {s['sector'][:18]}", None, None,
                          self._sector_key(i)))

        # ---- confirmed neutron stars: nothing to retire, so no second button ----
        # Only the FIRST row carries the key label: alt+N always copies the nearest,
        # so labelling the rest would promise a key that does not exist.
        r = self._grid_table(
            g, r, self._neutron_header(), ED_AMBER_HOT,
            self.neutron,
            lambda nd, i: (self._neutron_row(*nd), FG, nd[0],
                           f"copy {nd[0][:26]} ({nd[1]:,.0f} ly)", None, None,
                           self.ROW_KEYS["neutron"] if i == 0 else " "))

        # ---- carriers: copy the SYSTEM, and retire the CARRIER when it has moved ----
        # alt+U targets the nearest DSSA specifically, so the label goes on that row
        # rather than on the first one, which is usually an ordinary UC carrier.
        dssa_row = next((j for j, c in enumerate(self.carriers) if c["dssa"]), None)
        r = self._grid_table(
            g, r, "-- nearest Universal Cartographics (copies system) --", ED_AMBER_HOT,
            self.carriers,
            lambda c, i: (self._carrier_row(c), CONFIRM if c["dssa"] else FG, c["system"],
                          f"copy system {c['system'][:24]} ({c['dist']:,.0f} ly)",
                          lambda cs=c["callsign"], s=c["system"]: self.mark_carrier_gone(cs, s),
                          f"GONE: {c['callsign']} is no longer at {c['system'][:20]}",
                          self.ROW_KEYS["dssa"] if i == dssa_row else " "))
        self._reposition()

    def _grid_row(self, g, r, text, colour, key=" ", copy=None, copy_hint="",
                  retire=None, retire_hint="", on_click=None, hint=None):
        """One table line: [hotkey] [copy] [retire] text. Returns the next grid row.

        Every row draws through here -- the mode line included -- so the key bracket,
        the buttons and the text column land in the same places regardless of which
        table a row belongs to. That is what lets the shared star_row layout actually
        line up on screen, and it is why the mode line does not pad itself by hand.
        """
        tk.Label(g, text=f"[{key:>{self.KEY_W}}]" if key.strip() else " " * self.ROW_PREFIX_W,
                 font=self.font, fg=OK, bg=KEY).grid(row=r, column=0, sticky="w")
        if copy is not None:
            self._icon(g, "copy", lambda x=copy: self.copy(x), copy_hint
                       ).grid(row=r, column=1, padx=(4, 5), pady=2)
        if retire is not None:
            self._icon(g, "wrong", retire, retire_hint
                       ).grid(row=r, column=2, padx=(0, 10), pady=2)
        lab = tk.Label(g, text=text, font=self.font, fg=colour, bg=KEY,
                       cursor="hand2" if on_click else "")
        lab.grid(row=r, column=self.COL_TEXT, sticky="w")
        if on_click:
            lab.bind("<Button-1>", lambda _e: on_click())
        if hint:
            lab.bind("<Enter>", lambda _e: self.status.config(text=hint))
        return r + 1

    def _grid_table(self, g, r, header, header_colour, rows, spec):
        """A whole sub-table: amber header then one _grid_row per entry.

        `spec(item, i)` returns
        (text, colour, copy_value, copy_hint, retire, retire_hint, key).
        """
        if not rows:
            return r
        tk.Label(g, text=header, font=self.font, fg=header_colour, bg=KEY
                 ).grid(row=r, column=0, columnspan=self.COL_TEXT + 1, sticky="w")
        r += 1
        for i, item in enumerate(rows):
            text, colour, cp, cp_hint, retire, retire_hint, key = spec(item, i)
            r = self._grid_row(g, r, text, colour, key=key, copy=cp, copy_hint=cp_hint,
                               retire=retire, retire_hint=retire_hint)
        return r

    def _carrier_row(self, c):
        tag = " DSSA" if c["dssa"] else ""
        label = (c["cname"] or c["callsign"])[:16]
        return (f" {c['system'][:24]:24s}{c['dist']:7.0f}{'':>8}"
                f"  {c['callsign']} {label}{tag}  moved {c['moved']}")

    def _found_header(self):
        shown = f"{len(self.found)} of " if len(self.found) < self.found_total else ""
        return (f"** CONFIRMED BH/WR, not visited -- Pred first "
                f"({shown}{self.found_total:,}, any range) --")

    def _found_row(self, it):
        return core.star_row_confirmed(it["name"], it["rec"], it["dist"],
                                       name_w=self.NAME_W)

    def _mode_text(self):
        """The mode line's TEXT only -- the key label is added by whoever draws it,
        so it lines up with the waypoint rows instead of being spaced by hand.

        The leading space matches the +/space in-radius flag that star_row emits, so
        the mode text starts in the same column as the system names.
        """
        return (" [X] PREDICTED ONLY -- uncatalogued systems" if self.pred_only
                else " [ ] all sources -- predicted + catalogued")

    def _mode_key(self):
        return f"{self.a.action_prefix}+P"

    def _found_key(self, i):
        """Key label for confirmed row `i`, blank past the twelve bound F-keys."""
        return self.FOUND_KEYS[i] if i < len(self.FOUND_KEYS) else " "

    def _sector_key(self, i):
        """Key label for adjacent-sector row `i`, blank past the bound digits."""
        return self.SECTOR_KEYS[i] if i < len(self.SECTOR_KEYS) else " "

    def _sector_header(self):
        shown = (f"{len(self.sectors)} of " if len(self.sectors) < self.sector_total
                 else "")
        # kept within the table's own width (79 cols) so it cannot widen the HUD
        return (f"-- ADJACENT sectors, most Pred first -- Pred = predicted systems "
                f"({shown}{self.sector_total}) --")

    def _sector_row(self, s):
        return core.sector_row(s, name_w=self.NAME_W)

    def _neutron_header(self):
        toward = f" toward {self.top_target[0][:22]}" if self.top_target else ""
        return f"-- neutron star (FSD boost){toward} --"

    def _neutron_row(self, nm, dist):
        # a scanned, catalogued neutron star: no BH/WR odds to offer and never a
        # prediction, but Conf carries its class so it reads like every other row
        return core.star_row(nm, dist, 0.0, 0.0, predicted=False, conf="N",
                             name_w=self.NAME_W)

    def _plain(self):
        pad = " " * self.ROW_PREFIX_W

        def keyed(key, text):
            """A row prefixed with its key, or blank-padded to the same width."""
            return (f"[{key:>{self.KEY_W}}]" if key.strip() else pad) + text

        out = [self.header, keyed(self._mode_key(), self._mode_text())]
        if self._alert_line:
            out.append(self._alert_line)
        if self.nsp_line:
            out.append(self.nsp_line)
        if self.region_line:
            out.append(self.region_line)
        if self.nav_line:
            out.append(self.nav_line)
        if self.note:
            out.append(f"! {self.note}")
        out.append(pad + self.HDR)                    # clear the "[ F1]" row prefix
        if not self.items:
            out.append(pad + "(none)")
        for i, it in enumerate(self.items):
            out.append(keyed(HOTKEYS[i] if i < len(HOTKEYS) else "-",
                             self._row_text(i, it)))
        if self.found:
            out.append(self._found_header())
            for i, it in enumerate(self.found):
                out.append(keyed(self._found_key(i), self._found_row(it)))
        if self.sectors:
            out.append(self._sector_header())
            for i, s in enumerate(self.sectors):
                out.append(keyed(self._sector_key(i), self._sector_row(s)))
        if self.neutron:
            out.append(self._neutron_header())
            for i, (nm, dist) in enumerate(self.neutron):
                out.append(keyed(self.ROW_KEYS["neutron"] if i == 0 else " ",
                                 self._neutron_row(nm, dist)))
        if self.carriers:
            out.append("-- nearest Universal Cartographics --")
            dssa_row = next((j for j, c in enumerate(self.carriers) if c["dssa"]), None)
            for i, c in enumerate(self.carriers):
                out.append(keyed(self.ROW_KEYS["dssa"] if i == dssa_row else " ",
                                 self._carrier_row(c)))
        return "\n".join(out)

    # ---- journal polling ----
    def tick(self):
        if self.a.pos:
            if self.pos is None:
                self.pos, self.sys = list(self.a.pos), "(fixed)"
                self.recompute()
                self.render()
            return
        p = core.latest_journal(self.a.journal_dir)
        if p and p != self.path:
            self.path, self.offset = p, 0
        if self.path:
            try:
                moved = new_class = route_changed = nsp_new = False
                # Plotting a route rewrites NavRoute.json. Watch the file's mtime as
                # well as the journal event: the two are written independently, so
                # whichever lands first triggers the refresh.
                try:
                    mt = os.path.getmtime(os.path.join(self.a.journal_dir, core.NAVROUTE_FILE))
                except OSError:
                    mt = None
                if mt != self._navroute_mtime:
                    self._navroute_mtime = mt
                    route_changed = True
                with open(self.path, "r", encoding="utf-8") as fh:
                    fh.seek(self.offset)
                    for line in fh:
                        try:
                            e = json.loads(line)
                        except Exception:
                            continue
                        ev = e.get("event")
                        if ev in core.POS_EVENTS and "StarPos" in e:
                            self.pos, self.sys = e["StarPos"], e.get("StarSystem", "?")
                            addr = e.get("SystemAddress")
                            if addr != self.sysaddr:
                                self.sysaddr, self._nsp_burst = addr, {}
                            if self.sys and self.sys not in core.VISITED:
                                core.VISITED.add(self.sys)
                                core.save_visited_store()   # retire it permanently
                            # being here IS seeing it -- the phenomena are in the nav
                            # panel on arrival, so the system stops being a target
                            if core.note_poi_seen(self.sys):
                                core.save_poi_seen_store()
                            self._rate_countdown = 0   # a jump moves the rate: recount
                            moved = True
                        elif (nsp := core.nsp_from_event(e)):
                            addr, _label = nsp
                            # only the system you are in; bursts carry other addresses
                            if addr is not None and addr == self.sysaddr:
                                ts = e.get("timestamp")
                                first = not self._nsp_burst
                                self._nsp_burst[ts] = self._nsp_burst.get(ts, 0) + 1
                                if first:
                                    nsp_new = True
                                    if core.note_poi_seen(self.sys):
                                        core.save_poi_seen_store()
                                    if self._nsp_armed:
                                        core.alert("NSP")
                        elif ev in core.CLASS_EVENTS and e.get("StarClass"):
                            # Elite reveals the arrival star's class the moment you
                            # target or jump -- free confirmation, no scan needed
                            if core.note_starclass(e.get("Name") or e.get("StarSystem"),
                                                   e["StarClass"]):
                                new_class = True
                            route_changed = True      # target changed -> refresh progress
                        elif ev in core.ROUTE_EVENTS:
                            route_changed = True
                    self.offset = fh.tell()
                self._nsp_armed = True   # caught up; from here a new signal is news
                if new_class:
                    core.save_starclass_store()
                if (moved or new_class or route_changed or nsp_new) and self.pos:
                    self.recompute()
                    self.render()
            except FileNotFoundError:
                pass
        self.root.after(2000, self.tick)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            if keyboard:
                try:
                    keyboard.unhook_all()
                except Exception:
                    pass


def main():
    ap = argparse.ArgumentParser(description="In-game HUD route overlay for BH/WR candidates.")
    ap.add_argument("--anchor", choices=("br", "bl", "tr", "tl"), default="br",
                    help="screen corner to pin the HUD to (default br = bottom-right)")
    ap.add_argument("--margin", type=int, default=30, help="gap from the screen edge in px (default 30)")
    ap.add_argument("--work-area", action="store_true",
                    help="anchor to the usable desktop (clears the taskbar) instead of the full "
                         "screen; the default suits Borderless play, which covers the taskbar")
    ap.add_argument("--x", type=int, default=None, help="explicit position; overrides --anchor")
    ap.add_argument("--y", type=int, default=None, help="explicit position; overrides --anchor")
    ap.add_argument("--font", type=int, default=11)
    ap.add_argument("--icon-size", type=int, default=None,
                    help="icon button size in px (default: scales with --font)")
    ap.add_argument("--opacity", type=float, default=0.9)
    ap.add_argument("--topn", type=int, default=12,
                    help="waypoints to display (default 12, one per function key F1-F12)")
    ap.add_argument("--sort", choices=("prob", "route"), default="prob",
                    help="'prob' (default): the nearest --topn targets in radius, BEST ODDS "
                         "first, ties to PREDICTED systems then to the nearer one; the column "
                         "shows distance from you. 'route': the shortest path through them, "
                         "with per-leg and cumulative distance.")
    ap.add_argument("--radius", type=float, default=1000.0, help="target search radius in ly (default 1000)")
    ap.add_argument("--no-sound", dest="sound", action="store_false",
                    help="do not play a tone when a BH/WR is revealed by a route plot")
    ap.add_argument("--alert-sound", default=None, metavar="WAV",
                    help="play this .wav instead of the built-in tones")
    ap.add_argument("--keep-secondary", action="store_true",
                    help="keep systems whose revealed primary is NOT a BH/WR (off by default)")
    ap.add_argument("--found-n", type=int, default=6,
                    help="rows in the confirmed-but-unvisited BH/WR table (default 6; 0 = off). "
                         "The store itself is never truncated.")
    ap.add_argument("--predicted-only", action="store_true",
                    help="start in PREDICTED ONLY mode: hunt only systems that appear in "
                         "no catalogue. Toggle live with the on-screen switch or "
                         "<action-prefix>+p.")
    ap.add_argument("--action-prefix", default="alt",
                    help="modifier for the action keys P/N/U (default alt): "
                         "alt+p toggles PREDICTED ONLY, alt+n copies the nearest "
                         "neutron star, alt+u copies the nearest DSSA carrier's system")
    ap.add_argument("--rule-out-below", type=float, default=0.0005,
                    help="drop candidates whose CONFIDENCE-BOUNDED P(BH or WR) is below this "
                         "fraction (default 0.0005 = 0.05%%). The bound is max(observed, 3/n), so "
                         "a zero from a thin sample is not treated as a real zero. PREDICTED "
                         "systems and revealed BH/WR primaries are never dropped. 0 disables.")
    ap.add_argument("--bh-codes", default="fgh", help="mass codes treated as black-hole targets (default fgh)")
    ap.add_argument("--route-ms", type=int, default=250,
                    help="2-opt refinement budget in ms (default 250; the HUD is single-threaded, "
                         "so this bounds the pause on each jump)")
    ap.add_argument("--neutron-n", type=int, default=1,
                    help="nearest confirmed neutron stars to show (default 1; 0 = off)")
    ap.add_argument("--sector-n", type=int, default=3,
                    help="ADJACENT sectors to show, ordered by how many predicted "
                         "systems each holds (default 3; 0 = off, max 12). Bound to "
                         "<sector-prefix>+F1..FN; each copies the BEST predicted "
                         "system in that sector.")
    ap.add_argument("--sector-prefix", default="ctrl",
                    help="modifier for the adjacent-sector F-keys (default ctrl, so "
                         "ctrl+F1..ctrl+F3)")
    ap.add_argument("--poi-n", "--nsp-n", dest="nsp_n", type=int, default=3,
                    help="catalogued points of interest to put at the TOP of the "
                         "waypoint list -- phenomena, anomalies and green gas giants "
                         "(default 3; 0 = off). They leave the list permanently once "
                         "you arrive, and ignore --predicted-only.")
    ap.add_argument("--poi-radius", "--nsp-radius", dest="nsp_radius", type=float,
                    default=None, metavar="LY",
                    help="how far to look for them (default: the same as --radius)")
    ap.add_argument("--carrier-n", type=int, default=1,
                    help="nearest Universal Cartographics carriers to show (default 1; 0 = off)")
    ap.add_argument("--no-carrier-dssa", dest="carrier_dssa", action="store_false",
                    help="do not always append the nearest DSSA carrier")
    ap.add_argument("--max-nodes", type=int, default=2000, help="max targets fed to the TSP (default 2000)")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--fn-prefix", default="",
                    help="modifier for the F1-F12 waypoint keys; empty (default) = bare "
                         "function keys. Set e.g. ctrl+alt if a bare F-key clashes with an "
                         "in-game or Steam binding (F10 is Elite's screenshot, F12 Steam's).")
    ap.add_argument("--hotkey-prefix", default="ctrl+alt",
                    help="modifier for the fallback digit keys, which copy waypoints 1-10 "
                         "(e.g. ctrl+alt (default), shift, ctrl+shift)")
    ap.add_argument("--suppress", action="store_true", help="stop the hotkey from also reaching the game")
    ap.add_argument("--include-visited", action="store_true", help="do NOT hide already-visited systems")
    ap.add_argument("--include-wrong", action="store_true",
                    help="do NOT hide systems tagged non-existent in wrong.json")
    # accepted and ignored: copying is always manual, so there is nothing to disable.
    # Kept only so a saved launch command does not fail on an unknown argument.
    ap.add_argument("--no-clipboard", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--journal-dir", default=core.DEFAULT_JOURNAL_DIR)
    ap.add_argument("--pos", nargs=3, type=float, metavar=("X", "Y", "Z"))
    a = ap.parse_args()
    if not core.CANDIDATES.exists():
        sys.exit(f"missing {core.CANDIDATES} -- run scripts/build_candidates.py first")
    if keyboard is None:
        print("note: `keyboard` not installed -> global hotkeys off. `pip install keyboard`.")
    Overlay(a).run()


if __name__ == "__main__":
    main()
