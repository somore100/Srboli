"""Report data, validation and the structured email text."""
import json
import os
from dataclasses import dataclass, field

# (label shown to the user, tag used in the subject line)
REPORT_TYPES = [("Bug Report", "BUG"), ("Feature Suggestion", "FEATURE"), ("General Feedback", "FEEDBACK"),
                ("Question", "QUESTION"), ("Other", "OTHER")]

MAX_TITLE, MAX_NAME, MAX_DESC = 120, 60, 4000


@dataclass
class FeedbackConfig:
    app_name: str
    app_version: str
    to_email: str
    endpoint: str = ""                   # relay URL (see apps_script.gs); empty -> open the user's mail app instead
    save_dir: str = ""                   # where a copy of each report is kept (used by the mail-app fallback)

    @classmethod
    def load(cls, app_name, app_version, to_email, path="feedback.json", save_dir=""):
        """Reads {"endpoint": "..."} from path (or the FEEDBACK_ENDPOINT environment variable). Nothing secret goes here."""
        endpoint = os.environ.get("FEEDBACK_ENDPOINT", "")
        try:
            with open(path) as fh:
                endpoint = endpoint or json.load(fh).get("endpoint", "")
        except (OSError, ValueError):
            pass
        return cls(app_name, app_version, to_email, endpoint.strip(), save_dir)


@dataclass
class Report:
    type_index: int = 0
    name: str = ""
    title: str = ""
    description: str = ""
    system: dict = field(default_factory=dict)      # empty unless the user ticked the box

    @property
    def type_label(self):
        return REPORT_TYPES[self.type_index][0]

    @property
    def type_tag(self):
        return REPORT_TYPES[self.type_index][1]


def validate(r):
    """Returns a list of problems (empty when the report can be sent)."""
    errs = []
    if not r.title.strip():
        errs.append("Please enter a title.")
    elif len(r.title.strip()) < 4:
        errs.append("The title is too short.")
    if not r.description.strip():
        errs.append("Please describe the problem or suggestion.")
    elif len(r.description.strip()) < 10:
        errs.append("The description is too short to be useful.")
    return errs


def build_subject(cfg, r):
    return f"[{cfg.app_name}] [{r.type_tag}] {' '.join(r.title.split())[:MAX_TITLE]}"


def build_body(cfg, r):
    from .sysinfo import format_system_info
    lines = ["== FEEDBACK REPORT ==",
             f"App:      {cfg.app_name}",
             f"Version:  {cfg.app_version}",
             f"Type:     {r.type_label}",
             f"From:     {r.name.strip() or '(not given)'}",
             f"Title:    {' '.join(r.title.split())}",
             "", "== DESCRIPTION ==", r.description.strip(), ""]
    if r.system:
        lines += ["== SYSTEM (sent because the user ticked the box) =="] + format_system_info(r.system) + [""]
    else:
        lines += ["== SYSTEM ==", "(not included)", ""]
    return "\n".join(lines)
