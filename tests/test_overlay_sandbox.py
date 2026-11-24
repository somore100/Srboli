# tests/test_overlay_sandbox.py - xvfb-run -a python3 tests/test_overlay_sandbox.py  (kivy screens.)
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from screens import overlay_sandbox_screen as OS
from core import macro_core as mc


class T:
    _n = 0
    def __init__(self, x, y):
        T._n += 1
        self.uid = T._n; self.pos = (x, y); self.x, self.y = x, y; self.grab_current = None
    def grab(self, w): self.grab_current = w
    def ungrab(self, w): self.grab_current = None
    def move(self, x, y): self.pos = (x, y); self.x, self.y = x, y


fails = 0
def check(name, cond, info=""):
    global fails
    if not cond:
        fails += 1; print("FAIL", name, info)


tmp = tempfile.mkdtemp()
Window.size = (1200, 1000)
scr = OS.OverlaySandboxScreen()
scr._folder = lambda: tmp
sb = scr.sb
sb.folder_fn = lambda: tmp
Window.add_widget(scr); scr.size = Window.size
for _ in range(6): Clock.tick()
check("sandbox sized", sb.width > 500 and sb.height > 500, sb.size)


def tap(x, y):
    t = T(x, y); sb.on_touch_down(t); sb.on_touch_up(t)


def drag(a, b, steps=1):
    t = T(*a); sb.on_touch_down(t); t.move(*b); sb.on_touch_move(t); sb.on_touch_up(t)


# ---- bubbles -------------------------------------------------------------------
m = sb.bubbles["master"]
check("master bubble present", m is not None and "master" in sb.bubbles)
tap(*m.center)
check("tap opens radial menu", len(sb.menu_items) == 3)
tap(*m.center)
check("tap again closes it", not sb.menu_items)
tap(*m.center)
tap(sb.x + 5, sb.y + 5)
check("tap elsewhere closes menu", not sb.menu_items)

start = m.center
drag(start, (sb.x + 100, sb.y + sb.height * 0.5))
check("drag moves bubble and snaps to the left edge", m.center_x < sb.center_x and m.fx == 0.05, (m.fx, m.fy))
check("X target removed afterwards", sb.xt is None)

t = T(*m.center); sb.on_touch_down(t); t.move(m.center_x + 30, m.center_y + 30); sb.on_touch_move(t)
check("X target shown while dragging", sb.xt is not None)
t.move(sb.center_x, sb.y + dp(70)); sb.on_touch_move(t)
check("X highlights when hovered", sb.xt.hot)
sb.on_touch_up(t)
check("dropping on X dismisses the bubble", "master" not in sb.bubbles and sb.xt is None)
scr.btns["master"].dispatch("on_release")
check("Master button brings it back", "master" in sb.bubbles)

# ---- calculator ----------------------------------------------------------------
cb = sb.show_bubble("calc")
tap(*cb.center)
check("calc bubble opens panel", sb.calc is not None)
p = sb.calc
for k in ["1", "2", "+", "3", "="]:
    p.press(k)
check("calculator works", p.disp.text == "15", p.disp.text)
p.press("*"); check("operator shown", "×" in p.expr.text or p.expr.text.endswith("×"), p.expr.text)
p.press("C"); p.press("5"); p.press("sqrt")
check("sqrt", p.disp.text.startswith("2.23606"), p.disp.text)
x0, y0 = p.pos
t = T(p.x + 20, p.top - 10); sb.on_touch_down(t); t.move(p.x + 120, p.top - 90); sb.on_touch_move(t); sb.on_touch_up(t)
check("panel dragged by title", p.x > x0 + 50 and p.y < y0 - 40, (x0, y0, p.pos))
t = T(-500, -500); p.pos = (sb.x + 5, sb.y + 5); t = T(p.x + 20, p.top - 10)
sb.on_touch_down(t); t.move(-900, -900); sb.on_touch_move(t); sb.on_touch_up(t)
check("panel kept on screen", p.x >= sb.x and p.y >= sb.y)
scr.btns["panel"].dispatch("on_release")
check("calc toggles closed", sb.calc is None)
tap(*cb.center); check("tap reopens", sb.calc is not None)
sb.close_calc()

