# core/studio_export.py - Srboli Studio: slides (frames in order) and slide export helpers. No Kivy.
import os
import re


def slides(doc):
    """The presentation: every visible frame, in layer-list order (reorder them in Layers)."""
    return [o for o in doc.objects if o["type"] == "frame" and doc.effective_visible(o)]


def start_index(doc, selected_ids=()):
    """Which slide to open on: the selected frame (or the frame holding the selection), else 0."""
    sl = slides(doc)
    ids = [s["id"] for s in sl]
    for i in selected_ids:
        o = doc.get(i)
        while o is not None:
            if o["id"] in ids:
                return ids.index(o["id"])
            o = doc.get(o["parent"]) if o["parent"] is not None else None
    return 0


def slide_ids(doc, frame):
    """Ids of what a slide shows: the frame and everything inside it."""
    return {frame["id"]} | {d["id"] for d in doc.descendants(frame["id"])}


def slide_pixels(frame, max_side=4096, scale=1.0):
    """Output size of a slide: frame size times scale, long side capped."""
    w, h = frame["w"] * scale, frame["h"] * scale
    k = min(1.0, max_side / max(w, h, 1.0))
    return max(1, int(round(w * k))), max(1, int(round(h * k)))


def file_stem(text, fallback="slides"):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(text)).strip("._")[:60] or fallback


def images_to_pdf(png_paths, pdf_path):
    """Join PNG files into one PDF, one page each."""
    if not png_paths:
        raise ValueError("No slides to export.")
    from PIL import Image
    imgs = []
    try:
        for p in png_paths:
            im = Image.open(p)
            imgs.append(im.convert("RGB"))
            im.close()
        imgs[0].save(pdf_path, "PDF", save_all=True, append_images=imgs[1:])
    finally:
        for im in imgs:
            im.close()
    return pdf_path
