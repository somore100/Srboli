# screens/shape_generator_screen.py
# Fixed: re-generate works every time, style mixing added

import os
import math
import random
import colorsys

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Ellipse, Triangle, Rectangle
from kivy.clock import Clock
from kivy.metrics import dp

import app_data

STYLES = ["geometric", "organic", "mandala", "circuit"]

PALETTE_MODES = ["analogous", "complementary", "triadic", "mono"]


def _make_palette(base_hue, mode, rng):
    offsets = {
        "analogous":     [-0.08, -0.04, 0, 0.04, 0.08],
        "complementary": [0, 0.02, 0.5, 0.52],
        "triadic":       [0, 1/3, 2/3],
        "mono":          [0, 0, 0, 0],
    }.get(mode, [0])
    return [
        colorsys.hsv_to_rgb((base_hue + o) % 1.0,
                            rng.uniform(0.55, 1.0),
                            rng.uniform(0.65, 1.0))
        for o in offsets
    ]


class ShapeSpec:
    def __init__(self):
        self.seed      = 0
        self.styles    = ["geometric"]
        self.palette   = []
        self.shapes    = []
        self.bg_color  = (0.05, 0.05, 0.08)

    def generate(self, styles, complexity, seed=None):
        import random as _r
        import os as _os
        if seed is None:
            # Use os.urandom for true randomness, not affected by any state
            seed = int.from_bytes(_os.urandom(4), "big") % 1000000
        self.seed   = seed
        self.styles = styles
        rng = _r.Random(self.seed)

        base_hue  = rng.random()
        pal_mode  = rng.choice(PALETTE_MODES)
        self.palette   = _make_palette(base_hue, pal_mode, rng)
        self.bg_color  = colorsys.hsv_to_rgb(base_hue, 0.3, 0.10)

        n = max(5, int(complexity * 22))
        self.shapes = []

        # distribute shapes across selected styles
        per_style = max(1, n // len(styles))
        for style in styles:
            getattr(self, f"_gen_{style}")(rng, per_style)

    def _gen_geometric(self, rng, n):
        for _ in range(n):
            self.shapes.append({
                "kind":    rng.choice(["rect","circle","triangle","line","ring"]),
                "cx":      rng.uniform(0.05, 0.95),
                "cy":      rng.uniform(0.05, 0.95),
                "size":    rng.uniform(0.03, 0.26),
                "color":   rng.choice(self.palette),
                "alpha":   rng.uniform(0.30, 0.95),
                "angle":   rng.uniform(0, 360),
                "stroke":  rng.random() < 0.4,
                "stroke_w":rng.uniform(1, 3.5),
            })

    def _gen_organic(self, rng, n):
        for _ in range(n):
            self.shapes.append({
                "kind":    "circle",
                "cx":      rng.uniform(0.05, 0.95),
                "cy":      rng.uniform(0.05, 0.95),
                "size":    rng.uniform(0.03, 0.32),
                "color":   rng.choice(self.palette),
                "alpha":   rng.uniform(0.12, 0.55),
                "angle":   0, "stroke": False, "stroke_w": 1,
            })
        for _ in range(max(1, n // 3)):
            self.shapes.append({
                "kind": "line2",
                "x1": rng.random(), "y1": rng.random(),
                "x2": rng.random(), "y2": rng.random(),
                "color":   rng.choice(self.palette),
                "alpha":   rng.uniform(0.3, 0.85),
                "stroke_w":rng.uniform(1, 2.5),
            })

    def _gen_mandala(self, rng, n):
        arms   = rng.choice([4, 6, 8, 12])
        layers = max(2, n // arms)
        for layer in range(layers):
            r     = (layer + 1) / (layers + 1) * 0.44
            color = rng.choice(self.palette)
            alpha = rng.uniform(0.5, 0.95)
            for arm in range(arms):
                angle = (arm / arms) * 360
                self.shapes.append({
                    "kind":    rng.choice(["circle","rect","triangle","ring"]),
                    "cx":      0.5 + r * math.cos(math.radians(angle)),
                    "cy":      0.5 + r * math.sin(math.radians(angle)),
                    "size":    r * rng.uniform(0.08, 0.20),
                    "color":   color, "alpha": alpha,
                    "angle":   angle + rng.uniform(-15, 15),
                    "stroke":  rng.random() < 0.4, "stroke_w": 1.5,
                })
        self.shapes.append({
            "kind":"circle","cx":0.5,"cy":0.5,
            "size":0.035,"color":self.palette[0],
            "alpha":1.0,"angle":0,"stroke":False,"stroke_w":1,
        })

    def _gen_circuit(self, rng, n):
        grid  = 0.1
        nodes = [(round(rng.uniform(0,1)/grid)*grid,
                  round(rng.uniform(0,1)/grid)*grid) for _ in range(n)]
        for i in range(len(nodes)-1):
            x1,y1 = nodes[i]; x2,y2 = nodes[i+1]
            self.shapes.append({
                "kind":"line2","x1":x1,"y1":y1,"x2":x2,"y2":y2,
                "color":rng.choice(self.palette),
                "alpha":rng.uniform(0.6,1.0),
                "stroke_w":rng.uniform(1.5,3.5),
            })
        for x,y in nodes:
            self.shapes.append({
                "kind":"circle","cx":x,"cy":y,
                "size":rng.uniform(0.007,0.022),
                "color":rng.choice(self.palette),
                "alpha":1.0,"angle":0,"stroke":False,"stroke_w":1,
            })


class ShapeCanvas(Widget):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.spec = None
        self.bind(pos=self._redraw, size=self._redraw)

    def set_spec(self, spec):
        self.spec = spec
        self._redraw()

    def _redraw(self, *a):
        self.canvas.clear()
        if not self.spec or not self.spec.shapes:
            return
        s   = self.spec
        w,h = self.size
        x0,y0 = self.pos

        with self.canvas:
            Color(*s.bg_color, 1)
            Rectangle(pos=self.pos, size=self.size)

            for sh in s.shapes:
                Color(*sh["color"], sh.get("alpha", 1.0))
                kind = sh["kind"]

                if kind == "line2":
                    x1 = x0+sh["x1"]*w; y1 = y0+sh["y1"]*h
                    x2 = x0+sh["x2"]*w; y2 = y0+sh["y2"]*h
                    Line(points=[x1,y1,x2,y2], width=sh.get("stroke_w",1.5))
                    continue

                cx = x0+sh["cx"]*w; cy = y0+sh["cy"]*h
                sz = sh["size"]*min(w,h)
                stroke = sh.get("stroke", False)
                sw     = sh.get("stroke_w", 1.5)

                if kind in ("circle","ring"):
                    if stroke or kind=="ring":
                        Line(circle=(cx,cy,sz), width=sw)
                    else:
                        Ellipse(pos=(cx-sz,cy-sz), size=(sz*2,sz*2))
                elif kind == "rect":
                    hw = sz; hh = sz*0.85
                    if stroke:
                        Line(rectangle=(cx-hw,cy-hh,hw*2,hh*2), width=sw)
                    else:
                        Rectangle(pos=(cx-hw,cy-hh), size=(hw*2,hh*2))
                elif kind == "triangle":
                    ang = math.radians(sh.get("angle",0))
                    pts = []
                    for i in range(3):
                        a = ang + i*(2*math.pi/3)
                        pts += [cx+sz*math.cos(a), cy+sz*math.sin(a)]
                    if stroke:
                        Line(points=pts+pts[:2], width=sw)
                    else:
                        Triangle(points=pts)
                elif kind == "line":
                    ang = math.radians(sh.get("angle",0))
                    Line(points=[cx-sz*math.cos(ang), cy-sz*math.sin(ang),
                                 cx+sz*math.cos(ang), cy+sz*math.sin(ang)],
                         width=sw)

    def export_png(self, path):
        try:
            self.export_to_png(path)
            return True
        except Exception as e:
            print("PNG export:", e)
            return False

    def export_svg(self, path):
        if not self.spec:
            return False
        W = H = 512
        def _rgb(c):
            return f"rgb({int(c[0]*255)},{int(c[1]*255)},{int(c[2]*255)})"
        bg = _rgb(self.spec.bg_color)
        lines = [f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{W}" height="{H}" style="background:{bg}">']
        for sh in self.spec.shapes:
            col  = _rgb(sh["color"])
            a    = sh.get("alpha",1.0)
            kind = sh["kind"]
            if kind == "line2":
                x1=sh["x1"]*W; y1=(1-sh["y1"])*H
                x2=sh["x2"]*W; y2=(1-sh["y2"])*H
                lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" '
                              f'x2="{x2:.1f}" y2="{y2:.1f}" '
                              f'stroke="{col}" stroke-width="{sh["stroke_w"]:.1f}" '
                              f'opacity="{a:.2f}"/>')
                continue
            cx=sh["cx"]*W; cy=(1-sh["cy"])*H; sz=sh["size"]*W
            stroke=sh.get("stroke",False)
            sw=sh.get("stroke_w",1.5)
            fill=col if not stroke else "none"
            scol=col if stroke else "none"
            if kind in ("circle","ring"):
                fill = "none" if kind=="ring" else fill
                scol = col if kind=="ring" else scol
                lines.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{sz:.1f}" '
                              f'fill="{fill}" stroke="{scol}" '
                              f'stroke-width="{sw:.1f}" opacity="{a:.2f}"/>')
            elif kind=="rect":
                hw=sz; hh=sz*0.85
                lines.append(f'<rect x="{cx-hw:.1f}" y="{cy-hh:.1f}" '
                              f'width="{hw*2:.1f}" height="{hh*2:.1f}" '
                              f'fill="{fill}" stroke="{scol}" '
                              f'stroke-width="{sw:.1f}" opacity="{a:.2f}"/>')
            elif kind=="triangle":
                ang=math.radians(sh.get("angle",0))
                pts=" ".join(f"{cx+sz*math.cos(ang+i*2*math.pi/3):.1f},"
                             f"{cy+sz*math.sin(ang+i*2*math.pi/3):.1f}"
                             for i in range(3))
                lines.append(f'<polygon points="{pts}" fill="{fill}" '
                              f'stroke="{scol}" stroke-width="{sw:.1f}" '
                              f'opacity="{a:.2f}"/>')
        lines.append("</svg>")
        try:
            with open(path,"w",encoding="utf-8") as f:
                f.write("\n".join(lines))
            return True
        except Exception as e:
            print("SVG:", e); return False


class ShapeGeneratorScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._history    = []
        self._hist_index = -1

        root = BoxLayout(orientation="vertical", padding=6, spacing=5)

        # ── controls ──────────────────────────────────────────────────────
        ctrl = BoxLayout(size_hint_y=None, height=dp(40), spacing=5)
        ctrl.add_widget(Label(text="Style(s):", size_hint_x=None,
                              width=dp(58), font_size=13))

        # style checkboxes
        self._style_cbs = {}
        for s in STYLES:
            cb = CheckBox(active=(s == "geometric"),
                          size_hint_x=None, size=(dp(22), dp(22)))
            ctrl.add_widget(cb)
            ctrl.add_widget(Label(text=s.capitalize(), size_hint_x=None,
                                  width=dp(78), font_size=12))
            self._style_cbs[s] = cb

        ctrl.add_widget(Label(text="Cmplx:", size_hint_x=None,
                              width=dp(50), font_size=12))
        self._complexity = Slider(min=0.1, max=1.0, value=0.5,
                                  size_hint_x=None, width=dp(110))
        ctrl.add_widget(self._complexity)

        self._seed_input = TextInput(hint_text="Seed", multiline=False,
                                     input_filter="int", size_hint_x=None,
                                     width=dp(90), font_size=12)
        ctrl.add_widget(self._seed_input)

        gen_btn = Button(text=" Generate", size_hint_x=None, width=dp(110),
                         font_size=14)
        gen_btn.bind(on_release=self._generate)
        ctrl.add_widget(gen_btn)
        root.add_widget(ctrl)

        # ── canvas ──────────────────────────────────────────────────────────
        self._canvas_w = ShapeCanvas()
        root.add_widget(self._canvas_w)

        # ── bottom ──────────────────────────────────────────────────────────
        bot = BoxLayout(size_hint_y=None, height=dp(44), spacing=5)
        prev_btn = Button(text="<", size_hint_x=None, width=dp(44))
        prev_btn.bind(on_release=self._hist_back)
        self._hist_lbl = Label(text="0/0", size_hint_x=None, width=dp(50),
                               font_size=12)
        next_btn = Button(text=">", size_hint_x=None, width=dp(44))
        next_btn.bind(on_release=self._hist_fwd)
        png_btn = Button(text="Save PNG", size_hint_x=None, width=dp(80))
        png_btn.bind(on_release=self._save_png)
        svg_btn = Button(text="Save SVG", size_hint_x=None, width=dp(80))
        svg_btn.bind(on_release=self._save_svg)
        self._seed_lbl = Label(text="Seed: —", font_size=11)
        back_btn = Button(text="< Back", size_hint_x=None, width=dp(90))
        back_btn.bind(on_release=self._go_back)
        for w in (prev_btn, self._hist_lbl, next_btn,
                  png_btn, svg_btn, self._seed_lbl, back_btn):
            bot.add_widget(w)
        root.add_widget(bot)
        self.add_widget(root)

        Clock.schedule_once(lambda dt: self._generate(), 0.4)

    def _get_styles(self):
        s = [name for name, cb in self._style_cbs.items() if cb.active]
        return s if s else ["geometric"]

    def _generate(self, *a):
        seed_txt = self._seed_input.text.strip()
        seed = int(seed_txt) if seed_txt.isdigit() else None
        # Always clear seed input so next click is fresh
        self._seed_input.text = ""

        import random as _rng
        spec = ShapeSpec()
        spec.generate(
            styles=self._get_styles(),
            complexity=self._complexity.value,
            seed=seed,  # None = fresh random each time
        )
        self._history = self._history[:self._hist_index + 1]
        self._history.append(spec)
        self._hist_index = len(self._history) - 1
        self._apply(spec)

    def _apply(self, spec):
        self._canvas_w.set_spec(spec)
        self._seed_lbl.text = f"Seed: {spec.seed}"
        # Only update seed input when navigating history, not after generating
        # (writing it back would cause reuse on next Generate click)
        n = len(self._history)
        self._hist_lbl.text = f"{self._hist_index+1}/{n}"

    def _hist_back(self, *a):
        if self._hist_index > 0:
            self._hist_index -= 1
            self._apply(self._history[self._hist_index])

    def _hist_fwd(self, *a):
        if self._hist_index < len(self._history) - 1:
            self._hist_index += 1
            self._apply(self._history[self._hist_index])

    def _save_png(self, *a):
        self._pick_save(".png", lambda p: (
            self._canvas_w.export_png(p),
            self._popup("Saved", p)
        ))

    def _save_svg(self, *a):
        self._pick_save(".svg", lambda p: (
            self._canvas_w.export_svg(p),
            self._popup("Saved", p)
        ))

    def _pick_save(self, ext, cb):
        chooser = FileChooserIconView(path=app_data.get_data_dir())
        name_in = TextInput(
            text=f"srboli_shape_{self._canvas_w.spec.seed if self._canvas_w.spec else 0}{ext}",
            multiline=False, size_hint_y=None, height=dp(36), font_size=13)
        save_btn = Button(text="Save", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=4)
        layout.add_widget(chooser)
        layout.add_widget(name_in)
        layout.add_widget(save_btn)
        popup = Popup(title="Save", content=layout, size_hint=(0.92, 0.92))

        def _do(*a):
            path = os.path.join(chooser.path, name_in.text.strip())
            popup.dismiss()
            cb(path)

        save_btn.bind(on_release=_do)
        popup.open()

    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=str(msg)),
              size_hint=(0.72, 0.36)).open()

    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"
