# core/drawing_core.py - the picture behind the Drawing screen. Pure Python (Pillow only
# to save). Points are pixels from the TOP-LEFT of the picture.
#
# The picture is a list of strokes; undo/redo move strokes between two lists, so
# "Clear" is just another stroke (a marker) and can be undone too.
TOOLS = ("brush", "eraser", "line", "rect", "oval")
BACKGROUNDS = {"White": (255, 255, 255), "Cream": (250, 244, 225),
               "Grey": (60, 63, 70), "Black": (0, 0, 0)}
PALETTE = ["#000000", "#FFFFFF", "#E53935", "#FB8C00", "#FDD835", "#43A047",
           "#00ACC1", "#1E88E5", "#8E24AA", "#8D6E63"]
MIN_WIDTH, MAX_WIDTH = 1, 80


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Drawing:
    def __init__(self, size=(800, 600), bg=(255, 255, 255)):
        self.size = size
        self.bg = bg
        self.strokes = []       # {"tool", "color" (rgb or None), "width", "filled", "points"}
        self.redo_list = []
        self.live = None

    # ----- drawing -----
    def begin(self, tool, color, width, filled, point):
        if tool not in TOOLS:
            raise ValueError("unknown tool")
        self.live = {"tool": tool,
                     "color": None if tool == "eraser" else tuple(color),
                     "width": max(MIN_WIDTH, min(MAX_WIDTH, int(width))),
                     "filled": bool(filled) and tool in ("rect", "oval"),
                     "points": [tuple(point)]}
        return self.live

    def move(self, point):
        s = self.live
        if s is None:
            return
        point = tuple(point)
        if s["tool"] in ("brush", "eraser"):
            if point != s["points"][-1]:
                s["points"].append(point)
        else:                                   # shapes: start point + current end
            s["points"] = [s["points"][0], point]

    def end(self):
        s, self.live = self.live, None
        if s is None:
            return None
        self.strokes.append(s)
        self.redo_list = []
        return s

    def clear(self):
        self.strokes.append({"tool": "clear"})
        self.redo_list = []

    def undo(self):
        if self.strokes:
            self.redo_list.append(self.strokes.pop())
            return True
        return False

    def redo(self):
        if self.redo_list:
            self.strokes.append(self.redo_list.pop())
            return True
        return False

    def visible(self):
        """The strokes after the last Clear."""
        last = 0
        for i, s in enumerate(self.strokes):
            if s["tool"] == "clear":
                last = i + 1
        return self.strokes[last:]

    def is_empty(self):
        return not self.visible()

    def set_background(self, bg):
        self.bg = tuple(bg)

    # ----- saving -----
    def render(self):
        """The picture as a Pillow image."""
        from PIL import Image, ImageDraw
        w, h = self.size
        img = Image.new("RGB", (int(w), int(h)), self.bg)
        d = ImageDraw.Draw(img)
        for s in self.visible():
            draw_stroke(d, s, self.bg)
        return img

    def save(self, path):
        import os
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.render().save(path)
        return path


def draw_stroke(d, s, bg):
    col = tuple(bg) if s["color"] is None else tuple(s["color"])
    w = s["width"]
    pts = s["points"]
    r = w / 2
    t = s["tool"]
    if t in ("brush", "eraser", "line"):
        if len(pts) > 1:
            d.line(pts, fill=col, width=w, joint="curve")
        for x, y in (pts[0], pts[-1]):          # round caps (and the dot of a tap)
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)
    elif len(pts) > 1:
        (x0, y0), (x1, y1) = pts
        box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        fill = col if s["filled"] else None
        if t == "rect":
            d.rectangle(box, outline=col, fill=fill, width=w)
        else:
            d.ellipse(box, outline=col, fill=fill, width=w)


# ---- zoom / pan (the view onto the picture; the picture itself never changes) ---------
MIN_ZOOM, MAX_ZOOM, ZOOM_STEP = 1.0, 8.0, 1.5


def clamp_zoom(z):
    return max(MIN_ZOOM, min(MAX_ZOOM, float(z)))


def clamp_pan(pan, size, zoom):
    """Keep the zoomed picture covering the panel. `pan` is the picture's top-left
    offset in panel pixels (y measured down): between size*(1-zoom) and 0."""
    return tuple(min(0.0, max(s * (1 - zoom), p)) for p, s in zip(pan, size))


def zoom_about(pan, size, zoom, new_zoom, centre=None):
    """New (pan, zoom) after zooming so the point `centre` (panel pixels, y down;
    default the middle) stays under the finger."""
    new_zoom = clamp_zoom(new_zoom)
    cx, cy = centre if centre is not None else (size[0] / 2, size[1] / 2)
    k = new_zoom / zoom
    pan = (cx - (cx - pan[0]) * k, cy - (cy - pan[1]) * k)
    return clamp_pan(pan, size, new_zoom), new_zoom
