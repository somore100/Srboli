# core/disk_usage_core.py - where did the space go?
# Pure Python (standard library only), no Kivy. One pass over a folder builds a
# tree of folder sizes, the biggest files and a per-kind breakdown. Nothing is
# ever changed or deleted by this module.
#
#   scan(root, progress, cancelled)  -> Scan
#   rows(node)                       -> the lines for one folder (biggest first)
#   Scan.largest / Scan.types / Scan.total ...

import heapq
import os
import shutil

from core.file_inspect_core import human_size

TOP_FILES = 100
MAX_ENTRIES = 3_000_000          # stop (and say so) beyond this many files

KINDS = {
    "Pictures":  {"jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "tif", "tiff", "svg", "raw", "cr2", "nef", "ico"},
    "Video":     {"mp4", "mkv", "avi", "mov", "wmv", "webm", "flv", "m4v", "mpg", "mpeg", "3gp"},
    "Audio":     {"mp3", "wav", "flac", "ogg", "m4a", "aac", "opus", "wma", "mid"},
    "Documents": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "txt", "md", "rtf", "epub", "csv"},
    "Archives":  {"zip", "7z", "rar", "tar", "gz", "bz2", "xz", "tgz", "iso", "img", "dmg", "apk", "deb", "rpm"},
    "Code":      {"py", "js", "ts", "java", "c", "cpp", "h", "cs", "go", "rs", "php", "rb", "html", "css", "json", "xml", "yml", "yaml", "sh", "kt", "swift"},
    "Programs":  {"exe", "dll", "so", "msi", "appimage", "bin", "app", "jar"},
}
_EXT_KIND = {e: k for k, exts in KINDS.items() for e in exts}


def kind_of(name):
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    return _EXT_KIND.get(ext, "Other")


class Node:
    """One folder: total size of everything inside it, and its sub-folders."""
    __slots__ = ("name", "path", "size", "own", "files", "children", "parent", "denied")

    def __init__(self, name, path, parent=None):
        self.name, self.path, self.parent = name, path, parent
        self.size = 0            # everything inside, including sub-folders
        self.own = 0             # files directly in this folder
        self.files = 0           # files inside, all levels
        self.children = []
        self.denied = False


class Scan:
    def __init__(self, root):
        self.root = root
        self.largest = []        # [(size, path)] biggest first
        self.types = {}          # kind -> [size, count]
        self.files = 0
        self.folders = 0
        self.errors = 0          # entries that couldn't be read
        self.stopped = ""        # "", "cancelled" or "limit"
        self.free = self.disk_total = None

    @property
    def total(self):
        return self.root.size


def scan(root, progress=None, cancelled=None, top=TOP_FILES, same_device=True,
         max_entries=MAX_ENTRIES):
    """Walk `root` once. Symlinks are not followed or counted (they would count
    twice). With same_device (the default) other drives mounted inside the
    folder are skipped, like `du -x`. progress(files, size) is called now and
    then; cancelled() -> True stops early (the partial result is still usable)."""
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        raise NotADirectoryError("That isn't a folder.")
    try:
        root_dev = os.stat(root).st_dev
    except OSError:
        root_dev = None
    result = Scan(os.path.basename(root) or root)
    top_node = Node(result.root, root)
    result.root = top_node
    heap = []                    # min-heap of (size, path) for the biggest files
    stack = [top_node]
    tick = 0
    while stack:
        node = stack.pop()
        result.folders += 1
        try:
            it = os.scandir(node.path)
        except OSError:
            node.denied = True
            result.errors += 1
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if same_device and root_dev is not None:
                            try:
                                if entry.stat(follow_symlinks=False).st_dev != root_dev:
                                    continue
                            except OSError:
                                pass
                        child = Node(entry.name, entry.path, node)
                        node.children.append(child)
                        stack.append(child)
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        node.own += size
                        node.files += 1
                        result.files += 1
                        k = kind_of(entry.name)
                        t = result.types.setdefault(k, [0, 0])
                        t[0] += size
                        t[1] += 1
                        if len(heap) < top:
                            heapq.heappush(heap, (size, entry.path))
                        elif size > heap[0][0]:
                            heapq.heapreplace(heap, (size, entry.path))
                except OSError:
                    result.errors += 1
                tick += 1
                if tick % 500 == 0:
                    if progress:
                        progress(result.files, sum(v[0] for v in result.types.values()))
                    if cancelled and cancelled():
                        result.stopped = "cancelled"
                        break
                if result.files >= max_entries:
                    result.stopped = "limit"
                    break
        if result.stopped:
            break
    _roll_up(top_node)
    result.largest = sorted(heap, reverse=True)
    try:
        du = shutil.disk_usage(root)
        result.free, result.disk_total = du.free, du.total
    except OSError:
        pass
    if progress:
        progress(result.files, top_node.size)
    return result


