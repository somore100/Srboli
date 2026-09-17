# screens/fast_transfer_screen.py
#
# Fast (parallel/batched) file transfer.
#
# The problem this solves: copying/moving a folder one file at a time
# means file 2 waits for file 1 to fully finish, even on a source/dest
# pair that could easily sustain several transfers running at once.
# This screen collects the file list up front, then keeps up to N of
# them "in flight" at the same time (a rolling window, not rigid
# discrete batches - as soon as one finishes, the next one starts,
# rather than waiting for a whole group of N to complete first).
#
# IMPORTANT SCOPE NOTE (recorded design decision - do not "fix" this
# later without a deliberate discussion): this is for MANY SMALLER
# FILES (extracted projects, photo dumps, source trees) - not a
# general "faster than Explorer/Finder" claim. A handful of very large
# files, or a destination on a spinning hard drive that has to
# physically seek between simultaneous writes, can genuinely transfer
# SLOWER this way than one-at-a-time. Analyze (below) tries to flag
# that case rather than silently recommending high concurrency anyway.
#
# There is no OS API that hands you a real "max simultaneous transfer
# limit" - Explorer/Finder/Nautilus don't expose one either, they just
# use their own internal heuristics. Recommend_concurrency() below is
# the same kind of heuristic: a starting point from file count, average
# file size, and (Linux-only, best-effort) whether the destination disk
# is rotational - never an authoritative number. The concurrency field
# is always user-editable.

import os, shutil, threading, time, platform
from concurrent.futures import ThreadPoolExecutor, as_completed

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.metrics import dp

# Reuse the exact "don't act on a file that's still being written"
# guard File Sorter already has, rather than a second copy of it - the
# same download-mid-flight risk applies here.
from screens.file_sorter_screen import wait_for_stable_file, _fmt_size

MODES = ["Copy", "Move"]
PROBE_SAMPLE_BYTES = 4 * 1024 * 1024  # 4MB, for the quick write-speed probe


# ── pure / testable logic ───────────────────────────────────────────────

def collect_files_with_relpaths(source, recursive=True):
    """Returns [(abs_path, rel_path), ...] for every regular file under
    `source`. rel_path is used to rebuild the same folder structure
    under the destination."""
    pairs = []
    if recursive:
        for root, _dirs, files in os.walk(source):
            for name in files:
                abs_path = os.path.join(root, name)
                rel_path = os.path.relpath(abs_path, source)
                pairs.append((abs_path, rel_path))
    else:
        for name in os.listdir(source):
            abs_path = os.path.join(source, name)
            if os.path.isfile(abs_path):
                pairs.append((abs_path, name))
    return pairs


def detect_rotational(path):
    """Best-effort: True/False if we can tell the disk backing `path` is
    a spinning hard drive, None if we genuinely can't tell (non-Linux,
    network mount, container without /sys, etc). Never raises.

    CAVEAT (confirmed while testing this): virtualized disks (VMs,
    some containers) frequently report rotational=1 via sysfs even when
    the real underlying storage is an SSD/NVMe - the virtio-blk driver
    just doesn't always know or bother to say otherwise. This is a
    genuine limitation of the OS-level signal itself, not something we
    can correct for from userspace. Treat a True result as "possibly
    rotational, recommend caution" rather than certainty, especially
    inside a VM."""
    if platform.system() != "Linux":
        return None
    try:
        st = os.stat(path)
        maj, minr = os.major(st.st_dev), os.minor(st.st_dev)
        dev_link = f"/sys/dev/block/{maj}:{minr}"
        if not os.path.exists(dev_link):
            return None
        real = os.path.realpath(dev_link)
        parts = real.split(os.sep)
        if "block" not in parts:
            return None
        # .../block/sda/sda1 (partition) or .../block/sda (whole disk) -
        # "queue/rotational" only exists at the whole-disk level, so walk
        # up to the segment right after "block".
        idx = parts.index("block")
        disk_dir = os.sep.join(parts[:idx + 2])
        rot_file = os.path.join(disk_dir, "queue", "rotational")
        if os.path.exists(rot_file):
            with open(rot_file) as f:
                return f.read().strip() == "1"
    except Exception:
        pass
    return None


