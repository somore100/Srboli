# screens/converted/randomizer.py
# Upgraded: class is now UtilityToolsScreen (matches main.py import)
# Added: result history, password strength indicator, dice roller, coin flip

import os
import random
import string
import collections

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.core.clipboard import Clipboard
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp

DEFAULT_SYMBOLS = "!@#$%^&*()-_=+[]{}|;:,.<>?"

# Built-in words for passwords (used when no wordlist was imported).
_BUILTIN_WORDS = [
    'gorilla', 'money', 'tiger', 'river', 'storm', 'eagle', 'cloud', 'frost',
    'flame', 'arrow', 'silver', 'golden', 'iron', 'stone', 'forest', 'ocean',
    'mountain', 'thunder', 'shadow', 'falcon', 'dragon', 'panda', 'koala', 'monkey',
    'zebra', 'rabbit', 'turtle', 'dolphin', 'penguin', 'walrus', 'otter', 'badger',
    'beaver', 'lizard', 'parrot', 'raven', 'swan', 'crane', 'heron', 'cobra',
    'viper', 'python', 'wolf', 'fox', 'bear', 'lion', 'leopard', 'jaguar',
    'lynx', 'moose', 'bison', 'camel', 'llama', 'alpaca', 'donkey', 'pony',
    'horse', 'goat', 'sheep', 'cow', 'pig', 'duck', 'goose', 'chicken',
    'apple', 'banana', 'cherry', 'grape', 'lemon', 'mango', 'melon', 'orange',
    'peach', 'pear', 'plum', 'berry', 'candy', 'cookie', 'cake', 'bread',
    'cheese', 'butter', 'honey', 'sugar', 'pepper', 'garlic', 'onion', 'carrot',
    'potato', 'tomato', 'pizza', 'burger', 'noodle', 'rice', 'soup', 'salad',
    'coffee', 'tea', 'juice', 'milk', 'water', 'fire', 'earth', 'wind',
    'snow', 'rain', 'sun', 'moon', 'star', 'comet', 'planet', 'rocket',
    'galaxy', 'orbit', 'meteor', 'sky', 'dawn', 'dusk', 'night', 'day',
    'winter', 'summer', 'spring', 'autumn', 'breeze', 'blizzard', 'desert', 'jungle',
    'island', 'valley', 'canyon', 'meadow', 'harbor', 'castle', 'tower', 'bridge',
    'garden', 'window', 'door', 'table', 'chair', 'lamp', 'clock', 'mirror',
    'pencil', 'paper', 'book', 'candle', 'blanket', 'pillow', 'basket', 'bucket',
    'hammer', 'wrench', 'anchor', 'compass', 'lantern', 'engine', 'pixel', 'turbo',
    'laser', 'cyber', 'robot', 'ninja', 'pirate', 'wizard', 'knight', 'viking',
    'hunter', 'ranger', 'sailor', 'pilot', 'artist', 'writer', 'driver', 'maker',
    'runner', 'jumper', 'swift', 'brave', 'quiet', 'happy', 'lucky', 'mighty',
    'clever', 'gentle', 'bright', 'rapid', 'silent', 'crimson', 'violet', 'amber',
    'indigo', 'scarlet', 'cobalt', 'ivory', 'ebony', 'copper', 'bronze', 'marble',
    'crystal', 'velvet', 'cotton', 'wooden', 'rusty', 'dusty', 'fuzzy', 'cosmic',
    'atomic', 'magic', 'secret', 'hidden', 'ancient', 'modern',
]

# Passwords must come from the OS CSPRNG, not the default Mersenne Twister.
_rng = random.SystemRandom()
HISTORY_MAX = 50


def _home():
    # Android: "~" resolves to "/" (read-only, empty). Start in shared storage.
    try:
        from core.android_storage import shared_storage_root
        return shared_storage_root()
    except Exception:
        return os.path.expanduser("~")


