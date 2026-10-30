"""feedback_kit - a small, dependency-free "Leave Feedback" system you can copy into any Python app.

    from feedback_kit import FeedbackConfig
    cfg = FeedbackConfig("My App", "1.2.0", "support@example.com")        # + endpoint="https://..." for silent send
    from feedback_kit.pygame_ui import run as feedback_form               # pygame form
    feedback_form(pygame, display, cfg)

The core (this package minus pygame_ui) has no third-party imports, so any other UI can reuse it."""
from .core import FeedbackConfig, REPORT_TYPES, Report, validate, build_subject, build_body
from .sysinfo import collect_system_info, format_system_info
from .transport import send_report, SendResult

__all__ = ["FeedbackConfig", "REPORT_TYPES", "Report", "validate", "build_subject", "build_body",
           "collect_system_info", "format_system_info", "send_report", "SendResult"]
