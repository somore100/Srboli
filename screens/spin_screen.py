# screens/spin_screen.py
# Wheel of Names — fixed rendering, proper segment highlighting,
# numbers wheel mode, weight display

import os
import random
import math
import collections

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, Triangle
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.metrics import dp


def _start_dir():
    """File-picker start folder: shared storage on Android ("~" is "/" there)."""
    try:
        from core.android_storage import shared_storage_root
        return shared_storage_root()
    except Exception:
        return os.path.expanduser("~")

PALETTE = [
    (0.92, 0.26, 0.26), (0.95, 0.61, 0.07), (0.18, 0.80, 0.44),
    (0.20, 0.60, 0.95), (0.73, 0.33, 0.83), (0.95, 0.34, 0.74),
    (0.11, 0.74, 0.74), (0.85, 0.85, 0.11), (0.96, 0.51, 0.19),
    (0.56, 0.74, 0.56),
]


class WheelWidget(Widget):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.items           = []   # list of {"name": str, "weight": float}
        self.rotation_angle  = 0.0  # degrees, CCW positive (Kivy convention)
        self.highlight_index = None
        self._label_cache    = []
        self.bind(pos=self.redraw, size=self.redraw)

    # ── public API ──────────────────────────────────────────────────────────
    def set_items(self, items):
        self.items = list(items)
        self.redraw()

    def add_item(self, name, weight=1.0):
        if name and name.strip():
            self.items.append({"name": name.strip(), "weight": float(weight)})
            self.redraw()

    def remove_index(self, idx):
        if 0 <= idx < len(self.items):
            del self.items[idx]
            self.redraw()

    def clear(self):
        self.items = []
        self.highlight_index = None
        self.redraw()

    # ── drawing ─────────────────────────────────────────────────────────────
    def redraw(self, *a):
        # remove old label widgets
        for lbl in self._label_cache:
            self.remove_widget(lbl)
        self._label_cache = []
        self.canvas.clear()

        if not self.items:
            return

        cx, cy = self.center_x, self.center_y
        R  = min(self.width, self.height) * 0.42
        n  = len(self.items)
        seg = 360.0 / n

        with self.canvas:
            for i, item in enumerate(self.items):
                r, g, b = PALETTE[i % len(PALETTE)]
                bright = (self.highlight_index == i)
                if bright:
                    r = min(r + 0.18, 1); g = min(g + 0.18, 1)
                    b = min(b + 0.18, 1)
                Color(r, g, b, 1)
                # Segment i covers math angles [start, start + seg]
                # (CCW from 3 o'clock) - the same convention the divider
                # lines, labels and winner lookup use. Kivy's Ellipse
                # measures angles CLOCKWISE from 12 o'clock, so convert:
                # kivy = 90 - math. Without this the colours spin the
                # opposite way to the lines/labels and only line up when
                # 90 deg is a multiple of the segment size.
                start = self.rotation_angle + i * seg
                Ellipse(
                    pos=(cx - R, cy - R),
                    size=(R * 2, R * 2),
                    angle_start=90.0 - (start + seg),
                    angle_end=90.0 - start,
                )

            # divider lines between segments
            Color(0, 0, 0, 0.35)
            for i in range(n):
                ang = math.radians(self.rotation_angle + i * seg)
                Line(points=[cx, cy,
                             cx + R * math.cos(ang),
                             cy + R * math.sin(ang)], width=1.2)

            # centre cap
            Color(0.10, 0.10, 0.12, 1)
            cap = R * 0.09
            Ellipse(pos=(cx - cap, cy - cap), size=(cap * 2, cap * 2))

            # pointer > at RIGHT edge (0° in Kivy = 3 o'clock)
            tip_x  = cx + R - 2
            base_x = cx + R + 28
            half   = 14
            Color(1, 0.15, 0.15, 1)
            Triangle(points=[base_x, cy,
                             tip_x, cy - half,
                             tip_x, cy + half])

            # outer ring
            Color(0.85, 0.85, 0.85, 0.4)
            Line(circle=(cx, cy, R), width=1.5)

        # text labels placed as Kivy widgets (no canvas rotation needed)
        for i, item in enumerate(self.items):
            mid_ang = math.radians(self.rotation_angle + i * seg + seg / 2)
            lx = cx + (R * 0.62) * math.cos(mid_ang)
            ly = cy + (R * 0.62) * math.sin(mid_ang)
            name = item["name"]
            short = name if len(name) <= 10 else name[:9] + "…"
            lbl = Label(text=short, size_hint=(None, None), size=(dp(88), dp(22)),
                        font_size=11, bold=True, color=(1, 1, 1, 1))
            lbl.pos = (lx - dp(44), ly - dp(11))
            self.add_widget(lbl)
            self._label_cache.append(lbl)

    # ── animation ───────────────────────────────────────────────────────────
    def animate_spin(self, delta, duration=6.0, on_complete=None):
        target = self.rotation_angle + delta
        anim = Animation(rotation_angle=target, duration=duration,
                         t="out_cubic")
        anim.bind(
            on_progress=lambda *a: self.redraw(),
            on_complete=lambda *a: (self.redraw(),
                                    on_complete() if on_complete else None),
        )
        anim.start(self)

    # ── result ───────────────────────────────────────────────────────────────
    def get_selected_index(self):
        """Which segment is under the pointer (0° / right side)?"""
        if not self.items:
            return None
        n   = len(self.items)
        seg = 360.0 / n
        # pointer at 0°; undo rotation to find which segment is there
        idx = int((-self.rotation_angle % 360) / seg) % n
        return idx