# ── password strength ─────────────────────────────────────────────────────────
def _password_strength(pw: str) -> tuple[int, str]:
    """Returns (score 0-4, label)."""
    score = 0
    if len(pw) >= 8:  score += 1
    if len(pw) >= 14: score += 1
    if any(c.isdigit() for c in pw):      score += 1
    if any(c in DEFAULT_SYMBOLS for c in pw): score += 1
    labels = ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"]
    return score, labels[score]


class StrengthBar(BoxLayout):
    def __init__(self, **kw):
        super().__init__(size_hint_y=None, height=dp(18), **kw)
        self._score = 0
        self.bind(pos=self._draw, size=self._draw)

    def set_score(self, score: int):
        self._score = max(0, min(4, score))
        self._draw()

    def _draw(self, *a):
        self.canvas.clear()
        with self.canvas:
            w = self.width
            h = self.height
            seg = w / 4
            colours = [
                (0.8, 0.15, 0.15),
                (0.85, 0.50, 0.10),
                (0.80, 0.75, 0.10),
                (0.30, 0.75, 0.25),
                (0.10, 0.85, 0.35),
            ]
            # background
            Color(0.20, 0.20, 0.22, 1)
            Rectangle(pos=self.pos, size=(w, h))
            # filled segments
            r, g, b = colours[self._score]
            Color(r, g, b, 1)
            Rectangle(pos=self.pos, size=(seg * self._score + (seg if self._score else 0), h))


