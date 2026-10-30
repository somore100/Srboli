# pytest entry point. The tests/test_*.py files are stand-alone scripts (plain
# asserts at module level, run with `python3 tests/test_x.py`), so pytest must
# not import them itself; tests/test_scripts.py runs each one in a subprocess.
def pytest_ignore_collect(collection_path, config):
    n = collection_path.name
    return n.startswith("test_") and n != "test_scripts.py"
