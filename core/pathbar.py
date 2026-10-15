# core/pathbar.py
# Adds a "type / paste a path" bar + quick-jump buttons to EVERY
# FileChooserIconView in the app, without touching the ~30 call sites.
#
# install() swaps `kivy.uix.filechooser.FileChooserIconView` for a subclass
# BEFORE any screen module does `from kivy.uix.filechooser import
# FileChooserIconView`. When the chooser is put into a vertical BoxLayout
# (every picker in the app does this), the subclass inserts the bar above
# itself. Callers still use .path / .selection / on_submit exactly as before.
#
# The bar also shows WHY a list is empty ("Can't read this folder" vs
# "Empty folder"), which a bare FileChooser never says.

import os

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core.android_storage import shared_storage_root

_installed = False
_TREE_MODE = [False]      # remembered for the session: history vs folder levels


def _is_android():
    from core.android_storage import ON_ANDROID
    return ON_ANDROID


def allowed_roots():
    """Folders the picker may stay inside. On Android, "/", "/storage" and
    "/storage/emulated" can't be listed by apps (EACCES): walking up into them
    left the picker on a stale, empty list. Elsewhere: no restriction."""
    if not _is_android():
        return None
    from core.android_storage import shared_storage_root, removable_volumes
    roots = [os.path.abspath(shared_storage_root())]
    roots += [os.path.abspath(p) for _, p in removable_volumes()]
    return roots


def inside_allowed(path, roots):
    if roots is None:
        return True
    p = os.path.abspath(path)
    return any(p == r or p.startswith(r.rstrip(os.sep) + os.sep)
               for r in roots)


def _fs_root(path):
    """'/' on Linux/mac/Android, the drive root (C:\\) on Windows."""
    if os.name == "nt":
        drive = os.path.splitdrive(os.path.abspath(path or "."))[0]
        return (drive or "C:") + "\\"
    return "/"


def _clean(text):
    t = (text or "").strip().strip("\"'")
    if not t:
        return ""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(t)))


def folder_state(path):
    """('ok'|'empty'|'denied'|'missing', None) without listing the folder."""
    if not os.path.isdir(path):
        return "missing"
    if not os.access(path, os.R_OK | os.X_OK):
        return "denied"
    try:
        with os.scandir(path) as it:
            for _ in it:
                return "ok"
        return "empty"
    except PermissionError:
        return "denied"
    except OSError:
        return "denied"


