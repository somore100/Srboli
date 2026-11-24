# Srboli - notes and to-do

Keep this up to date: it is where a new session (or a new contributor) looks
to see what is half-done and what is planned. Newest decisions first.

## Ideas (not started)

- Big backlog of possible tools and the rules for keeping the app lean:
  `docs/IDEAS.md`.

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

## Srboli Studio roadmap (replaced the Full Editor in 5.32)

Done (phases 1, 2 and 4 of the concept): infinite canvas with pan/zoom, text and shape
objects, select / move / resize / turn, frames, grouping, layers, undo/redo, `.srbcanvas`
packages with recovery autosave and versioning (`core/studio_core.py`).

Next: phase 3 tables + charts (reuse `core/table_core.py`), images (assets/ folder is
already part of the package), presentation mode from frames, smart text transformation,
import/export (md, txt, csv, html, pdf), connectors between objects.
The old outline / slides / table cores (`outline_core.py`, `slides_core.py`,
`table_core.py`) are kept for those phases; the old Full Editor screen is gone and its
documents in the `full_editor` data folder are untouched but no longer opened by the app.

## Other

- Text Editor `.json` export currently validates and pretty-prints. Confirm
  that is what was wanted (alternatives: a live "format JSON" button, or
  opening `.json` files directly).
- Syncthing keeps leaving `*.sync-conflict-*` files in the project; delete
  them once nothing in them is needed (compare first).
