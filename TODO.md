# Srboli - notes and to-do

Keep this up to date: it is where a new session (or a new contributor) looks
to see what is half-done and what is planned. Newest decisions first.

## Ideas (not started)

- Dashboard: tile layout (2-3 per row on wide windows), user-made sections,
  pinned favourites (today only the automatic Recent row), a section order
  setting. Sections are fixed in `screens/registry.py` (GROUPS).

## Done recently

- **Dashboard** (`main.py` Dashboard, `core/dashboard_core.py`, `GROUPS` in
  `screens/registry.py`): search box, Recent row (last 4 used), collapsible
  sections with their folded state remembered. Settings lists the same
  sections and moves a screen within its section; hide still works. New
  settings keys `recent` / `collapsed` are written only by the Dashboard
  (Settings can't overwrite them with a stale copy). A tool no section lists
  shows under "Other".

- **Linux shortcut creator** (`screens/shortcut_screen.py`, `core/desktop_entry.py`):
  name / command / icon / categories / terminal, preview, create, list + edit +
  delete (only files it made, marked `X-Srboli-Created`). Later: Windows `.lnk`
  files; an "icon picker" from the theme; MIME types / `%f` file arguments.

- **File safety** (`core/file_safety.py`, `core/transfer_core.py`): files are only
  touched when not empty, quiet for N seconds (File Sorter has a setting; default 5),
  no editor lock file, and not open for writing by another program (Linux: /proc;
  Windows: exclusive-open test). Copies/moves write a hidden temp name, verify, then
  rename; a cross-disk move deletes the original last. Fast Transfer: old files
  skip the wait (it used to sleep ~0.45 s per file), worker cap 64 (warns above 16),
  Auto-tune replaces the 4 MB "bandwidth test". Later: macOS open-file detection
  (lsof); a settle-seconds field in Fast Transfer; hash verification option;
  Auto-tune for a few LARGE files (it only samples smaller ones).

## Full Editor roadmap

Done:
1. Outline document: nested sections, Markdown bodies, formatting bar with
   colour swatches + wheel, preview, section previews in the tree.
2. Coloured tables replace the Sheet tab; `[[table:Name]]` places one in a section.
3. Slides are derived from the outline (`core/slides_core.py`): a mode switch
   (sub-sections as separate slides / as bullets), optional title slide,
   per-slide background / text colour / image / skip, presenter. Old
   hand-written slides are imported as a "Slides (imported)" section.

Known limits / later:
- Tree and editor sit side by side; on a narrow phone screen show one at a time.
- Leaving the Full Editor through a global shortcut or the dashboard skips the
  unsaved-changes prompt (only the in-editor Back button asks).
- A formula cell keeps only its result, not the formula.
- The formatting-bar logic in `screens/md_editor.py` is copied from
  `screens/text_editor_screen.py`; the two could share one implementation.
- Recent colours (`RECENT_COLORS` in `screens/md_editor.py`) reset on restart.
- The colour strip exists three times: `MarkdownEditor`, the Tables panel and
  `ColorStrip` (used by the Slides panel). Move the first two onto `ColorStrip`.
- Slides: no speaker notes, no per-slide font size, no transitions; slide text
  is rendered as Kivy markup (headings, lists, quotes, code, tables as text rows).
- Slides can't be reordered separately from the outline (reorder the sections).

## Other

- Text Editor `.json` export currently validates and pretty-prints. Confirm
  that is what was wanted (alternatives: a live "format JSON" button, or
  opening `.json` files directly).
- Syncthing keeps leaving `*.sync-conflict-*` files in the project; delete
  them once nothing in them is needed (compare first).
