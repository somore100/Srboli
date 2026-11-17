# Srboli - screen and feature ideas backlog

Inspiration for future screens and utilities. Source of the list: things people
solve today with "just write a small Python script", "just run this terminal
command", "use an online converter" or "install another app for this one thing".

**The goal is not to implement everything.** It is to find the most useful
missing utilities so someone can solve small computer problems without another
app, website, script or terminal command.

## How we keep Srboli from getting bloated

Decided together; check any new idea against this before building it.

- **Merge, don't multiply.** Related small functions become tabs of ONE screen
  (a "Text Workbench" with tabs, not twelve text screens). The Dashboard is
  already grouped; a new screen has to earn its tile.
- **Extend before adding.** If an existing tool can take the feature (Bulk
  Renamer next to File Sorter's rename action, hashes inside a file inspector),
  put it there.
- **Everything is hideable.** Settings can already hide any screen from the
  Dashboard; nobody pays for a tool they never open (screens load lazily).
- **No new dependencies** unless the gain is large; the Android build stays
  small. Standard library first.
- **Preview before destructive actions, and keep a way back** (the replaced
  folder pattern from Backup/Sync).
- **Estimate the cost first** (core logic with tests, screen, README line) and
  skip ideas that are rare, or do almost what another screen does.

## Suggested order (small, useful, mostly one core file each)

1. **Text Workbench** (one screen, tabs): lines (sort, reverse, dedupe, filter,
   extract emails/URLs/numbers), regex tester, diff, statistics, find/replace.
2. **Bulk Renamer**: rules, numbering, dates, regex, live preview, undo.
3. **File Inspector** (one screen): type by contents, MIME, hashes/checksum
   verify, timestamps, permissions, hex and text preview.
4. **Disk Space Analyzer** and **Duplicate Finder** (share one folder scanner).
5. **Data tools** (one screen, tabs): JSON explorer, CSV table, converter
   (JSON/CSV/TSV/XML/YAML), timestamp, UUID, base converter, URL/escape.
6. Later: PDF toolbox, Clipboard History, Log Viewer, Process/Port/Network
   inspector, Image Batch Editor, HTTP tester.
7. Large projects: Automation Studio, Command Cookbook, Workspace Snapshots.

Mobile note: process/port/network/window/clipboard-history ideas are desktop
only; the Dashboard should simply not list them on Android.

---

## 1. File management and organization

| Screen / utility | Description |
|---|---|
| Bulk Renamer | Batch rename files using rules, regex, numbering, dates, prefixes, suffixes and chained operations. |
| Disk Space Analyzer | Visualize folder sizes, largest files, storage usage and treemap distributions. |
| Duplicate Finder | Find identical files using hashes and similar images using perceptual hashes. |
| File Inspector | Inspect file type, MIME type, metadata, hashes, timestamps, permissions and file signatures. |
| File Timeline | Browse files based on creation and modification dates. |
| File Permissions Editor | GUI for chmod permissions, recursive permission changes and permission previews. |
| Metadata Cleaner | Batch-remove EXIF, GPS and other metadata from files. |
| Checksum Verifier | Generate and verify MD5, SHA-1, SHA-256 and other checksums. |
| File Type Detector | Detect actual file types based on file contents rather than extensions. |
| Contact Sheet Generator | Generate image thumbnail sheets from folders of pictures. |

## 2. Text and data utilities

| Screen / utility | Description |
|---|---|
| Text Workbench | Sort, reverse, shuffle, deduplicate, filter, extract and transform lines of text. |
| Regex Tester | Interactive regular expression testing with live matches, groups and replacements. |
| Text Diff | Compare two text blocks or files and highlight differences. |
| Text Statistics | Word count, character count, line count, reading time and line-length analysis. |
| JSON Explorer | View, edit, validate, format and search JSON in a tree structure. |
| CSV/TSV Explorer | View and edit structured data in a table. |
| Data Converter | Convert between JSON, CSV, TSV, XML and YAML. |
| Timestamp Converter | Convert Unix timestamps into readable dates and vice versa. |
| URL Toolbox | Encode/decode URLs, parse query parameters and inspect URL components. |
| Escape/Unescape Tool | Convert JSON, HTML, Unicode, JavaScript and URL escaped strings. |
| Markdown Table Generator | Convert pasted text or CSV into Markdown tables. |
| SQL Formatter | Format, validate and minify SQL queries. |
| JWT Inspector | Decode JWT headers and payloads and inspect expiration dates. |
| Data Generator | Generate dummy names, emails, numbers, addresses and datasets. |
| UUID Generator | Generate UUID v4 and v7 identifiers. |
| Lorem Ipsum Generator | Generate placeholder text with configurable length. |
| Cron Explainer | Generate and explain cron expressions in plain language. |
| Hash Generator | Calculate text and file hashes using common algorithms. |
| Base Converter | Convert between decimal, binary, hexadecimal and arbitrary number bases. |

## 3. Developer utilities

| Screen / utility | Description |
|---|---|
| HTTP Request Tester | Lightweight Postman alternative for sending HTTP requests and inspecting responses. |
| Log Viewer | View large log files, follow live logs, search and filter messages. |
| Process Inspector | View running processes, resource usage, process trees and command-line arguments. |
| Port Inspector | Find occupied ports, identify the process using them and test port availability. |
| Environment Variable Manager | Inspect environment variables, edit .env files and analyze PATH entries. |
| Command Builder | GUI generators for common terminal commands such as ffmpeg, grep, find, rsync, curl and tar. |
| SQLite Explorer | Open SQLite databases, browse tables and execute queries. |
| API Response Formatter | Format, inspect and search API responses. |
| Local Web Server | Serve a selected folder over HTTP and optionally generate a QR code for access from another device. |
| File Signature Inspector | Inspect hexadecimal file headers and identify file formats. |

## 4. System and desktop utilities

| Screen / utility | Description |
|---|---|
| Clipboard History | Search, pin and reuse previously copied text and images. |
| Network Inspector | View network interfaces, IP addresses, DNS, gateway and active connections. |
| Ping Monitor | Monitor multiple hosts and visualize latency and packet loss. |
| Window Manager | Arrange, resize and move windows between monitors. |
| Keyboard & Mouse Tester | Test keys, mouse buttons, scroll wheel and simultaneous key presses. |
| Screen Ruler | Measure screen distances, angles and areas in pixels. |
| Screenshot Annotator | Capture screenshots, crop, blur, draw arrows and add text. |
| Font Inspector | Preview installed fonts, compare typefaces and inspect font metadata. |
| Workspace Snapshots | Save and restore window arrangements and application launch configurations. |
| System Information | Display detailed hardware, operating system, storage and device information. |

## 5. Image, audio, video and document utilities

| Screen / utility | Description |
|---|---|
| Image Batch Editor | Resize, crop, rotate, compress, watermark and rename images in batches. |
| Color Studio | Screen color picker, palette generator, gradients, color conversions and contrast checker. |
| PDF Toolbox | Merge, split, extract, rotate, reorder, compress and convert PDF pages. |
| Audio Toolbox | Trim, normalize, change speed, inspect waveforms and convert audio. |
| Subtitle Toolbox | Edit SRT/VTT files, shift timestamps, merge and split subtitles. |
| Screen Recording Toolbox | Record screens, selected regions or windows; create GIFs and extract frames. |
| QR Toolbox | Generate and read QR codes, Wi-Fi QR codes and contact cards. |
| Barcode Generator | Generate common barcode formats such as EAN-13 and Code 128. |
| Document Scanner | Capture pages, correct perspective and combine images into PDFs. |
| Font-to-Image | Render text into PNG or SVG with custom fonts and backgrounds. |

## 6. Productivity utilities

| Screen / utility | Description |
|---|---|
| Scratchpad | Quick floating notes with autosave, pinned notes and global shortcut access. |
| Time Zone Planner | Compare multiple time zones and find overlapping working hours. |
| Unit-Aware Calculator | Perform calculations with units, e.g. distance divided by time. |
| Automation Studio | Create workflows using triggers, conditions and actions. |
| Command Cookbook | Select common computer tasks, configure options, preview and execute generated commands. |
| Quick Actions | Create reusable combinations of existing Srboli tools and operations. |
| Reminder Integration | Turn notes, tasks or automation events into reminders. |

---

## 7. Larger feature concepts

These combine several existing utilities.

### Automation Studio
A visual workflow builder. Example: trigger "a new file appears in Downloads",
condition "extension is PNG or JPG", actions "resize", "move to Pictures",
"create a backup", "show a notification". Other triggers: scheduled times,
folder changes, process events. (File Sorter's folder watcher is the seed.)

### Command Cookbook
A GUI for common terminal tasks: find files larger than 500 MB, not modified in
six months, empty directories; which process occupies a port; convert all PNGs in
a folder to WebP; extract images from PDFs; generate checksums; search files for
text. Show the generated command, explain its arguments, allow copy or run.

### File Intelligence Toolbox
One file inspection screen: signatures, MIME types, hashes, metadata, hex
preview, text preview, permissions, timestamps, type detection.

### Text Workbench
One screen: sort and reverse lines, remove duplicates, regex filtering, find and
replace, extract emails/URLs/IPs/numbers, compare two texts, format and transform.

### Workspace Manager
Save and restore desktop setups per project: window positions, applications, folders.

---

## 8. Improvements to existing tools

| Existing tool | Possible improvements |
|---|---|
| File Sorter | Dry-run mode, rule simulator and conflict detection. (Preview exists; the rest is open.) |
| Backup | Backup integrity verification, scheduling and storage estimates. |
| Folder Sync | Exclusions. (Two-way sync and conflict handling are done.) |
| Fast Transfer | Pause/resume, transfer speed graphs and bandwidth limits. |
| Metadata Inspector | Batch metadata editing and metadata comparison. |
| Gallery Sorter | Similar-image detection, contact sheets and bulk tagging. |
| Music Player | Audio metadata editor and album artwork manager. |
| Text Editor | Multi-cursor editing, snippets and advanced find/replace. |
| Function Plotter | SVG export, saved equations and reusable plot presets. |
| System Stats | Historical graphs and per-process resource usage. |
| Quick Switcher | Custom aliases, chained actions and command history. |
| File Converter | Batch presets and conversion queues. |

---

## 9. General guidelines

- Prioritize practical everyday utilities over gimmicks.
- Look for tasks that normally need a tiny script or a terminal command.
- Combine related small functions into one well-organized screen.
- Reuse existing components and infrastructure.
- Prefer local/offline processing.
- Avoid screens that do almost exactly what another one does.
- Preview / dry-run before destructive operations; undo or recovery where possible.
- Keep interfaces consistent with the existing Srboli design.
- Consider cross-platform limits (many system tools are desktop only).
- Estimate implementation complexity before recommending a feature.