def quick_write_probe(dest_folder, sample_bytes=PROBE_SAMPLE_BYTES):
    """Writes and deletes a throwaway file to estimate write MB/s.
    Returns None if the probe itself fails (read-only folder, no space,
    permissions) - callers should treat that as 'unknown', not an error."""
    probe_path = os.path.join(dest_folder, ".srboli_transfer_probe.tmp")
    try:
        data = os.urandom(min(sample_bytes, 1024 * 1024)) * (sample_bytes // (1024 * 1024) or 1)
        data = data[:sample_bytes]
        t0 = time.time()
        with open(probe_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        elapsed = max(time.time() - t0, 1e-6)
        return (sample_bytes / elapsed) / (1024 * 1024)  # MB/s
    except Exception:
        return None
    finally:
        try:
            os.remove(probe_path)
        except Exception:
            pass


def recommend_concurrency(file_count, avg_size_bytes, rotational):
    """Returns (recommended_workers, reason_text). Always a starting
    point, never authoritative - see module docstring.

    Deliberately NOT based on CPU core count: these threads spend
    almost all their time waiting on disk/network I/O, not computing,
    so a single-core machine can still usefully run several transfers
    at once. What actually limits useful concurrency here is the
    destination's ability to serve multiple I/O requests at once
    (rotational disks can't; SSDs/NVMe/most network shares can, up to
    a point) and simply how many files there are to spread across
    workers."""
    if file_count <= 1:
        return 1, "Only one file - nothing to parallelize."

    if rotational is True:
        return 2, ("Destination looks like a spinning hard drive - it "
                    "has to physically seek between simultaneous writes, "
                    "so a high number here can be slower, not faster. "
                    "Kept low on purpose.")

    if avg_size_bytes > 200 * 1024 * 1024:  # large files (video, ISOs...)
        return min(3, file_count), (
            "These are large files - a single transfer already "
            "saturates most of the available throughput, so extra "
            "parallel transfers help less than they do for many small "
            "files.")

    # many small/medium files, unknown or non-rotational destination
    suggested = min(6, file_count)
    reason = ("Lots of smaller files - this is exactly the case parallel "
              "transfer helps most with.")
    if rotational is None:
        reason += " (couldn't determine the destination's disk type, so treating it as best-case.)"
    return suggested, reason


def _unique_dest_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


# File Sorter's wait_for_stable_file() defaults (1s poll x 3 checks =
# ~2s minimum) are fine for its occasional, rule-triggered actions. Fast
# Transfer moves potentially thousands of files, almost all of them
# already fully written - paying that same ~2s tax on every single one
# would defeat the entire point of a "fast" transfer tool. Poll much
# faster here instead; a file that's actively growing will still show a
# size change well within this window, so real in-progress files are
# still caught, just with far less needless overhead on finished ones.
_FT_STABLE_POLL_INTERVAL = 0.15
_FT_STABLE_CHECKS_REQUIRED = 3


def _transfer_one(abs_path, rel_path, dest_root, mode, overwrite, stop_check, log):
    if stop_check and stop_check():
        return ("stopped", abs_path, None, None)

    dest_path = os.path.join(dest_root, rel_path)
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    except Exception as e:
        return ("error", abs_path, None, str(e))

    if not overwrite:
        dest_path = _unique_dest_path(dest_path)

    if not wait_for_stable_file(abs_path, log=log, stop_check=stop_check,
                                 poll_interval=_FT_STABLE_POLL_INTERVAL,
                                 checks_required=_FT_STABLE_CHECKS_REQUIRED):
        if stop_check and stop_check():
            return ("stopped", abs_path, None, None)
        return ("error", abs_path, None,
                "file disappeared while waiting for it to finish writing")

    try:
        size = os.path.getsize(abs_path)
        if mode == "move":
            shutil.move(abs_path, dest_path)
        else:
            shutil.copy2(abs_path, dest_path)
        return ("done", abs_path, dest_path, size)
    except Exception as e:
        return ("error", abs_path, None, str(e))


def run_transfer(pairs, dest_root, mode, concurrency, overwrite=False,
                  stop_check=None, log=None, on_result=None):
    """Runs the transfer with up to `concurrency` files in flight at
    once (a rolling window via ThreadPoolExecutor - not rigid batches,
    so a fast file doesn't sit waiting on a slow one in the same
    'batch'). `on_result(status, abs_path, dest_path, size_or_error)` is
    called from THIS (worker) thread as each file finishes - the caller
    is responsible for hopping back to the UI thread if needed."""
    concurrency = max(1, int(concurrency))
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_transfer_one, abs_path, rel_path, dest_root,
                        mode, overwrite, stop_check, log): abs_path
            for abs_path, rel_path in pairs
        }
        for future in as_completed(futures):
            status, abs_path, dest_path, extra = future.result()
            results.append((status, abs_path, dest_path, extra))
            if on_result:
                on_result(status, abs_path, dest_path, extra)
    return results