# ── main screen ──────────────────────────────────────────────────────────────
class UtilityToolsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._history = collections.deque(maxlen=HISTORY_MAX)
        self._items = []        # list picker
        self._word_list = []    # password wordlist

        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))

        self.tabs = TabbedPanel(do_default_tab=False, tab_height=dp(42))
        self.tabs.add_widget(self._build_number_tab())
        self.tabs.add_widget(self._build_password_tab())
        self.tabs.add_widget(self._build_list_tab())
        self.tabs.add_widget(self._build_dice_tab())
        self.tabs.add_widget(self._build_history_tab())
        root.add_widget(self.tabs)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=lambda *a: setattr(self.manager, "current", "dashboard"))
        root.add_widget(back)

        self.add_widget(root)

    # ── shared helpers ────────────────────────────────────────────────────────
    def _record(self, category: str, value: str):
        self._history.appendleft(f"[{category}]  {value}")
        self._refresh_history()

    def _copy_popup(self, value: str):
        Clipboard.copy(value)

    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=msg),
              size_hint=(0.75, 0.38)).open()

    # ── Number tab ────────────────────────────────────────────────────────────
    def _build_number_tab(self):
        tab = TabbedPanelItem(text=" Number")
        layout = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        row.add_widget(Label(text="Min:", size_hint_x=None, width=dp(40)))
        self.num_min = TextInput(text="1", multiline=False, input_filter="int")
        row.add_widget(self.num_min)
        row.add_widget(Label(text="Max:", size_hint_x=None, width=dp(40)))
        self.num_max = TextInput(text="100", multiline=False, input_filter="int")
        row.add_widget(self.num_max)
        layout.add_widget(row)

        row2 = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        row2.add_widget(Label(text="Count:", size_hint_x=None, width=dp(56)))
        self.num_count = TextInput(text="1", multiline=False, input_filter="int",
                                   size_hint_x=None, width=dp(60))
        row2.add_widget(self.num_count)
        self.num_unique_cb = CheckBox(size_hint_x=None, size=(dp(28), dp(28)))
        row2.add_widget(self.num_unique_cb)
        row2.add_widget(Label(text="Unique", size_hint_x=None, width=dp(60)))
        layout.add_widget(row2)

        gen_btn = Button(text="Generate", size_hint_y=None, height=dp(46),
                         font_size=15)
        gen_btn.bind(on_release=self._gen_numbers)
        layout.add_widget(gen_btn)

        self.num_result = Label(text="—", font_size=22,
                                size_hint_y=None, height=dp(48))
        layout.add_widget(self.num_result)

        copy_btn = Button(text="Copy Copy", size_hint_y=None, height=dp(38))
        copy_btn.bind(on_release=lambda *a: self._copy_popup(self.num_result.text))
        layout.add_widget(copy_btn)

        tab.add_widget(layout)
        return tab

    def _gen_numbers(self, *a):
        try:
            lo = int(self.num_min.text)
            hi = int(self.num_max.text)
            count = max(1, int(self.num_count.text))
        except ValueError:
            self._popup("Error", "Enter valid integers.")
            return
        if lo > hi:
            lo, hi = hi, lo
        unique = self.num_unique_cb.active
        pool = list(range(lo, hi + 1))
        if unique and count > len(pool):
            self._popup("Error", f"Can't pick {count} unique numbers from {len(pool)}.")
            return
        if unique:
            nums = random.sample(pool, count)
        else:
            nums = [random.randint(lo, hi) for _ in range(count)]
        result = ", ".join(str(n) for n in nums)
        self.num_result.text = result
        self._record("Number", result)

    # ── Password tab ─────────────────────────────────────────────────────────
    def _build_password_tab(self):
        tab = TabbedPanelItem(text=" Password")
        layout = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(5))

        # ── mode ──
        mode_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        mode_row.add_widget(Label(text="Mode:", size_hint_x=None,
                                  width=dp(50), font_size=13))
        from kivy.uix.spinner import Spinner as _Spinner
        self._pw_mode = _Spinner(
            text="Character",
            values=("Character", "Simple (word+num+sym)", "Words (passphrase)", "Base64"),
            font_size=13,
        )
        self._pw_mode.bind(text=self._on_pw_mode_change)
        mode_row.add_widget(self._pw_mode)
        layout.add_widget(mode_row)

        # ── length / word count (shared row, label swaps) ──
        len_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        self._pw_len_label = Label(text="Length:", size_hint_x=None,
                                   width=dp(70), font_size=13)
        len_row.add_widget(self._pw_len_label)
        self.pw_length = TextInput(text="16", multiline=False,
                                   input_filter="int",
                                   size_hint_x=None, width=dp(60))
        len_row.add_widget(self.pw_length)
        layout.add_widget(len_row)

        # ── character options ──
        self._char_opts = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.pw_letters = CheckBox(active=True,  size_hint_x=None,
                                   size=(dp(24), dp(24)))
        self.pw_numbers = CheckBox(active=True,  size_hint_x=None,
                                   size=(dp(24), dp(24)))
        self.pw_symbols = CheckBox(active=False, size_hint_x=None,
                                   size=(dp(24), dp(24)))
        for cb, lbl in ((self.pw_letters, "A-Z"),
                        (self.pw_numbers, "0-9"),
                        (self.pw_symbols, "!@#")):
            self._char_opts.add_widget(cb)
            self._char_opts.add_widget(Label(text=lbl, size_hint_x=None,
                                             width=dp(44), font_size=13))
        # custom symbols
        self._char_opts.add_widget(Label(text="Custom:", size_hint_x=None,
                                         width=dp(60), font_size=12))
        self._custom_sym = TextInput(text="", multiline=False,
                                     hint_text="extra chars", font_size=12)
        self._char_opts.add_widget(self._custom_sym)
        layout.add_widget(self._char_opts)

        # ── include words (Character mode) ──
        self._pw_words_row = BoxLayout(size_hint_y=None, height=dp(38),
                                       spacing=dp(6))
        self._pw_words_row.add_widget(Label(text="Include words:",
                                            size_hint_x=None, width=dp(110),
                                            font_size=13))
        self._pw_nwords = _Spinner(text="0", values=("0", "1", "2"),
                                   size_hint_x=None, width=dp(60),
                                   font_size=13)
        self._pw_words_row.add_widget(self._pw_nwords)
        self._pw_cap = CheckBox(active=False, size_hint_x=None,
                                width=dp(32))
        self._pw_words_row.add_widget(self._pw_cap)
        self._pw_words_row.add_widget(Label(text="Capitalize", font_size=13,
                                            size_hint_x=None, width=dp(80)))
        self._pw_words_row.add_widget(Label())
        layout.add_widget(self._pw_words_row)

        # ── generate button ──
        gen_btn = Button(text=" Generate", size_hint_y=None, height=dp(46),
                         font_size=15)
        gen_btn.bind(on_release=self._gen_password)
        layout.add_widget(gen_btn)

        # ── result (editable so user can paste their own to check strength) ──
        layout.add_widget(Label(text="Result / paste to check strength:",
                                size_hint_y=None, height=dp(22), font_size=12))
        self.pw_result = TextInput(
            text="", multiline=False,
            size_hint_y=None, height=dp(44), font_size=15,
            background_color=(0.12, 0.12, 0.14, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
        )
        self.pw_result.bind(text=self._on_pw_result_change)
        layout.add_widget(self.pw_result)

        self.pw_strength_bar = StrengthBar()
        layout.add_widget(self.pw_strength_bar)
        self.pw_strength_label = Label(text="", size_hint_y=None,
                                       height=dp(22), font_size=12)
        layout.add_widget(self.pw_strength_label)

        # ── copy + wordlist import ──
        bot = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        copy_btn = Button(text="Copy Copy", font_size=13)
        copy_btn.bind(on_release=lambda *a: self._copy_popup(self.pw_result.text))
        import_btn = Button(text="Import Wordlist .txt", font_size=12)
        import_btn.bind(on_release=self._import_wordlist)
        wl_lbl = Label(font_size=11, text=f"built-in: {len(_BUILTIN_WORDS)} words")
        self._wl_label = wl_lbl
        bot.add_widget(copy_btn)
        bot.add_widget(import_btn)
        bot.add_widget(wl_lbl)
        layout.add_widget(bot)

        tab.add_widget(layout)
        return tab

    def _on_pw_mode_change(self, spinner, text):
        is_char   = text == "Character"
        is_simple = text == "Simple (word+num+sym)"
        is_words  = text == "Words (passphrase)"
        is_b64    = text == "Base64"
        self._char_opts.opacity  = 1 if is_char else 0.3
        self._pw_words_row.opacity = 1 if is_char else 0.3
        self._pw_words_row.disabled = not is_char
        self._pw_len_label.text  = "Words:" if is_words else "Length:"
        if is_words:
            self.pw_length.text = "4"
        elif is_b64:
            self.pw_length.text = "24"
        elif is_simple:
            self.pw_length.text = "2"   # number of words to combine
        else:
            self.pw_length.text = "16"

    def _on_pw_result_change(self, inst, val):
        """Live strength check when user types/pastes into result box."""
        if val:
            score, label = _password_strength(val)
            self.pw_strength_bar.set_score(score)
            self.pw_strength_label.text = f"Strength: {label}"

    def _gen_password(self, *a):
        mode = self._pw_mode.text

        if mode == "Simple (word+num+sym)":
            # Pattern: word(s) + 2-digit number + optional symbol
            # e.g. catfish55X  truckeat55!  bluerain42#
            try:
                word_count = max(1, min(3, int(self.pw_length.text)))
            except ValueError:
                word_count = 2

            # word bank — imported wordlist, else the built-in one
            bank = self._word_list if self._word_list else _BUILTIN_WORDS
            words = [_rng.choice(bank).lower() for _ in range(word_count)]
            combined = "".join(words)

            num = str(_rng.randint(10, 99))

            # optional suffix: uppercase letter or symbol
            if self.pw_symbols.active:
                suffix = _rng.choice(DEFAULT_SYMBOLS)
            elif self.pw_letters.active:
                suffix = _rng.choice(string.ascii_uppercase)
            else:
                suffix = ""

            pw = combined + num + suffix

        elif mode == "Base64":
            import base64 as _b64, os as _os
            try:
                byte_count = max(6, int(self.pw_length.text) * 3 // 4)
            except ValueError:
                byte_count = 18
            pw = _b64.urlsafe_b64encode(_os.urandom(byte_count)).decode()[:int(self.pw_length.text) if self.pw_length.text.isdigit() else 24]

        elif mode == "Words (passphrase)":
            try:
                word_count = max(2, min(12, int(self.pw_length.text)))
            except ValueError:
                word_count = 4
            bank = self._word_list if self._word_list else _BUILTIN_WORDS
            words = [_rng.choice(bank) for _ in range(word_count)]
            sep = _rng.choice(["-", "_", ".", ""])
            num = str(_rng.randint(10, 99))
            pw  = sep.join(words) + num

        else:  # Character mode
            try:
                length = max(4, min(256, int(self.pw_length.text)))
            except ValueError:
                length = 16
            charset = ""
            if self.pw_letters.active: charset += string.ascii_letters
            if self.pw_numbers.active: charset += string.digits
            if self.pw_symbols.active: charset += DEFAULT_SYMBOLS
            extra = self._custom_sym.text
            if extra:
                charset += extra
            if not charset:
                charset = string.ascii_letters + string.digits

            try:
                n_words = max(0, min(2, int(self._pw_nwords.text)))
            except ValueError:
                n_words = 0
            if n_words:
                # words first, then random characters, e.g. gorillamoney2341.
                # The words already supply letters, so when digits/symbols
                # are enabled the tail uses only those.
                bank = self._word_list if self._word_list else _BUILTIN_WORDS
                picked = [_rng.choice(bank).strip().lower()
                          for _ in range(n_words)]
                if self._pw_cap.active:
                    picked = [w.capitalize() for w in picked]
                head = "".join(picked)
                tail_set = "".join(c for c in charset
                                   if c not in string.ascii_letters) or charset
                tail_len = max(4, length - len(head))   # never fewer than 4
                pw = head + "".join(_rng.choice(tail_set)
                                    for _ in range(tail_len))
            else:
                pw = "".join(_rng.choice(charset) for _ in range(length))

        self.pw_result.text = pw
        score, label = _password_strength(pw)
        self.pw_strength_bar.set_score(score)
        self.pw_strength_label.text = f"Strength: {label}"
        self._record("Password", pw)

    def _import_wordlist(self, *a):
        chooser = FileChooserIconView(path=_home(), filters=["*.txt"],
                                      multiselect=False)
        btn = Button(text="Import", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Import Wordlist", content=layout,
                      size_hint=(0.9, 0.9))

        def _do(inst):
            if chooser.selection:
                try:
                    with open(chooser.selection[0], encoding="utf-8") as f:
                        lines = [l.strip() for l in f if l.strip()]
                    self._word_list = lines
                    self._wl_label.text = f"{len(lines)} words"
                    self._popup("Imported", f"{len(lines)} words loaded.")
                except Exception as e:
                    self._popup("Error", str(e))
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    # ── List picker tab ───────────────────────────────────────────────────────
    def _build_list_tab(self):
        tab = TabbedPanelItem(text="Copy List")
        layout = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))

        add_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.list_input = TextInput(hint_text="Add item…", multiline=False)
        add_btn = Button(text="Add", size_hint_x=None, width=dp(70))
        add_btn.bind(on_release=self._add_item)
        import_btn = Button(text="Import .txt", size_hint_x=None, width=dp(100))
        import_btn.bind(on_release=self._import_list)
        clear_btn = Button(text="Clear", size_hint_x=None, width=dp(70))
        clear_btn.bind(on_release=lambda *a: self._clear_items())
        add_row.add_widget(self.list_input)
        add_row.add_widget(add_btn)
        add_row.add_widget(import_btn)
        add_row.add_widget(clear_btn)
        layout.add_widget(add_row)

        sv = ScrollView(size_hint=(1, 0.45))
        self.list_grid = GridLayout(cols=1, spacing=dp(3), size_hint_y=None)
        self.list_grid.bind(minimum_height=self.list_grid.setter("height"))
        sv.add_widget(self.list_grid)
        layout.add_widget(sv)

        pick_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        pick_row.add_widget(Label(text="Pick:", size_hint_x=None, width=dp(42)))
        self.pick_count = TextInput(text="1", multiline=False, input_filter="int",
                                    size_hint_x=None, width=dp(50))
        pick_row.add_widget(self.pick_count)
        pick_btn = Button(text="Pick Random!")
        pick_btn.bind(on_release=self._pick_random)
        pick_row.add_widget(pick_btn)
        layout.add_widget(pick_row)

        self.list_result = Label(text="—", font_size=16,
                                 size_hint_y=None, height=dp(40))
        layout.add_widget(self.list_result)

        copy_btn = Button(text="Copy Copy result", size_hint_y=None, height=dp(36))
        copy_btn.bind(on_release=lambda *a: self._copy_popup(self.list_result.text))
        layout.add_widget(copy_btn)

        tab.add_widget(layout)
        return tab

    def _add_item(self, *a):
        name = self.list_input.text.strip()
        if name and name not in self._items:
            self._items.append(name)
            self.list_input.text = ""
            self._refresh_list_ui()

    def _clear_items(self):
        self._items = []
        self._refresh_list_ui()

    def _import_list(self, *a):
        chooser = FileChooserIconView(path=_home(), filters=["*.txt"],
                                      multiselect=False)
        btn = Button(text="Import", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Import list from .txt", content=layout,
                      size_hint=(0.9, 0.9))

        def _do(inst):
            if chooser.selection:
                try:
                    with open(chooser.selection[0], encoding="utf-8") as f:
                        for line in f:
                            ln = line.strip()
                            if ln and ln not in self._items:
                                self._items.append(ln)
                    self._refresh_list_ui()
                except Exception as e:
                    self._popup("Error", str(e))
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def _refresh_list_ui(self):
        self.list_grid.clear_widgets()
        for i, name in enumerate(self._items):
            row = BoxLayout(size_hint_y=None, height=dp(30))
            row.add_widget(Label(text=name, halign="left", font_size=13))
            d = Button(text="x", size_hint_x=None, width=dp(34), font_size=12)
            d.bind(on_release=lambda inst, idx=i: (
                self._items.pop(idx), self._refresh_list_ui()
            ))
            row.add_widget(d)
            self.list_grid.add_widget(row)

    def _pick_random(self, *a):
        if not self._items:
            self._popup("Empty", "Add items first.")
            return
        try:
            count = max(1, int(self.pick_count.text))
        except ValueError:
            count = 1
        count = min(count, len(self._items))
        picked = random.sample(self._items, count)
        result = ", ".join(picked)
        self.list_result.text = result
        self._record("List Pick", result)

    # ── Dice / Coin tab ───────────────────────────────────────────────────────
    def _build_dice_tab(self):
        tab = TabbedPanelItem(text=" Dice")
        layout = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))

        layout.add_widget(Label(text="[b]Dice Roller[/b]", markup=True,
                                size_hint_y=None, height=dp(30), font_size=16))

        dice_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        dice_row.add_widget(Label(text="Rolls:", size_hint_x=None, width=dp(52)))
        self.dice_count = TextInput(text="1", multiline=False, input_filter="int",
                                    size_hint_x=None, width=dp(50))
        dice_row.add_widget(self.dice_count)
        dice_row.add_widget(Label(text="d", size_hint_x=None, width=dp(18),
                                  font_size=18))
        self.dice_sides = TextInput(text="6", multiline=False, input_filter="int",
                                    size_hint_x=None, width=dp(60))
        dice_row.add_widget(self.dice_sides)
        dice_row.add_widget(Label(text="+", size_hint_x=None, width=dp(16), font_size=16))
        self.dice_mod = TextInput(text="0", multiline=False, input_filter="int",
                                  size_hint_x=None, width=dp(50))
        dice_row.add_widget(self.dice_mod)
        layout.add_widget(dice_row)

        # quick dice buttons
        quick = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(5))
        for sides in (4, 6, 8, 10, 12, 20, 100):
            b = Button(text=f"d{sides}", font_size=12)
            b.bind(on_release=lambda inst, s=sides: self._quick_roll(s))
            quick.add_widget(b)
        layout.add_widget(quick)

        roll_btn = Button(text=" Roll!", size_hint_y=None, height=dp(46),
                          font_size=16)
        roll_btn.bind(on_release=self._roll_dice)
        layout.add_widget(roll_btn)

        self.dice_result = Label(text="—", font_size=24,
                                 size_hint_y=None, height=dp(50))
        layout.add_widget(self.dice_result)

        # coin flip
        layout.add_widget(Label(text="[b]Coin Flip[/b]", markup=True,
                                size_hint_y=None, height=dp(28), font_size=15))
        coin_btn = Button(text=" Flip!", size_hint_y=None, height=dp(44),
                          font_size=15)
        coin_btn.bind(on_release=self._coin_flip)
        layout.add_widget(coin_btn)
        self.coin_result = Label(text="—", font_size=20,
                                 size_hint_y=None, height=dp(40))
        layout.add_widget(self.coin_result)

        tab.add_widget(layout)
        return tab

    def _roll_dice(self, *a):
        try:
            count = max(1, int(self.dice_count.text))
            sides = max(2, int(self.dice_sides.text))
            mod   = int(self.dice_mod.text)
        except ValueError:
            self._popup("Error", "Enter valid numbers.")
            return
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + mod
        detail = " + ".join(str(r) for r in rolls)
        if mod != 0:
            detail += f" + {mod}"
        result = f"{total}  ({detail})"
        self.dice_result.text = result
        self._record("Dice", result)

    def _quick_roll(self, sides):
        self.dice_sides.text = str(sides)
        self.dice_count.text = "1"
        self.dice_mod.text   = "0"
        self._roll_dice()

    def _coin_flip(self, *a):
        result = random.choice(["Heads ", "Tails "])
        self.coin_result.text = result
        self._record("Coin", result)

    # ── History tab ───────────────────────────────────────────────────────────
    def _build_history_tab(self):
        tab = TabbedPanelItem(text=" History")
        layout = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))

        top = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        top.add_widget(Label(text="Recent results:", font_size=14))
        clr = Button(text="Clear", size_hint_x=None, width=dp(80))
        clr.bind(on_release=lambda *a: self._clear_history())
        top.add_widget(clr)
        layout.add_widget(top)

        sv = ScrollView()
        self.history_grid = GridLayout(cols=1, spacing=dp(3), size_hint_y=None,
                                       padding=dp(4))
        self.history_grid.bind(minimum_height=self.history_grid.setter("height"))
        sv.add_widget(self.history_grid)
        layout.add_widget(sv)

        tab.add_widget(layout)
        return tab

    def _refresh_history(self):
        if not hasattr(self, "history_grid"):
            return
        self.history_grid.clear_widgets()
        for entry in self._history:
            row = BoxLayout(size_hint_y=None, height=dp(28))
            lbl = Label(text=entry, font_size=12, halign="left")
            lbl.bind(size=lbl.setter("text_size"))
            copy_btn = Button(text="Copy", size_hint_x=None, width=dp(34),
                              font_size=12)
            val = entry.split("]  ", 1)[-1]
            copy_btn.bind(on_release=lambda inst, v=val: self._copy_popup(v))
            row.add_widget(lbl)
            row.add_widget(copy_btn)
            self.history_grid.add_widget(row)

    def _clear_history(self):
        self._history.clear()
        self._refresh_history()
