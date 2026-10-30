# core/feedback.py - Srboli's settings for the feedback_kit (Kivy-free).
#
# feedback_kit is the shared, app-independent "Leave Feedback" engine; this
# file only says who we are and where the relay endpoint is kept. No
# passwords or API keys live in the app: reports go to a relay URL
# (feedback.json) that forwards them to the support inbox.
import os
import sys

import app_data
from core.version import APP_NAME, VERSION

SUPPORT_EMAIL = "support.somore100@gmail.com"


def _base_dir():
    return getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(app_data.__file__))


def make_config():
    from feedback_kit import FeedbackConfig
    try:
        save_dir = os.path.join(app_data.get_data_dir(), "feedback")
    except Exception:
        save_dir = ""
    return FeedbackConfig.load(APP_NAME, VERSION, SUPPORT_EMAIL,
                               path=os.path.join(_base_dir(), "feedback.json"),
                               save_dir=save_dir)
