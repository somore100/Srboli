# The mini player builds, plays, pauses, loops, seeks and closes (fake sound).
# needs kivy and a display (CI skips it: tests/test_scripts.py looks for the word "kivy")
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from core import theme; theme.install()
from core.mini_player import MiniPlayer

class Snd:
    length, state, volume, loop, pos, unloaded = 171.0, "stop", 1.0, False, 11.0, False
    def play(self): self.state = "play"
    def stop(self): self.state = "stop"
    def seek(self, p): self.pos = p
    def get_pos(self): return self.pos
    def unload(self): self.unloaded = True

snd, opened, closed = Snd(), [], []
mp = MiniPlayer("/x/song.mp3", "song.mp3", on_open_in_app=lambda: opened.append(1),
                on_close=lambda: closed.append(1), loader=lambda p: snd)
mp.show()
assert snd.state == "play" and mp.seek.max == 171.0
mp._tick(0); assert mp.time.text == "00:11 / 02:51", mp.time.text
mp.toggle(); assert snd.state == "stop" and mp.play_btn.text == "Play"
mp.toggle(); assert snd.state == "play" and snd.pos == 11.0 and mp.play_btn.text == "Pause"
mp.toggle_loop(); assert snd.loop and mp.loop_btn.text == "Loop: on"
mp.set_volume(0.3); assert abs(snd.volume - 0.3) < 1e-6
assert mp.vol_lbl.text.endswith("%")
mp.set_collapsed(True); assert mp.collapsed and mp.fold_btn.text == "^"
mp.set_collapsed(False); assert not mp.collapsed
mp.open_in_app(); assert opened == [1] and snd.unloaded
# folder with other sounds: next-track + the checkbox
import shutil
folder = tempfile.mkdtemp()
for n in ("a.mp3", "b.mp3", "c.txt"): open(os.path.join(folder, n), "w").close()
from core import mini_player as mpl
assert [os.path.basename(x) for x in mpl.siblings(os.path.join(folder, "a.mp3"))] == ["a.mp3", "b.mp3"]
assert os.path.basename(mpl.next_sibling(os.path.join(folder, "a.mp3"))) == "b.mp3"
assert mpl.next_sibling(os.path.join(folder, "b.mp3")) is None
assert os.path.basename(mpl.next_sibling(os.path.join(folder, "b.mp3"), loop=True)) == "a.mp3"
assert mpl.siblings("/nonexistent/x.mp3") == []
assert mpl.clean_title("【imase】NIGHT DANCER（MV）") == "[imase]NIGHT DANCER(MV)"
snd3 = Snd()
mp3 = MiniPlayer(os.path.join(folder, "a.mp3"), "a.mp3", on_open_in_app=lambda: None, loader=lambda p: snd3)
assert mp3.auto_cb is not None and mp3._autonext is False
mp3.show(); mp3.auto_cb.active = True; snd3.state = "stop"; mp3._tick(0)
assert mp3.path.endswith("b.mp3"), mp3.path
mp3.close()
mp2 = MiniPlayer("/x/bad.mp3", "bad", on_open_in_app=lambda: None, loader=lambda p: None)
mp2.show(); assert "Can't play" in mp2.time.text; mp2.close()
print("mini player OK")