class PathBar(BoxLayout):
    def __init__(self, chooser, **kw):
        super().__init__(orientation="vertical", size_hint_y=None,
                         height=dp(40) + dp(34) + dp(18), **kw)
        self._chooser = chooser

        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self._input = TextInput(
            multiline=False, write_tab=False, font_size=13,
            hint_text="Type or paste a folder path",
            foreground_color=(1, 1, 1, 1), hint_text_color=(0.6, 0.6, 0.6, 1),
            background_color=(0.12, 0.12, 0.12, 1),
            cursor_color=(0.4, 0.75, 1, 1), padding=(dp(8), dp(10)))
        self._input.bind(on_text_validate=lambda *a: self._go())
        go = Button(text="Go", size_hint_x=None, width=dp(56), font_size=13)
        go.bind(on_release=lambda *a: self._go())
        self._paste_btn = Button(text="Paste", font_size=12,
                                 background_color=(0.2, 0.35, 0.5, 1))
        self._paste_btn.bind(on_release=lambda *a: self._paste())
        self._hist, self._hpos, self._navigating = [], -1, False
        self._tree = _TREE_MODE[0]       # False: history, True: folder levels
        self._down = []                  # folders we climbed out of (for ">")
        self._tree_move = False
        self._roots = allowed_roots()
        self._last_ok = chooser.path
        self._reverting = False
        self._back = Button(text="<", size_hint_x=None, width=dp(38),
                            font_size=14)
        self._fwd = Button(text=">", size_hint_x=None, width=dp(38),
                           font_size=14)
        self._mode_btn = Button(text="", size_hint_x=None, width=dp(52),
                                font_size=12,
                                background_color=(0.2, 0.35, 0.5, 1))
        self._back.bind(on_release=lambda *a: self._nav(-1))
        self._fwd.bind(on_release=lambda *a: self._nav(1))
        self._mode_btn.bind(on_release=lambda *a: self._toggle_mode())
        for w in (self._back, self._fwd, self._mode_btn, self._input, go):
            row.add_widget(w)
        self.add_widget(row)

        self._chips = BoxLayout(size_hint_y=None, height=dp(34),
                                spacing=dp(4))
        self.add_widget(self._chips)

        self._status = Label(text="", font_size=11, size_hint_y=None,
                             height=dp(18), halign="left", valign="middle",
                             color=(1, 0.6, 0.4, 1))
        self._status.bind(size=lambda i, s: setattr(i, "text_size", s))
        self.add_widget(self._status)

        self._build_chips()
        chooser.bind(path=self._sync)
        self._sync()

    # chips -------------------------------------------------------------
    def _build_chips(self):
        home = shared_storage_root()
        from core.android_storage import ON_ANDROID, removable_volumes
        if ON_ANDROID:
            # Android refuses to list "/" and "/storage" to apps, so those
            # shortcuts only ever showed "no permission". Offer the phone's
            # shared storage plus any SD card / USB drive instead.
            targets = [("Phone", home)] + removable_volumes()
        else:
            targets = [("Home", home), ("Root", _fs_root(home))]
        for name in ("DCIM", "Download", "Pictures", "Movies", "Music"):
            p = os.path.join(home, name)
            if os.path.isdir(p):
                targets.append((name, p))
        for label, p in targets[:5]:
            b = Button(text=label, font_size=12, shorten=True,
                       background_color=(0.25, 0.25, 0.25, 1))
            b.bind(on_release=lambda inst, pp=p: self._open(pp))
            self._chips.add_widget(b)
        self._chips.add_widget(self._paste_btn)

    # behaviour ---------------------------------------------------------
    def _open(self, path):
        self._input.text = path
        self._go()

    def _paste(self):
        try:
            from kivy.core.clipboard import Clipboard
            txt = Clipboard.paste()
        except Exception:
            txt = ""
        if txt:
            self._input.text = txt.strip().splitlines()[0]
            self._go()
        else:
            self._status.text = "Clipboard is empty"

    def _go(self):
        p = _clean(self._input.text)
        if not p:
            return
        if os.path.isfile(p):
            folder = os.path.dirname(p)
            self._chooser.path = folder
            Clock.schedule_once(
                lambda dt: setattr(self._chooser, "selection", [p]), 0.2)
            return
        state = folder_state(p)
        if state == "missing":
            self._status.text = "Not found: " + p
            return
        if state == "denied":
            self._status.text = ("No permission to read this folder"
                                 " (Android: allow 'all files access')")
            return
        self._chooser.path = p

    def _parent(self):
        p = os.path.abspath(self._chooser.path)
        parent = os.path.dirname(p.rstrip("/\\")) or _fs_root(p)
        if (parent and parent != p and os.path.isdir(parent)
                and inside_allowed(parent, self._roots)):
            return parent
        return None

    def _up(self):
        parent = self._parent()
        if parent:
            self._down.append(os.path.abspath(self._chooser.path))
            self._tree_move = True
            try:
                self._chooser.path = parent
            finally:
                self._tree_move = False

    def _down_into(self):
        cur = os.path.abspath(self._chooser.path)
        while self._down:
            child = self._down.pop()
            if os.path.dirname(child.rstrip("/\\")) == cur \
                    and os.path.isdir(child):
                self._tree_move = True
                try:
                    self._chooser.path = child
                finally:
                    self._tree_move = False
                return

    def _toggle_mode(self):
        self._tree = not self._tree
        _TREE_MODE[0] = self._tree
        self._update_nav()

    def _nav(self, step):
        if self._tree:
            self._up() if step < 0 else self._down_into()
        else:
            self._hist_go(step)

    def _hist_go(self, step):
        i = self._hpos + step
        if 0 <= i < len(self._hist):
            self._hpos = i
            self._navigating = True
            self._chooser.path = self._hist[i]
            self._navigating = False
            self._update_nav()

    def _update_nav(self):
        self._mode_btn.text = "Tree" if self._tree else "Hist"
        if self._tree:
            # "<" = up one folder level, ">" = back down into the folder you
            # just climbed out of
            self._back.disabled = self._parent() is None
            cur = os.path.abspath(self._chooser.path)
            self._fwd.disabled = not any(
                os.path.dirname(c.rstrip("/\\")) == cur for c in self._down)
        else:
            self._back.disabled = self._hpos <= 0
            self._fwd.disabled = self._hpos >= len(self._hist) - 1

    def _sync(self, *a):
        p = self._chooser.path
        if self._reverting:
            return
        # Never leave the folders an app is allowed to read, and never stay
        # on a folder we can't open: go back to the last good one and say why.
        bad = None
        if not inside_allowed(p, self._roots):
            bad = "That's the top of the storage an app can browse."
        elif folder_state(p) == "denied":
            bad = "Android doesn't let apps open that folder."
        if bad and self._last_ok and p != self._last_ok:
            self._reverting = True
            try:
                self._chooser.path = self._last_ok
            finally:
                self._reverting = False
            self._input.text = self._last_ok
            self._status.text = bad
            self._update_nav()
            return
        self._last_ok = p
        if not self._tree_move and self._down:
            cur = os.path.abspath(p)
            # moved somewhere unrelated: the "go back down" trail is stale
            if not any(os.path.dirname(c.rstrip("/\\")) == cur
                       or c.startswith(cur.rstrip(os.sep) + os.sep)
                       for c in self._down):
                self._down = []
        if not self._navigating and (not self._hist
                                     or self._hist[self._hpos] != p):
            del self._hist[self._hpos + 1:]      # new branch drops "forward"
            self._hist.append(p)
            self._hpos = len(self._hist) - 1
        self._update_nav()
        if not self._input.focus:
            self._input.text = p
        state = folder_state(p)
        self._status.text = {
            "ok": "", "empty": "Empty folder",
            "denied": "Can't read this folder (no permission?)",
            "missing": "Folder not found"}.get(state, "")


