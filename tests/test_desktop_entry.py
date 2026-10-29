# tests/test_desktop_entry.py - no display needed (python3 tests/test_desktop_entry.py)
# Everything is written under a temp dir: HOME / XDG_* point there and
# desktop_dir() is replaced, so the real menu and Desktop are never touched.
import os, sys, stat, tempfile
home = tempfile.mkdtemp()
os.environ["HOME"] = home
os.environ["XDG_DATA_HOME"] = os.path.join(home, "share")
os.environ["XDG_CONFIG_HOME"] = os.path.join(home, "cfg")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import desktop_entry as D

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

# Exec quoting: round trip for awkward arguments
cases = [["srboli"], ["/opt/My App/run", "--flag", "a b"], ["x", "say \"hi\""],
         ["sh", "-c", "echo $HOME `date` \\n 100%"], ["x", ""], ["a'b", "c;d", "(e)"],
         ["python3", "/home/u/dir with space/main.py", "--daemon"]]
for argv in cases:
    check(f"exec round trip {argv!r}", D.parse_exec(D.build_exec(argv)), argv)
check("plain args stay unquoted", D.build_exec(["srboli", "--daemon"]), "srboli --daemon")
check("space is quoted", D.build_exec(["/a b/c"]), '"/a b/c"')
check("percent doubled", D.build_exec(["a%b"]), "a%%b")
check("empty arg kept", D.build_exec(["x", ""]), 'x ""')
try:
    D.parse_exec('x "unterminated'); check("unterminated", False, True)
except ValueError:
    check("unterminated", True, True)

# whole-file round trip, through both escaping layers
argv = ["sh", "-c", "echo \\ \"q\" $x"]
text = D.build_entry("My Tool", argv, comment="line1\nline2", icon="/i.png",
                     terminal=True, categories=["Utility", "Bogus", "Game"], path="/tmp")
e = D.parse_entry(text)
check("entry argv survives", e["argv"], argv)
check("entry fields", (e["name"], e["comment"], e["icon"], e["path"], e["terminal"]),
      ("My Tool", "line1\nline2", "/i.png", "/tmp", True))
check("unknown categories dropped", e["categories"], ["Utility", "Game"])
check("marker set", e["ours"], True)
check("file shape", text.splitlines()[:3], ["[Desktop Entry]", "Type=Application", "Version=1.0"])
check("categories end with ;", "Categories=Utility;Game;" in text, True)
check("newline escaped in file", "Comment=line1\\nline2" in text and "\nline2" not in text, True)
minimal = D.build_entry("A", ["a"])
check("minimal has no optional keys", ("Comment" in minimal, "Icon" in minimal, "Path" in minimal, "Categories" in minimal), (False,) * 4)
check("terminal false", "Terminal=false" in minimal, True)
check("parse ignores other sections and locales",
      D.parse_entry("[Desktop Action x]\nName=no\n[Desktop Entry]\nName=yes\nName[de]=nein\n")["name"], "yes")
check("foreign file is not ours", D.parse_entry("[Desktop Entry]\nName=x\nExec=y\n")["ours"], False)
check("bad exec gives empty argv", D.parse_entry('[Desktop Entry]\nExec=a "b\n')["argv"], [])

# validation
errs, warns = D.validate("", [])
check("empty -> two errors", len(errs), 2)
errs, warns = D.validate("n", ["definitely-not-a-program-xyz"], icon="/no/such.png", path="/no/dir")
check("warnings only", (errs, len(warns)), ([], 3))
errs, warns = D.validate("n", ["sh"])
check("sh found", (errs, warns), ([], []))
check("filename", (D.filename_for("My Tool!"), D.filename_for("***")), ("my-tool.desktop", "shortcut.desktop"))

# install / list / delete
desk = os.path.join(home, "Desktop")
os.makedirs(desk)
D.desktop_dir = lambda: desk
check("not there yet", D.exists("my-tool.desktop"), False)
paths, err = D.install(text, "my-tool.desktop", on_desktop=True)
check("installed both", (err, [os.path.dirname(p) for p in paths]), (None, [D.applications_dir(), desk]))
check("executable bit", all(os.stat(p).st_mode & stat.S_IXUSR for p in paths), True)
check("no tmp left", [f for f in os.listdir(D.applications_dir()) if f.endswith(".tmp")], [])
check("exists", D.exists("my-tool.desktop"), True)
other = os.path.join(D.applications_dir(), "firefox.desktop")
open(other, "w").write("[Desktop Entry]\nName=Firefox\nExec=firefox\n")
check("list only ours", [pe[1]["name"] for pe in D.list_created()], ["My Tool"])
check("refuses foreign launcher", D.delete("firefox.desktop")[0], False)
check("foreign launcher untouched", os.path.isfile(other), True)
check("refuses path tricks", (D.delete("../x.desktop")[0], D.delete("a/b.desktop")[0], D.delete("notes.txt")[0]), (False,) * 3)
check("delete ours", D.delete("my-tool.desktop"), (True, None))
check("both copies gone", (D.exists("my-tool.desktop"), os.path.exists(os.path.join(desk, "my-tool.desktop"))), (False, False))
check("delete missing", D.delete("my-tool.desktop")[0], False)
D.desktop_dir = lambda: None
paths, err = D.install(text, "x.desktop", on_desktop=True)
check("no Desktop folder: menu still written, user told", (len(paths), err is not None), (1, True))

# desktop_dir against the fake HOME
import importlib; importlib.reload(D)
check("desktop_dir uses ~/Desktop", D.desktop_dir(), desk)

print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