# ── Screen ────────────────────────────────────────────────────────────────────
class SpinScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._history = collections.deque(maxlen=30)
        self._spinning = False

        root = BoxLayout(orientation="vertical", padding=6, spacing=5)

        # ── mode toggle ──
        mode_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=8)
        mode_row.add_widget(Label(text="Mode:", size_hint_x=None,
                                  width=dp(50), font_size=13))
        self._mode_names = ToggleButton(text="Names", group="mode",
                                        state="down", size_hint_x=None,
                                        width=dp(90), font_size=13)
        self._mode_nums  = ToggleButton(text="Numbers", group="mode",
                                         size_hint_x=None, width=dp(90),
                                         font_size=13)
        self._mode_names.bind(on_release=lambda *a: self._switch_mode("names"))
        self._mode_nums.bind(on_release=lambda *a: self._switch_mode("numbers"))
        mode_row.add_widget(self._mode_names)
        mode_row.add_widget(self._mode_nums)
        root.add_widget(mode_row)

        # ── add / numbers row (swaps with mode) ──
        # Two rows: on a phone the old single row needed ~370dp of fixed
        # widths and squeezed the Name box down to nothing.
        self._add_row = BoxLayout(orientation="vertical", size_hint_y=None,
                                  height=dp(92), spacing=5)
        self._name_input   = TextInput(hint_text="Name", multiline=False,
                                       size_hint_y=None, height=dp(42))
        self._weight_input = TextInput(hint_text="Weight (1.0)",
                                       size_hint_x=0.3, multiline=False,
                                       input_filter="float")
        add_btn    = Button(text="Add",         size_hint_x=0.2)
        import_btn = Button(text="Import .txt", size_hint_x=0.3)
        clear_btn  = Button(text="Clear all",   size_hint_x=0.25)
        add_btn.bind(on_release=self._add_name)
        import_btn.bind(on_release=self._import_txt)
        clear_btn.bind(on_release=lambda *a: (self.wheel.clear(),
                                               self._refresh_list()))
        self._add_row.add_widget(self._name_input)
        row2 = BoxLayout(spacing=5, size_hint_y=None, height=dp(42))
        for w in (self._weight_input, add_btn, import_btn, clear_btn):
            row2.add_widget(w)
        self._add_row.add_widget(row2)
        root.add_widget(self._add_row)

        # ── numbers row (hidden initially) ──
        self._num_row = BoxLayout(size_hint_y=None, height=dp(40),
                                  spacing=5)
        self._num_row.add_widget(Label(text="Min:", size_hint_x=None,
                                        width=dp(40), font_size=13))
        self._num_min = TextInput(text="1", multiline=False,
                                   input_filter="int")
        self._num_row.add_widget(self._num_min)
        self._num_row.add_widget(Label(text="Max:", size_hint_x=None,
                                        width=dp(36), font_size=13))
        self._num_max = TextInput(text="10", multiline=False,
                                   input_filter="int")
        self._num_row.add_widget(self._num_max)
        fill_btn = Button(text="Fill wheel")
        fill_btn.bind(on_release=self._fill_numbers)
        self._num_row.add_widget(fill_btn)
        # not added yet — shown on mode switch

        # ── wheel ──
        self.wheel = WheelWidget(size_hint=(1, 0.52))
        root.add_widget(self.wheel)

        # ── name list ──
        sv = ScrollView(size_hint=(1, 0.16))
        self._list_grid = GridLayout(cols=1, spacing=2, size_hint_y=None)
        self._list_grid.bind(minimum_height=self._list_grid.setter("height"))
        sv.add_widget(self._list_grid)
        root.add_widget(sv)

        # ── spin + result ──
        bottom = BoxLayout(size_hint_y=None, height=dp(52), spacing=8)
        self._spin_btn = Button(text="Spin!", font_size=17)
        self._spin_btn.bind(on_release=self._spin)
        self._result_label = Label(text="", font_size=14)
        bottom.add_widget(self._spin_btn)
        bottom.add_widget(self._result_label)
        root.add_widget(bottom)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=lambda *a: setattr(self.manager, "current",
                                                 "dashboard"))
        root.add_widget(back)

        self.add_widget(root)
        self._current_mode = "names"

    # ── mode switching ───────────────────────────────────────────────────────
    def _switch_mode(self, mode):
        self._current_mode = mode
        if mode == "numbers":
            if self._add_row.parent:
                self._add_row.parent.remove_widget(self._add_row)
            # insert num_row after mode_row
            idx = self.children[0].children.index(self.wheel)
            self.children[0].add_widget(self._num_row,
                                         index=idx + 1)
        else:
            if self._num_row.parent:
                self._num_row.parent.remove_widget(self._num_row)
            idx = self.children[0].children.index(self.wheel)
            self.children[0].add_widget(self._add_row,
                                         index=idx + 1)

    def _fill_numbers(self, *a):
        try:
            lo = int(self._num_min.text)
            hi = int(self._num_max.text)
        except ValueError:
            return
        if lo > hi:
            lo, hi = hi, lo
        nums = list(range(lo, min(hi + 1, lo + 20)))  # cap at 20 segments
        self.wheel.clear()
        for n in nums:
            self.wheel.add_item(str(n), 1.0)
        self._refresh_list()

    # ── names mode ──────────────────────────────────────────────────────────
    def _add_name(self, *a):
        name = self._name_input.text.strip()
        try:
            w = float(self._weight_input.text) if self._weight_input.text.strip() else 1.0
        except ValueError:
            w = 1.0
        w = max(w, 0.01)   # zero/negative weights broke the weighted pick
        if name:
            self.wheel.add_item(name, w)
            self._name_input.text = ""
            self._weight_input.text = ""
            self._refresh_list()

    def _import_txt(self, *a):
        chooser = FileChooserIconView(path=_start_dir(),
                                       filters=["*.txt"], multiselect=False)
        btn = Button(text="Import", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Import names", content=layout,
                      size_hint=(0.9, 0.9))

        def _do(inst):
            if chooser.selection:
                try:
                    with open(chooser.selection[0], encoding="utf-8") as f:
                        for ln in f:
                            ln = ln.strip()
                            if ln and not any(it["name"] == ln
                                               for it in self.wheel.items):
                                self.wheel.add_item(ln, 1.0)
                    self._refresh_list()
                except Exception as e:
                    Popup(title="Error", content=Label(text=str(e)),
                          size_hint=(0.6, 0.4)).open()
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def _refresh_list(self):
        self._list_grid.clear_widgets()
        for idx, item in enumerate(self.wheel.items):
            row = BoxLayout(size_hint_y=None, height=dp(26))
            row.add_widget(Label(
                text=f"{item['name']}  (w={item['weight']})",
                halign="left", font_size=11))
            d = Button(text="x", size_hint_x=None, width=dp(34), font_size=11)
            d.bind(on_release=lambda inst, i=idx: (
                self.wheel.remove_index(i), self._refresh_list()))
            row.add_widget(d)
            self._list_grid.add_widget(row)

    # ── spin ─────────────────────────────────────────────────────────────────
    def _spin(self, *a):
        if self._spinning:
            return  # ignore rapid double-clicks - was letting two Animations
                    # race on the same rotation_angle property, so the
                    # displayed "winner" could disagree with where the
                    # wheel visually landed
        items = self.wheel.items
        if not items:
            Popup(title="Empty", content=Label(text="Add items first."),
                  size_hint=(0.55, 0.35)).open()
            return

        n   = len(items)
        seg = 360.0 / n

        # weighted pick
        weights = [it["weight"] for it in items]
        total   = sum(weights)
        r       = random.random() * total
        chosen  = n - 1
        acc     = 0.0
        for i, w in enumerate(weights):
            acc += w
            if r <= acc:
                chosen = i
                break

        # calculate delta so chosen lands at 0° (right/pointer)
        # after spin: rotation_angle_new + chosen*seg + seg/2 ≡ 0 (mod 360)
        # > rotation_angle_new = -(chosen*seg + seg/2 + jitter) mod 360
        jitter       = random.uniform(-seg * 0.28, seg * 0.28)
        current      = self.wheel.rotation_angle % 360
        target_rot   = (-(chosen * seg + seg / 2 + jitter)) % 360
        extra_spins  = random.randint(4, 8) * 360
        delta        = (target_rot - current) % 360 + extra_spins

        self.wheel.highlight_index = None
        self._result_label.text    = "Spinning…"
        self._spinning              = True
        self._spin_btn.disabled     = True

        def on_done():
            idx  = self.wheel.get_selected_index()
            self.wheel.highlight_index = idx
            self.wheel.redraw()
            name = items[idx]["name"] if idx is not None else "?"
            self._result_label.text = f"Winner: {name}"
            self._history.appendleft(name)
            self._spinning          = False
            self._spin_btn.disabled = False
            Popup(title="Result!",
                  content=Label(text=name, font_size=22, halign="center"),
                  size_hint=(0.55, 0.38)).open()

        self.wheel.animate_spin(
            delta,
            duration=5.5 + random.random() * 2.5,
            on_complete=on_done,
        )
