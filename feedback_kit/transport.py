"""Delivering a report. No credentials live in the app:
  1. endpoint set  -> HTTP POST (JSON) to a relay you own (apps_script.gs forwards it to your inbox);
  2. no endpoint   -> the user's own mail app opens with the report filled in (they press Send)."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass

from .core import build_body, build_subject, MAX_DESC


@dataclass
class SendResult:
    ok: bool
    message: str
    method: str = ""        # "relay" | "mailto"


def _save_copy(cfg, subject, body):
    if not cfg.save_dir:
        return ""
    try:
        os.makedirs(cfg.save_dir, exist_ok=True)
        path = os.path.join(cfg.save_dir, time.strftime("feedback-%Y%m%d-%H%M%S.txt"))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"To: {cfg.to_email}\nSubject: {subject}\n\n{body}")
        return path
    except OSError:
        return ""


def send_report(cfg, report, timeout=12):
    subject, body = build_subject(cfg, report), build_body(cfg, report)
    if cfg.endpoint:
        payload = json.dumps({"to": cfg.to_email, "subject": subject, "body": body, "app": cfg.app_name, "version": cfg.app_version,
                              "type": report.type_tag}).encode("utf-8")
        req = urllib.request.Request(cfg.endpoint, data=payload, headers={"Content-Type": "text/plain;charset=utf-8"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read(2000).decode("utf-8", "replace")
                if 200 <= resp.status < 300 and '"ok":false' not in text.replace(" ", "").lower():
                    return SendResult(True, "Thank you! Your feedback was sent.", "relay")
                return SendResult(False, f"The server answered {resp.status}. Please try again later.", "relay")
        except urllib.error.HTTPError as e:
            return SendResult(False, f"Could not send (server error {e.code}).", "relay")
        except (urllib.error.URLError, OSError, ValueError):
            copy = _save_copy(cfg, subject, body)
            return SendResult(False, "Could not reach the server - check your connection." + (f" A copy was saved to {copy}" if copy else ""), "relay")
    # no relay configured: hand the report to the user's mail app
    copy = _save_copy(cfg, subject, body)
    mail_body = body if len(body) < 1800 else body[:1700] + "\n...\n(shortened - the full report is saved" + (f" at {copy}" if copy else "") + ")"
    url = f"mailto:{cfg.to_email}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(mail_body)}"
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    if opened:
        return SendResult(True, "Your mail app opened with the report filled in - press Send there to deliver it.", "mailto")
    return SendResult(False, f"No mail app could be opened. Please email {cfg.to_email}" + (f" and attach {copy}" if copy else "") + ".", "mailto")
