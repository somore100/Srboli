# tests/test_feedback_popup.py - needs a display. Nothing is sent: send_report is replaced.
import os, sys, time
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
import screens.feedback_popup as fp

def pump(cond, secs=15):
    end = time.time() + secs
    while not cond() and time.time() < end:
        EventLoop.idle(); time.sleep(0.02)
    assert cond(), "timed out"

sent = []
class R: ok, message, method = True, "Thank you! Your feedback was sent.", "relay"
fp.send_report = lambda cfg, rep: (sent.append(rep), R)[1]

p = fp.FeedbackPopup(); p.open(); EventLoop.idle()
assert not p.sys_box.active and p.sys_lbl.text == ""          # off by default
p._send(); assert not sent and "title" in p.status.text.lower()  # required fields enforced
p.title_in.text = "UI is not working"; p.desc_in.text = "Settings shows nothing at all."
p.type_sp.text = "Question"

# ticking shows exactly what will be sent; unticking drops it
p.sys_box.active = True
pump(lambda: p._sys)
assert "OS:" in p.sys_lbl.text and "CPU:" in p.sys_lbl.text
p.sys_box.active = False
assert p._sys == {} and p.sys_lbl.text == ""

p._send(); pump(lambda: sent)
rep = sent[0]
assert rep.type_label == "Question" and rep.system == {} and rep.title == "UI is not working"
pump(lambda: p._closed)                                       # closes after success

# with the box ticked, the specs go along
sent.clear(); p2 = fp.FeedbackPopup(); p2.open()
p2.title_in.text = "Crash on startup"; p2.desc_in.text = "It closes right away."
p2.sys_box.active = True; pump(lambda: p2._sys)
p2._send(); pump(lambda: sent); assert "OS" in sent[0].system
print("feedback popup OK")