# ---- radial menu launches tools --------------------------------------------------------
m = sb.bubbles["master"]
tap(*m.center)
items = list(sb.menu_items)
tap(*items[1].center)
check("menu Macro opens macro tool and closes menu", sb.macro is not None and not sb.menu_items)
sb.close_macro()
tap(*m.center); tap(*sb.menu_items[2].center)
check("menu Rec spawns recorder bubble", "rec" in sb.bubbles)

# ---- macro tool ------------------------------------------------------------------------
ov = sb.open_macro()
for _ in range(2): Clock.tick()
check("toolbar on right", ov.toolbar.right <= sb.right and ov.toolbar.x > sb.center_x)
check("settings start minimised", not ov.settings_open and ov.panel.parent is None)
ov.btn["set"].dispatch("on_release")
check("settings open", ov.panel.parent is ov)
ov.btn["set"].dispatch("on_release")
check("settings minimise", ov.panel.parent is None)
ov.btn["click"].dispatch("on_release")
ov.btn["drag"].dispatch("on_release")
ov.btn["click"].dispatch("on_release")
check("actions added", [a["kind"] for a in ov.macro.actions] == ["click", "drag", "click"])
check("markers: 1 + 2 + 1", len(ov.markers) == 4 and [mk.kind for mk in ov.markers] == ["click", "start", "end", "click"])
ov.btn["undo"].dispatch("on_release")
check("remove previous", len(ov.macro.actions) == 2 and len(ov.markers) == 3)

mk = ov.markers[0]
cx, cy = mk.center
t = T(cx, cy); sb.on_touch_down(t); t.move(cx + 200, cy + 100); sb.on_touch_move(t); sb.on_touch_up(t)
a0 = ov.macro.actions[0]
check("marker drag updates action", abs(a0["x"] - ov.frac_of(cx + 200, cy + 100)[0]) < 0.01 and ov.popup is None, a0)
end = ov.markers[2]
t = T(*end.center); sb.on_touch_down(t); t.move(end.center_x - 50, end.center_y + 40); sb.on_touch_move(t); sb.on_touch_up(t)
check("drag end marker updates x2", abs(ov.macro.actions[1]["x2"] - ov.frac_of(*end.center)[0]) < 0.01)

mk = ov.markers[0]
tap(*mk.center)
check("tap marker opens editor", ov.popup is not None and "Edit Action 1" in ov.popup.title)
ov.popup.dismiss()
ov.edit(1)
check("drag editor has two rows", set(ov._fields) == {"interval", "duration"})
ov.popup.dismiss()
check("apply interval seconds", ov.apply_edit(0, "2", "seconds") and ov.macro.actions[0]["interval_ms"] == 2000)
check("apply drag duration", ov.apply_edit(1, "300", "ms", "1", "seconds") and ov.macro.actions[1]["duration_ms"] == 1000
      and ov.macro.actions[1]["interval_ms"] == 300)
ov.edit(0)
t_, s_ = ov._fields["interval"]
t_.text, s_.text = "750", "ms"
ov._done_edit(0)
check("Done applies fields", ov.macro.actions[0]["interval_ms"] == 750)
ov.edit(1); ov.remove_action(1)
check("Remove Action", len(ov.macro.actions) == 1 and len(ov.markers) == 1)

ov.btn["eye"].dispatch("on_release")
check("eye hides markers", ov.hidden and ov.markers[0].opacity == 0 and ov.btn["eye"].text == "Show")
ov.btn["eye"].dispatch("on_release")
check("eye shows again", not ov.hidden and ov.markers[0].opacity == 1)

ov.loops_in.text = "3"; ov.speed_sp.text = "2x"; ov.name_in.text = "Demo run"
check("settings apply", ov.macro.loops == 3 and ov.macro.speed == 2.0 and ov.macro.name == "Demo run")
path = ov.save()
check("save writes file", path and os.path.exists(path) and path.endswith("Demo run.macro.json"), path)
ov.btn["undo"].dispatch("on_release")
check("emptied", not ov.macro.actions)
ov.load_file("Demo run.macro.json")
check("load restores", len(ov.macro.actions) == 1 and ov.macro.loops == 3 and ov.speed_sp.text == "2x")
ov.open_saved(); check("saved list opens", ov.popup is not None); ov.popup.dismiss()

