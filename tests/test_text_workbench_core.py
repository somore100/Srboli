# tests/test_text_workbench_core.py - python3 tests/test_text_workbench_core.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import text_workbench_core as c

A = c.apply_lines
assert A("sort", "b\nA\nc") == "A\nb\nc"
assert A("sort", "b\nA\nc", ignore_case=True) == "A\nb\nc"
assert A("sort_desc", "a\nb") == "b\na"
assert A("natural", "f10\nf2\nf1") == "f1\nf2\nf10"
assert A("numeric", "10 x\n2 y\nzzz") == "2 y\n10 x\nzzz"
assert A("by_length", "ccc\na\nbb") == "a\nbb\nccc"
assert A("reverse", "1\n2\n3") == "3\n2\n1"
assert sorted(A("shuffle", "1\n2\n3\n4", seed=1).split("\n")) == ["1", "2", "3", "4"]
assert A("shuffle", "1\n2\n3\n4", seed=5) == A("shuffle", "1\n2\n3\n4", seed=5)
assert A("dedupe", "a\nb\na\nA") == "a\nb\nA"
assert A("dedupe", "a\nb\na\nA", ignore_case=True) == "a\nb"
assert A("dupes", "a\nb\na\nc\nb") == "a\nb"
assert A("blank", "a\n\n  \nb") == "a\nb"
assert A("trim", "  a  \n b") == "a\nb"
assert A("squeeze", "a   b\t\tc") == "a b c"
assert A("keep", "apple\nbanana\ncherry", "an") == "banana"
assert A("drop", "apple\nbanana\ncherry", "an") == "apple\ncherry"
assert A("keep", "Apple\nbob", "APP", ignore_case=True) == "Apple"
assert A("keep_re", "a1\nb\nc22", r"\d") == "a1\nc22"
assert A("drop_re", "a1\nb\nc22", r"\d") == "b"
assert A("prefix", "a\nb", "- ") == "- a\n- b"
assert A("suffix", "a\nb", ";") == "a;\nb;"
assert A("number", "a\nb") == "1. a\n2. b"
assert A("upper", "ab") == "AB" and A("lower", "AB") == "ab" and A("title", "hi there") == "Hi There"
assert A("join", "a\nb\nc", ", ") == "a, b, c"
assert A("split", "a,b,c", ",") == "a\nb\nc"
assert A("wrap", "aaaa bbbb cccc", "9") == "aaaa bbbb\ncccc"
for bad in (("keep", "x", ""), ("wrap", "x", "abc"), ("wrap", "x", "2"), ("keep_re", "x", "(")):
    try:
        A(*bad); raise SystemExit(f"should fail: {bad}")
    except c.TextError:
        pass
try:
    A("nope", "x"); raise SystemExit("unknown op")
except c.TextError:
    pass
try:
    A("sort", "x" * (c.MAX_CHARS + 1)); raise SystemExit("too big")
except c.TextError:
    pass

E = c.extract
t = "Mail a@b.com, x.y@z.org or a@b.com. See https://ex.com/a?b=1, www.foo.net! 10.0.0.1 and 999.1.1.1. 3.5 and -2. 2026-11-17 17.11.2026 #tag"
assert E("emails", t)[0] == ["a@b.com", "x.y@z.org"]
assert E("emails", t, unique=False)[0].count("a@b.com") == 2
assert E("urls", t)[0] == ["https://ex.com/a?b=1", "www.foo.net"]
assert "10.0.0.1" in E("ipv4", t)[0] and "999.1.1.1" not in E("ipv4", t)[0]
assert E("numbers", "3.5 and -2 and 7")[0] == ["3.5", "-2", "7"]
assert E("dates", t)[0] == ["2026-11-17", "17.11.2026"]
assert E("hashtags", t)[0] == ["#tag"]
assert E("quoted", 'say "hi there" and "bye"')[0] == ["hi there", "bye"]
assert E("words", "Don't stop-now 42")[0] == ["Don't", "stop-now"]
assert E("emails", "none")[1] == ""
assert E("words", "b a c", sort=True)[1] == "a\nb\nc"

m = c.regex_matches(r"(\d+)-(?P<w>\w+)", "12-ab 3-c")
assert [x[2] for x in m] == ["12-ab", "3-c"] and m[0][3] == ["12", "ab"] and m[0][4] == {"w": "ab"}
assert c.regex_matches("a", "A", ignore_case=True)
assert not c.regex_matches("a", "A")
assert c.regex_matches("^b", "a\nb", multiline=True)
assert c.regex_matches("a.b", "a\nb", dotall=True) and not c.regex_matches("a.b", "a\nb")
assert "2 matches" in c.regex_report(r"\d", "1 2") and c.regex_report("z", "a") == "No match."
assert c.regex_replace(r"(\d+)", r"<\1>", "a1 b22") == ("a<1> b<22>", 2)
assert c.regex_replace(r"(?P<n>\d)", r"[\g<n>]", "7") == ("[7]", 1)
for f in (lambda: c.regex_matches("(", "x"), lambda: c.regex_matches("", "x"),
          lambda: c.regex_replace("a", r"\9", "a")):
    try:
        f(); raise SystemExit("regex should fail")
    except c.TextError:
        pass
assert len(c.regex_matches("a", "a" * 600)) == 500

d, (add, rem, blocks) = c.diff_texts("a\nb\nc", "a\nB\nc\nd")
assert (add, rem, blocks) == (2, 1, 2) and "- b" in d and "+ B" in d and "+ d" in d and "  a" in d
assert c.diff_texts("a", "a")[1] == (0, 0, 0)
assert c.diff_texts("a  b", "a b", ignore_space=True)[1] == (0, 0, 0)
assert c.diff_texts("A", "a", ignore_case=True)[1] == (0, 0, 0)
many_a = "\n".join(str(i) for i in range(30)); many_b = many_a.replace("15", "x")
short = c.diff_texts(many_a, many_b, context=1)[0]
assert "..." in short and len(short.splitlines()) < 12

s = c.stats("Hello world. Hello again!\n\nSecond paragraph here.")
assert s["words"] == 7 and s["lines"] == 3 and s["paragraphs"] == 2 and s["sentences"] == 3
assert s["unique_words"] == 6 and s["common"][0] == ("hello", 2)
assert s["longest_line"] == 25
z = c.stats("")
assert z["words"] == 0 and z["avg_word_length"] == 0.0 and z["lines"] == 0
assert "Words: 7" in c.stats_report("Hello world. Hello again!\n\nSecond paragraph here.")
print("text workbench core: all ok")
