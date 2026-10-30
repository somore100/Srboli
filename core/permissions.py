# core/permissions.py - which Android permission a tool needs, and when to ask.
# The app no longer asks for everything at startup: a tool asks the first time
# it is opened, with a one-line reason. Kivy-free, so it is unit-testable.

STORAGE_ROUTES = {"gallery", "file_sorter", "fast_transfer"}
NOTIFY_ROUTES = {"reminders"}

REASONS = {
    "storage": ("This tool works on files outside Srboli's own folder, which "
                "Android only allows with the \"all files access\" permission. "
                "Srboli only touches the folders you pick."),
    "notify": ("Reminders show a notification when they are due. Android needs "
               "your permission for notifications."),
}


def needed(route, on_android, has_storage, has_notify, asked):
    """'storage' / 'notify' when opening `route` should ask, else None.
    `asked` holds the kinds already asked this session (never ask twice)."""
    if not on_android:
        return None
    if route in STORAGE_ROUTES and not has_storage and "storage" not in asked:
        return "storage"
    if route in NOTIFY_ROUTES and not has_notify and "notify" not in asked:
        return "notify"
    return None