# ---- playback hits the fake apps -------------------------------------------------------
sb.targets.reset()
tile = sb.targets.tile_rects()[0]
ov.macro.actions[0].update(x=ov.frac_of(tile[0] + tile[2] / 2, tile[1] + tile[3] / 2)[0],
                           y=ov.frac_of(tile[0] + tile[2] / 2, tile[1] + tile[3] / 2)[1])
ov.macro.set_loops(1)
ov.start()
check("running turns markers green", ov.running and ov.btn["run"].text == "Stop")
ov.stop()
check("stop cancels", not ov.running and not ov._handles and ov.btn["run"].text == "Run")
ov.start()
ov.fire(mc.plan(ov.macro, sb.width, sb.height)[0])
check("playback taps tile A", sb.targets.counts[0] == 1, sb.targets.counts)
ov.stop()
ov.add_drag()
a = ov.macro.actions[-1]
chip = sb.targets.chip_rect()
ov.macro.update(len(ov.macro.actions) - 1, x=ov.frac_of(chip[0] + 5, chip[1] + 5)[0], y=ov.frac_of(chip[0] + 5, chip[1] + 5)[1],
                x2=0.9, y2=ov.frac_of(0, chip[1])[1])
ov.running = True
ov.fire([e for e in mc.plan(ov.macro, sb.width, sb.height) if e[1] == "drag"][0])
check("playback drag moves chip", sb.targets.chip_f > 0.5, sb.targets.chip_f)
ov.running = False
ov.fire(mc.plan(ov.macro, sb.width, sb.height)[0])
check("fire ignored when stopped", sb.targets.counts[0] == 1)
ov.btn["undo"].dispatch("on_release"); ov.btn["undo"].dispatch("on_release")
ov.btn["run"].dispatch("on_release")
check("empty macro will not run", not ov.running)
ov.btn["click"].dispatch("on_release")
ov.macro.set_loops(0)
ov.start(); ov._pass_done(0)
check("loops 0 reschedules", ov.running and ov._handles)
ov.btn["undo"].dispatch("on_release") if False else None
ov.stop()
ov.btn["quit"].dispatch("on_release")
check("quit closes macro tool", sb.macro is None)

# manual interaction with the fake apps
sb.targets.reset()
tile = sb.targets.tile_rects()[1]
tap(tile[0] + 5, tile[1] + 5)
check("manual tap counted", sb.targets.counts[1] == 1)
chip = sb.targets.chip_rect()
drag((chip[0] + 5, chip[1] + 5), (sb.right - 20, chip[1] + 5))
check("manual chip drag", sb.targets.chip_f > 0.9, sb.targets.chip_f)

# ---- simulated recorder ----------------------------------------------------------------
rb = sb.bubbles["rec"]
tap(*rb.center)
check("recorder setup dialog", sb.popup is not None and sb.popup.title == "Recording Setup")
sb.start_recording()
check("recording state", sb.rec == 0 and rb.lab.text == "00:00")
sb._tick_rec(1); sb._tick_rec(1)
check("timer counts", rb.lab.text == "00:02")
tap(*rb.center)
check("tap stops recording", sb.rec is None and rb.lab.text == "Rec" and "Simulated" in sb.toast.text)
sb.start_recording(); sb.dismiss_bubble("rec")
check("dismissing the bubble stops recording", sb.rec is None and sb._rec_ev is None)

# ---- reset / resize --------------------------------------------------------------------
sb.open_macro(); sb.open_calc(); sb.reset()
check("reset closes tools", sb.macro is None and sb.calc is None and sb.targets.counts == [0] * 6)
Window.size = (700, 900)
for _ in range(4): Clock.tick()
cbub = sb.show_bubble("calc")
check("bubbles stay inside after resize", sb.x <= cbub.x and cbub.right <= sb.right + 1)

print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