EXPLAIN_TEXT = (
    "[b]How this is different from a normal copy/move[/b]\n"
    "Copying files one at a time means file 2 waits for file 1 to fully "
    "finish, even though your system can usually handle several "
    "transfers running at once. This screen scans the folder first, "
    "then keeps a chosen number of transfers running at the same time "
    "instead of strictly one by one.\n\n"
    "[b]Best for:[/b] folders with lots of smaller files - extracted "
    "projects, photo dumps, source trees.\n"
    "[b]Won't help much (sometimes hurts):[/b] a handful of very large "
    "files, or a destination on a spinning hard drive, which has to "
    "physically seek between simultaneous writes. Hit Analyze below and "
    "it will call this out if it looks like your case.\n\n"
    "[i]Note: there's no OS setting for a true 'max simultaneous "
    "transfers' number - Explorer/Finder/Nautilus don't have one to "
    "read either. The concurrency below is a recommendation based on "
    "your files, not a detected system limit, and you can change it.[/i]"
)


class FastTransferScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._source = ""
        self._dest = ""
        self._pairs = None          # last Analyze result
        self._busy = False
        self._stop_requested = False
        self._transferred_bytes = 0
        self._done_count = 0
        self._error_lines = []

        root = BoxLayout(orientation="vertical", padding=8, spacing=6)
        root.add_widget(Label(text="[b]Fast File Transfer[/b] (parallel/batched)",
                              markup=True, font_size=18, size_hint_y=None,
                              height=dp(30)))

        explain = Label(text=EXPLAIN_TEXT, markup=True, font_size=11,
                        halign="left", valign="top", size_hint_y=None,
                        color=(0.75, 0.85, 0.95, 1))
        explain.bind(width=lambda *a: setattr(
            explain, "text_size", (explain.width, None)))
        explain.bind(texture_size=lambda *a: setattr(
            explain, "height", explain.texture_size[1] + dp(8)))
        root.add_widget(explain)

        # source / destination
        src_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        self._src_lbl = Label(text="(no source folder chosen)", font_size=11,
                              halign="left", color=(0.7, 0.9, 0.7, 1))
        self._src_lbl.bind(size=self._src_lbl.setter("text_size"))
        pick_src = Button(text="Pick Source", size_hint_x=None, width=dp(120))
        pick_src.bind(on_release=lambda *a: self._pick_folder("source"))
        src_row.add_widget(pick_src)
        src_row.add_widget(self._src_lbl)
        root.add_widget(src_row)

        dst_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        self._dst_lbl = Label(text="(no destination folder chosen)", font_size=11,
                              halign="left", color=(0.7, 0.9, 0.7, 1))
        self._dst_lbl.bind(size=self._dst_lbl.setter("text_size"))
        pick_dst = Button(text="Pick Destination", size_hint_x=None, width=dp(120))
        pick_dst.bind(on_release=lambda *a: self._pick_folder("dest"))
        dst_row.add_widget(pick_dst)
        dst_row.add_widget(self._dst_lbl)
        root.add_widget(dst_row)

        # options
        opt_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=8)
        opt_row.add_widget(Label(text="Mode:", size_hint_x=None, width=dp(50),
                                 font_size=12))
        self._mode_spinner = Spinner(text="Copy", values=MODES,
                                     size_hint_x=None, width=dp(90))
        self._mode_spinner.bind(text=lambda *a: self._mark_stale())
        opt_row.add_widget(self._mode_spinner)

        self._recursive_cb = CheckBox(active=True, size_hint=(None, None),
                                      size=(dp(24), dp(24)))
        self._recursive_cb.bind(active=lambda *a: self._mark_stale())
        opt_row.add_widget(self._recursive_cb)
        opt_row.add_widget(Label(text="Include subfolders", font_size=12,
                                 size_hint_x=None, width=dp(120)))

        self._overwrite_cb = CheckBox(active=False, size_hint=(None, None),
                                      size=(dp(24), dp(24)))
        opt_row.add_widget(self._overwrite_cb)
        opt_row.add_widget(Label(text="Overwrite existing", font_size=12))
        root.add_widget(opt_row)

        # concurrency
        conc_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=8)
        conc_row.add_widget(Label(text="Concurrency:", size_hint_x=None,
                                  width=dp(90), font_size=12))
        self._concurrency_input = TextInput(text="4", multiline=False,
                                            input_filter="int", font_size=12,
                                            size_hint_x=None, width=dp(60))
        conc_row.add_widget(self._concurrency_input)
        self._recommend_lbl = Label(text="Run Analyze to get a recommendation.",
                                    font_size=11, halign="left",
                                    color=(0.8, 0.8, 0.5, 1))
        self._recommend_lbl.bind(size=self._recommend_lbl.setter("text_size"))
        conc_row.add_widget(self._recommend_lbl)
        root.add_widget(conc_row)

        # actions
        act_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        self._analyze_btn = Button(text="Analyze")
        self._analyze_btn.bind(on_release=self._run_analyze)
        self._start_btn = Button(text="Start Transfer", disabled=True)
        self._start_btn.bind(on_release=self._run_transfer)
        self._stop_btn = Button(text="Stop", disabled=True, size_hint_x=None,
                                width=dp(70))
        self._stop_btn.bind(on_release=self._request_stop)
        act_row.add_widget(self._analyze_btn)
        act_row.add_widget(self._start_btn)
        act_row.add_widget(self._stop_btn)
        root.add_widget(act_row)

        self._status = Label(text="", size_hint_y=None, height=dp(20),
                             font_size=11, color=(0.6, 0.8, 1, 1))
        root.add_widget(self._status)

        log_sv = ScrollView(size_hint_y=0.32)
        self._log_lbl = Label(text="", font_size=10, halign="left",
                              valign="top", size_hint_y=None, markup=False)
        self._log_lbl.bind(texture_size=lambda *a: setattr(
            self._log_lbl, "height", self._log_lbl.texture_size[1]))
        self._log_lbl.bind(width=lambda *a: setattr(
            self._log_lbl, "text_size", (self._log_lbl.width, None)))
        log_sv.add_widget(self._log_lbl)
        root.add_widget(log_sv)

        back = Button(text="< Back", size_hint_y=None, height=dp(40))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

    # ── folder picking ──────────────────────────────────────────────────
    def _pick_folder(self, which):
        chooser = FileChooserIconView(path=os.path.expanduser("~"),
                                      dirselect=True)
        popup = Popup(title="Choose a folder", content=chooser,
                      size_hint=(0.9, 0.9))

        def _use(*a):
            if chooser.selection:
                folder = chooser.selection[0]
                if os.path.isfile(folder):
                    folder = os.path.dirname(folder)
                if which == "source":
                    self._source = folder
                    self._src_lbl.text = folder
                else:
                    self._dest = folder
                    self._dst_lbl.text = folder
                self._mark_stale()
            popup.dismiss()

        btn_row = BoxLayout(size_hint_y=None, height=dp(40))
        use_btn = Button(text="Use this folder")
        use_btn.bind(on_release=_use)
        cancel_btn = Button(text="Cancel")
        cancel_btn.bind(on_release=lambda *a: popup.dismiss())
        btn_row.add_widget(use_btn)
        btn_row.add_widget(cancel_btn)
        wrapper = BoxLayout(orientation="vertical")
        wrapper.add_widget(chooser)
        wrapper.add_widget(btn_row)
        popup.content = wrapper
        popup.open()

    def _mark_stale(self):
        self._pairs = None
        self._start_btn.disabled = True

    # ── analyze ──────────────────────────────────────────────────────────
    def _run_analyze(self, *a):
        if self._busy:
            return
        if not self._source or not self._dest:
            self._status.text = "Pick a source and destination folder first."
            return
        if os.path.abspath(self._source) == os.path.abspath(self._dest):
            self._status.text = "Source and destination can't be the same folder."
            return

        self._busy = True
        self._analyze_btn.disabled = True
        self._start_btn.disabled = True
        self._status.text = "Analyzing..."
        self._log_lbl.text = ""
        recursive = self._recursive_cb.active
        source, dest = self._source, self._dest

        def worker():
            pairs = collect_files_with_relpaths(source, recursive)
            total_size = sum(
                (os.path.getsize(p) for p, _ in pairs if os.path.exists(p)),
                0)
            avg_size = (total_size / len(pairs)) if pairs else 0
            rotational = detect_rotational(dest)
            concurrency, reason = recommend_concurrency(
                len(pairs), avg_size, rotational)
            write_speed = quick_write_probe(dest)
            Clock.schedule_once(lambda dt: self._on_analyze_done(
                pairs, total_size, avg_size, rotational, concurrency,
                reason, write_speed))

        threading.Thread(target=worker, daemon=True).start()

    def _on_analyze_done(self, pairs, total_size, avg_size, rotational,
                          concurrency, reason, write_speed):
        self._busy = False
        self._analyze_btn.disabled = False
        self._pairs = pairs
        self._start_btn.disabled = (len(pairs) == 0)
        self._concurrency_input.text = str(concurrency)

        disk_note = {True: "spinning hard drive (or reports as one)",
                     False: "SSD/NVMe-like (non-rotational)",
                     None: "couldn't determine"}[rotational]
        speed_note = (f"{write_speed:.0f} MB/s measured" if write_speed
                     else "couldn't measure")

        self._recommend_lbl.text = (
            f"Recommended: {concurrency} - {reason}")
        self._status.text = (
            f"{len(pairs)} files, {_fmt_size(total_size)} total, "
            f"avg {_fmt_size(avg_size)}/file. Destination: {disk_note}, "
            f"write speed: {speed_note}.")
        self._log_lbl.text = (
            "Analyze complete. Adjust concurrency above if you want, "
            "then Start Transfer." if pairs else
            "No files found in the source folder.")

    # ── transfer ─────────────────────────────────────────────────────────
    def _run_transfer(self, *a):
        if self._busy or not self._pairs:
            return
        try:
            concurrency = max(1, int(self._concurrency_input.text or "1"))
        except ValueError:
            concurrency = 1

        self._busy = True
        self._stop_requested = False
        self._analyze_btn.disabled = True
        self._start_btn.disabled = True
        self._stop_btn.disabled = False
        self._transferred_bytes = 0
        self._done_count = 0
        self._error_lines = []
        self._log_lbl.text = ""

        pairs = self._pairs
        dest = self._dest
        mode = "move" if self._mode_spinner.text == "Move" else "copy"
        overwrite = self._overwrite_cb.active
        total = len(pairs)
        t_start = time.time()

        def log(msg):
            pass  # per-file wait_for_stable_file chatter isn't shown live;
                  # errors are surfaced via on_result below instead

        def on_result(status, abs_path, dest_path, extra):
            if status == "done":
                self._done_count += 1
                self._transferred_bytes += (extra or 0)
            elif status == "error":
                self._error_lines.append(f"ERROR {abs_path}: {extra}")
            elapsed = max(time.time() - t_start, 1e-6)
            speed = (self._transferred_bytes / elapsed) / (1024 * 1024)
            Clock.schedule_once(lambda dt: setattr(
                self._status, "text",
                f"Transferring... {self._done_count}/{total} files, "
                f"{speed:.1f} MB/s"))

        def worker():
            run_transfer(pairs, dest, mode, concurrency, overwrite=overwrite,
                        stop_check=lambda: self._stop_requested,
                        log=log, on_result=on_result)
            Clock.schedule_once(lambda dt: self._on_transfer_done())

        threading.Thread(target=worker, daemon=True).start()

    def _request_stop(self, *a):
        self._stop_requested = True
        self._stop_btn.disabled = True
        self._status.text = "Stopping... (finishing files already in flight)"

    def _on_transfer_done(self):
        self._busy = False
        self._analyze_btn.disabled = False
        self._stop_btn.disabled = True
        self._pairs = None
        self._start_btn.disabled = True
        n_errors = len(self._error_lines)
        self._status.text = (
            f"Done. {self._done_count} transferred"
            f"{f', {n_errors} error(s)' if n_errors else ''}. "
            f"Re-run Analyze before transferring again.")
        self._log_lbl.text = ("\n".join(self._error_lines) if self._error_lines
                              else "All files transferred with no errors.")

    # ── nav ──────────────────────────────────────────────────────────────
    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"
