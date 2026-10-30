# Android storage: config + default data live outside the code folder that p4a
# replaces on every update, and old files are migrated once.
import os, sys, json, tempfile, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp()
priv = os.path.join(tmp, "files")
code = os.path.join(priv, "app")
os.makedirs(os.path.join(code, "srboli_data", "config"))
open(os.path.join(code, "srboli_data", "config", "x.json"), "w").write("{}")
json.dump({"data_dir": os.path.join(code, "srboli_data")}, open(os.path.join(code, ".srboli_config.json"), "w"))

os.environ["ANDROID_ARGUMENT"], os.environ["ANDROID_PRIVATE"] = code, priv
import app_data
importlib.reload(app_data)
app_data._APP_ROOT = code
root = os.path.join(priv, "srboli_userdata")
assert app_data._CONFIG_FILE == os.path.join(root, ".srboli_config.json")

d = app_data.get_data_dir()
assert d == os.path.join(root, "data"), d
assert os.path.exists(os.path.join(d, "config", "x.json"))          # data came along
assert not os.path.exists(os.path.join(code, "srboli_data"))
assert not os.path.exists(os.path.join(code, ".srboli_config.json"))
assert json.load(open(app_data._CONFIG_FILE))["data_dir"] == d      # config repointed

# an "update" wipes the code folder; config and data survive
import shutil
shutil.rmtree(code)
app_data._APP_DIR = None
assert app_data.get_data_dir() == d and os.path.exists(os.path.join(d, "config", "x.json"))

# off Android nothing changes
del os.environ["ANDROID_ARGUMENT"], os.environ["ANDROID_PRIVATE"]
importlib.reload(app_data)
assert app_data._ANDROID is None
print("android paths OK")