def _roll_up(top):
    """size/files of every folder = its own files + its sub-folders. Folders are
    listed parent-first, so going backwards finishes every child before its parent."""
    order, stack = [], [top]
    while stack:
        n = stack.pop()
        order.append(n)
        stack.extend(n.children)
    for n in reversed(order):
        n.size += n.own
        if n.parent is not None:
            n.parent.size += n.size
            n.parent.files += n.files


def flatten(root, expanded, per_folder=40):
    """The visible lines of the whole tree, QDirStat style: a folder's children
    follow it (indented) while its path is in `expanded`. Each line is
    (depth, label, size, share_of_parent, node_or_None, kind) with kind
    'folder', 'files' or 'more'. Only the `per_folder` biggest entries of a
    folder are listed; the rest are summed in one 'more' line."""
    out = []

    def walk(node, depth):
        entries = rows(node, limit=None)
        shown, rest = entries[:per_folder], entries[per_folder:]
        for label, size, share, kind, child in shown:
            out.append((depth, label, size, share, child, kind))
            if child is not None and child.path in expanded:
                walk(child, depth + 1)
        if rest:
            total = sum(r[1] for r in rest)
            out.append((depth, f"[{len(rest)} more smaller entries]", total,
                        total / (node.size or 1), None, "more"))

    walk(root, 0)
    return out


def big_paths(root, min_share=0.05, max_depth=3):
    """Paths of the folders worth opening by default: every folder holding at
    least `min_share` of the whole scan, down to `max_depth` levels."""
    total = root.size or 1
    found, stack = {root.path}, [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if depth >= max_depth:
            continue
        for c in node.children:
            if c.children and c.size / total >= min_share:
                found.add(c.path)
                stack.append((c, depth + 1))
    return found


def rows(node, limit=200):
    """[(label, size, share 0-1, kind, node_or_None)] for one folder: its
    sub-folders and one 'files here' line, biggest first. kind is 'folder' or 'files'."""
    total = node.size or 1
    out = [(c.name + ("  (no access)" if c.denied else ""), c.size, c.size / total, "folder", c)
           for c in node.children]
    if node.own:
        out.append((f"[{node.files - sum(c.files for c in node.children)} files in this folder]",
                    node.own, node.own / total, "files", None))
    out.sort(key=lambda r: r[1], reverse=True)
    return out if limit is None else out[:limit]


def bar(share, width=12):
    full = max(0, min(width, round(share * width)))
    return "#" * full + "." * (width - full)


def type_rows(scan_result):
    """[(kind, size, count, share)] biggest first."""
    total = scan_result.total or 1
    items = [(k, v[0], v[1], v[0] / total) for k, v in scan_result.types.items()]
    items.sort(key=lambda r: r[1], reverse=True)
    return items


def report(scan_result, node=None):
    """A plain-text summary (for copying)."""
    node = node or scan_result.root
    lines = [f"{node.path}", f"Total: {human_size(node.size)} in {node.files:,} files"]
    if scan_result.free is not None and node is scan_result.root:
        lines.append(f"Disk: {human_size(scan_result.free)} free of {human_size(scan_result.disk_total)}")
    if scan_result.stopped:
        lines.append("(scan stopped early: " + ("you stopped it" if scan_result.stopped == "cancelled"
                                               else "too many files") + ")")
    lines += ["", "Biggest folders:"]
    for label, size, share, kind, _n in rows(node, 15):
        lines.append(f"  {human_size(size):>12}  {share * 100:5.1f}%  {label}")
    lines += ["", "Biggest files:"]
    for size, path in scan_result.largest[:15]:
        lines.append(f"  {human_size(size):>12}  {path}")
    lines += ["", "By kind:"]
    for k, size, count, share in type_rows(scan_result):
        lines.append(f"  {human_size(size):>12}  {share * 100:5.1f}%  {k} ({count:,} files)")
    if scan_result.errors:
        lines.append(f"\n{scan_result.errors} item(s) could not be read.")
    return "\n".join(lines)
