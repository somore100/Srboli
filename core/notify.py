# core/notify.py — OS-native "toast" notifications for fired reminders.
#
# Kivy-free (the daemon that calls this never imports Kivy). Best-effort
# by design: a notification failing (missing notify-send, no display
# server, PowerShell blocked by policy, whatever) should never take the
# daemon down — it just logs and moves on. `runner` is injectable so
# tests can check exactly what would have been run without needing the
# real notifier installed.

import os
import time
import platform
import subprocess

DEFAULT_TIMEOUT = 5


def _escape_applescript(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _escape_powershell(s):
    # Inside a PowerShell double-quoted string: backtick escapes, and a
    # literal double-quote is doubled.
    return s.replace("`", "``").replace('"', '""').replace("$", "`$")


def _linux_command(title, message):
    return ["notify-send", "--app-name=Srboli", title, message]


def _macos_command(title, message):
    script = (f'display notification "{_escape_applescript(message)}" '
             f'with title "{_escape_applescript(title)}"')
    return ["osascript", "-e", script]


def _windows_command(title, message):
    t, m = _escape_powershell(title), _escape_powershell(message)
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, "
        "Windows.UI.Notifications, ContentType = WindowsRuntime] > $null\n"
        "$xml = [Windows.UI.Notifications.ToastNotificationManager]::"
        "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::"
        "ToastText02)\n"
        "$text = $xml.GetElementsByTagName('text')\n"
        f'$text[0].AppendChild($xml.CreateTextNode("{t}")) > $null\n'
        f'$text[1].AppendChild($xml.CreateTextNode("{m}")) > $null\n'
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)\n"
        "[Windows.UI.Notifications.ToastNotificationManager]::"
        "CreateToastNotifier('Srboli').Show($toast)\n"
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]


_COMMAND_BUILDERS = {
    "Linux": _linux_command,
    "Darwin": _macos_command,
    "Windows": _windows_command,
}


def _is_android():
    return "ANDROID_ARGUMENT" in os.environ


def _android_notify(title, message):
    """Post a notification through Android's NotificationManager (pyjnius).
    Needs the POST_NOTIFICATIONS permission on Android 13+."""
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        Build = autoclass("android.os.Build$VERSION")
        NotificationManager = autoclass("android.app.NotificationManager")
        NotificationChannel = autoclass("android.app.NotificationChannel")
        Builder = autoclass("android.app.Notification$Builder")
        ctx = PythonActivity.mActivity
        nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE)
        chan_id = "srboli_reminders"
        nm.createNotificationChannel(NotificationChannel(
            chan_id, "Reminders", NotificationManager.IMPORTANCE_HIGH))
        b = Builder(ctx, chan_id)
        b.setContentTitle(str(title))
        b.setContentText(str(message))
        b.setSmallIcon(ctx.getApplicationInfo().icon)
        b.setAutoCancel(True)
        nm.notify(int(time.time()) & 0x7FFFFFFF, b.build())
        return True
    except Exception as e:
        print(f"Srboli notify (android): failed ({e})")
        return False


def send_notification(title, message, runner=None, system=None):
    """Show `title`/`message` as a native notification. Returns True if
    the notifier command ran without error, False otherwise (missing
    binary, non-zero exit, unsupported OS) — never raises.

    `runner` defaults to subprocess.run; tests pass a fake to record the
    call instead of needing notify-send/osascript/powershell installed.
    `system` defaults to platform.system(); tests override it to
    exercise all three OS branches from one machine.
    """
    if runner is None and system is None and _is_android():
        return _android_notify(title, message)
    runner = runner or subprocess.run
    system = system or platform.system()
    build = _COMMAND_BUILDERS.get(system)
    if build is None:
        print(f"Srboli notify: no notifier for platform {system!r}")
        return False
    cmd = build(str(title), str(message))
    try:
        result = runner(cmd, timeout=DEFAULT_TIMEOUT,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = getattr(result, "returncode", 0) == 0
        if not ok:
            print(f"Srboli notify: {cmd[0]} exited "
                 f"{getattr(result, 'returncode', '?')}")
        return ok
    except FileNotFoundError:
        print(f"Srboli notify: {cmd[0]} not found — no notification shown")
        return False
    except Exception as e:
        print(f"Srboli notify: failed ({e})")
        return False
