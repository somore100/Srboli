# tests/test_file_sorter_rules.py - no display needed.
# Rule naming and the "does this list of conditions make sense" check.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core.file_sorter_core import (auto_rule_name, rule_title, rule_one_liner,
                                   condition_problem)

def c(field, op, value=""):
    return {"field": field, "op": op, "value": value}

rule = {"logic": "AND", "conditions": [c("name", "contains", "roblox")],
        "action": {"type": "move", "dest": "/home/videos/roblox"}}
assert auto_rule_name(rule) == "IF File name contains roblox THEN Move TO /home/videos/roblox"
# an auto name is shown once, a custom name with the rule after it
assert rule_title(dict(rule, name=auto_rule_name(rule), auto_name=True)) == auto_rule_name(rule)
assert rule_title(dict(rule, name="Games")).startswith("Games: IF File name")
# a half-built rule (no folder yet) still gives a readable name
half = dict(rule, action={"type": "move", "dest": ""})
assert auto_rule_name(half).endswith("Move TO ?")
assert "keep checking" in rule_one_liner(dict(rule, continue_after_match=True))

# identical conditions are refused, in any logic
same = [c("file_type", "is", "Image"), c("file_type", "is", "Image")]
assert condition_problem(same, "AND") and condition_problem(same, "OR")
assert condition_problem([c("extension", "is_one_of", "jpg, png"),
                          c("extension", "is_one_of", ".PNG,jpg")], "OR")
assert condition_problem([c("meta_has_gps", "is_true", "x"),
                          c("meta_has_gps", "is_true", "")], "AND")
# contradictions only matter for AND
img_vid = [c("file_type", "is", "Image"), c("file_type", "is", "Video")]
assert condition_problem(img_vid, "AND")
assert condition_problem(img_vid, "OR") is None
assert condition_problem([c("file_type", "is", "Image"),
                          c("file_type", "is_not", "Image")], "AND")
assert condition_problem([c("meta_has_gps", "is_true"), c("meta_has_gps", "is_false")], "AND")
# things that are fine
assert condition_problem([c("file_type", "is", "Image"),
                          c("file_type", "is_not", "Video")], "AND") is None
assert condition_problem([c("name", "contains", "a"), c("name", "contains", "b")], "AND") is None
assert condition_problem([c("size", "greater_than", "1MB"), c("size", "less_than", "1GB")], "AND") is None
assert condition_problem([c("file_type", "is", "Image"), c("name", "contains", "a")], "AND") is None
assert condition_problem([], "AND") is None
print("file sorter rules passed")
