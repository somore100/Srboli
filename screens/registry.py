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
    ("binary",         "screens.binary_screen",           "BinaryScreen"),
    ("plotter",        "screens.function_plotter_screen", "FunctionPlotterScreen"),
    ("cover",          "screens.cover_screen",            "CoverScreen"),
    ("backrooms",      "screens.backrooms_screen",        "BackroomsScreen"),
    ("spin",           "screens.spin_screen",             "SpinScreen"),
    ("unhelpful_calc", "screens.unhelpful_calc_screen",   "UnhelpfulCalcScreen"),
    ("shape_gen",      "screens.shape_generator_screen",  "ShapeGeneratorScreen"),
    ("metadata",       "screens.metadata_screen",         "MetadataScreen"),
    ("file_sorter",    "screens.file_sorter_screen",      "FileSorterScreen"),
    ("reminders",      "screens.reminders_screen",        "RemindersScreen"),
    ("fast_transfer",  "screens.fast_transfer_screen",    "FastTransferScreen"),
    ("quickswitcher",  "screens.quickswitcher_screen",    "QuickSwitcherScreen"),
    ("minesweeper",    "screens.minesweeper_screen",      "MinesweeperScreen"),
    ("chess",          "screens.chess_screen",            "ChessScreen"),
    ("touch_test",     "screens.touch_test_screen",       "TouchTestScreen"),
    ("converter",      "screens.file_converter_screen",   "FileConverterScreen"),
    ("learn",          "screens.learn_screen",            "LearnScreen"),
    ("shortcut",       "screens.shortcut_screen",         "ShortcutScreen"),
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
    "image_text":     "File to Base64",
    "morse":          "Morse Converter",
    "binary":         "Binary / Hex Converter",
    "plotter":        "Function Plotter",
    "cover":          "Cover / Privacy Boxes",
    "backrooms":      "Backrooms",
    "spin":           "Wheel of Names",
    "unhelpful_calc": "Unhelpful Calc",
    "shape_gen":      "Shape Generator",
    "metadata":       "Metadata Inspector",
    "file_sorter":    "File Sorter",
    "reminders":      "Reminders",
    "fast_transfer":  "Fast File Transfer",
    "quickswitcher":  "Quick Switcher",
    "minesweeper":    "Minesweeper",
    "chess":          "Chess",
    "touch_test":     "Touch Test",
    "converter":      "File Converter",
    "learn":          "Learn (AI courses)",
    "shortcut":       "Linux Shortcut Creator",
}


# Extra words the Dashboard search matches besides the tool's name.
ALIASES = {
    "image_text":     ["base64", "encode", "decode", "image", "ocr", "file"],
    "text_editor":    ["notes", "markdown", "json", "write", "txt"],
    "full_editor":    ["document", "word", "slides", "presentation", "table",
                       "outline", "docs"],
    "script_mode":    ["prompter", "teleprompter", "script"],
    "learn":          ["course", "quiz", "study", "ai"],
    "file_sorter":    ["rules", "organize", "move files", "clean"],
    "fast_transfer":  ["copy", "move", "speed", "usb", "backup"],
    "converter":      ["pdf", "docx", "convert", "image", "format"],
    "gallery":        ["photos", "pictures", "images", "video"],
    "metadata":       ["exif", "info", "properties"],
    "music":          ["audio", "player", "mp3", "playlist"],
    "shape_gen":      ["draw", "geometry", "svg"],
    "basic_tools":    ["calculator", "calc", "unit", "convert"],
    "plotter":        ["graph", "function", "math", "chart"],
    "random_tools":   ["dice", "random", "coin", "pick"],
    "binary":         ["hex", "bits", "base"],
    "morse":          ["code", "dots"],
    "system_stats":   ["cpu", "ram", "memory", "monitor", "overlay"],
    "reminders":      ["todo", "alarm", "notification", "timer"],
    "loading_timer":  ["stopwatch", "countdown", "timer"],
    "quickswitcher":  ["hotkey", "shortcut", "keybind"],
    "cover":          ["privacy", "blackout", "hide screen"],
    "shortcut":       ["desktop", "launcher", "icon", ".desktop", "linux"],
    "touch_test":     ["tap", "screen", "multitouch"],
    "minesweeper":    ["game", "mines"],
    "chess":          ["game", "board"],
    "spin":           ["wheel", "random", "names", "game"],
    "backrooms":      ["levels", "wiki", "game"],
    "unhelpful_calc": ["joke", "calculator", "fun"],
}


# The Dashboard shows the tools in these sections, in this order (inside a
# section the user's own order from Settings applies). Each tool is in exactly
# one section; a tool missing here (e.g. a screen added later) lands in an
# automatic "Other" section, so nothing can silently disappear.
GROUPS = [
    ("writing", "Writing",
     ["text_editor", "full_editor", "script_mode", "learn"]),
    ("files", "Files",
     ["file_sorter", "fast_transfer", "converter", "gallery", "metadata",
      "image_text"]),
    ("media", "Media",
     ["music", "shape_gen"]),
    ("math", "Math and data",
     ["basic_tools", "plotter", "random_tools", "binary", "morse"]),
    ("system", "System",
     ["system_stats", "reminders", "loading_timer", "quickswitcher", "cover",
      "shortcut", "touch_test"]),
    ("fun", "Fun",
     ["minesweeper", "chess", "spin", "backrooms", "unhelpful_calc"]),
]


def default_route_order():
    """Canonical fallback order — the order SCREENS is declared in above."""
    return [route for route, _, _ in SCREENS]
