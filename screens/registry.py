# screens/registry.py — single source of truth for the screen list.
#
# Previously SCREENS/LABELS lived duplicated in main.py and a near-copy
# (ALL_ROUTES/ROUTE_LABELS) lived in quickswitcher_screen.py. Two copies
# meant they could silently drift out of sync. Everything that needs the
# screen list (main.py, quickswitcher_screen.py, settings_screen.py) now
# imports from here instead.
#
# NOTE: "dashboard" and "settings" are NOT listed here — they're core
# screens wired directly in main.py, not part of the manageable/hideable
# screen list that the Settings screen lets you reorder or hide.

SCREENS = [
    ("loading_timer",  "screens.loading_timer_screen",    "LoadingTimerScreen"),
    ("text_editor",    "screens.text_editor_screen",      "TextEditorScreen"),
    ("script_mode",    "screens.script_mode_screen",      "ScriptModeScreen"),
    ("full_editor",    "screens.full_editor_screen",      "FullEditorScreen"),
    ("basic_tools",    "screens.basic_tools_screen",      "BasicToolsScreen"),
    ("system_stats",   "screens.system_stats_screen",     "SystemStatsScreen"),
    ("gallery",        "screens.gallery_sorter_screen",   "GallerySorterScreen"),
    ("music",          "screens.music_screen",            "MusicScreen"),
    ("random_tools",   "screens.randomizer",              "UtilityToolsScreen"),
    ("image_text",     "screens.image_text_screen",       "ImageTextScreen"),
    ("morse",          "screens.morse_screen",            "MorseScreen"),
    ("backrooms",      "screens.backrooms_screen",        "BackroomsScreen"),
    ("spin",           "screens.spin_screen",             "SpinScreen"),
    ("unhelpful_calc", "screens.unhelpful_calc_screen",   "UnhelpfulCalcScreen"),
    ("shape_gen",      "screens.shape_generator_screen",  "ShapeGeneratorScreen"),
    ("metadata",       "screens.metadata_screen",         "MetadataScreen"),
    ("file_sorter",    "screens.file_sorter_screen",      "FileSorterScreen"),
    ("fast_transfer",  "screens.fast_transfer_screen",    "FastTransferScreen"),
    ("quickswitcher",  "screens.quickswitcher_screen",    "QuickSwitcherScreen"),
]

LABELS = {
    "loading_timer":  "Loading / Timer",
    "text_editor":    "Text Editor",
    "script_mode":    "Script / Teleprompter",
    "full_editor":    "Full Editor",
    "basic_tools":    "Basic Tools",
    "system_stats":   "System Stats",
    "gallery":        "Gallery Sorter",
    "music":          "Music Player",
    "random_tools":   "Randomizer Tools",
    "image_text":     "Image to Text",
    "morse":          "Morse Converter",
    "backrooms":      "Backrooms",
    "spin":           "Wheel of Names",
    "unhelpful_calc": "Unhelpful Calc",
    "shape_gen":      "Shape Generator",
    "metadata":       "Metadata Inspector",
    "file_sorter":    "File Sorter",
    "fast_transfer":  "Fast File Transfer",
    "quickswitcher":  "Quick Switcher",
}


def default_route_order():
    """Canonical fallback order — the order SCREENS is declared in above."""
    return [route for route, _, _ in SCREENS]
