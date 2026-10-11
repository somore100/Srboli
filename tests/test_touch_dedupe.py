# tests/test_touch_dedupe.py - pure logic, no display needed.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.touch_dedupe import TouchDeduper


class ME:
    _n = 0

    def __init__(self, dev, x, y):
        self.device, self.sx, self.sy = dev, x, y
        ME._n += 1
        self.uid = ME._n


d = TouchDeduper()
finger, ghost = ME("sdl", .5, .5), ME("mouse", .502, .499)
assert not d.should_drop("begin", finger, now=1.00)
assert d.should_drop("begin", ghost, now=1.01)              # duplicate
assert d.should_drop("update", ghost, now=1.02)
assert not d.should_drop("update", finger, now=1.02)
assert d.should_drop("end", ghost, now=1.05)
assert not d.should_drop("end", finger, now=1.05)
assert not d.should_drop("begin", ME("mouse", .5, .5), now=1.4)   # later tap
a, b = ME("sdl", .8, .2), ME("sdl", .2, .8)                  # 2 fingers
assert not d.should_drop("begin", a, now=2.0)
assert not d.should_drop("begin", b, now=2.0)
g = ME("sdl", .5, .5)
d.should_drop("begin", g, now=3.0)
assert not d.should_drop("begin", ME("mouse", .9, .1), now=3.01)  # far away
assert d.count == 1
# a broken event must disable the filter, not raise
class Bad: uid = 999; device = "x"
assert d.should_drop("begin", Bad(), now=9.0) is False and d.disabled
assert not d.should_drop("begin", ME("sdl", .1, .1), now=9.1)   # now inert
print("touch dedupe tests passed")
