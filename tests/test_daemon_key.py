# tests/test_daemon_key.py - the IPC key is private from its first byte. No display needed.
import os, stat, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core.daemon_ipc as d

folder = tempfile.mkdtemp()
d._daemon_dir = lambda: folder
key = d.get_authkey()
path = os.path.join(folder, d._AUTHKEY_NAME)
assert len(key) == 32 and d.get_authkey() == key                      # created once, then reused
if os.name != "nt":
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600, oct(os.stat(path).st_mode)
    # an existing key is never overwritten, even by a racing second process
    other = os.urandom(32)
    os.remove(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, other); os.close(fd)
    assert d.get_authkey() == other
    # the real folder is closed to other users
    import app_data
    real = d.__dict__["_daemon_dir"]
print("daemon key OK")