def install():
    """Replace kivy's FileChooserIconView with the path-bar subclass.
    Safe to call twice. Call before screens are imported."""
    global _installed
    if _installed:
        return
    import kivy.uix.filechooser as fc
    _Orig = fc.FileChooserIconView

    class FileChooserIconView(_Orig):
        def _ghost(self, kind):
            """True if this entry event repeats the previous one within
            150 ms - one tap arriving twice. Android only (on desktop a quick
            double-click on a file is a real gesture)."""
            if not _is_android():
                return False
            import time as _t
            now = _t.monotonic()
            last = getattr(self, "_ghost_" + kind, 0.0)
            setattr(self, "_ghost_" + kind, now)
            return now - last < 0.15

        def entry_touched(self, entry, touch):
            if self._ghost("touched"):
                return False
            return super().entry_touched(entry, touch)

        def entry_released(self, entry, touch):
            if self._ghost("released"):
                return False
            # Folder pickers (dirselect=True): stock behaviour is tap =
            # select, DOUBLE tap = open - on a phone that meant a dead second
            # tap and an unreliable double tap. Now one tap opens the folder
            # (Select then uses the folder you are in). File pickers already
            # open folders on a single tap in stock Kivy, so leave them.
            try:
                if ("button" in touch.profile and touch.button in (
                        "scrollup", "scrolldown", "scrollleft",
                        "scrollright")):
                    return False
                if self.dirselect and not self.multiselect and \
                        self.file_system.is_dir(entry.path):
                    self.open_entry(entry)
                    return
            except Exception:
                pass
            return super().entry_released(entry, touch)

        def on_parent(self, inst, parent):
            if (parent is None or getattr(self, "_pathbar_done", False)
                    or not isinstance(parent, BoxLayout)
                    or parent.orientation != "vertical"):
                return
            self._pathbar_done = True

            # Deferred: Widget.add_widget sets .parent BEFORE it inserts the
            # child, so adding the bar right here would land it in the wrong
            # slot. One frame later the layout is stable.
            def _add(dt):
                try:
                    if self.parent is parent:
                        bar = PathBar(self)
                        parent.add_widget(bar, index=len(parent.children))
                except Exception as exc:
                    print(f"pathbar skipped: {exc}")
            Clock.schedule_once(_add, 0)

    fc.FileChooserIconView = FileChooserIconView
    _installed = True
