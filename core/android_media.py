# core/android_media.py
# Android-only helpers for video thumbnails / info / opening files in the
# phone's own apps. OpenCV and ffpyplayer don't exist in this APK, but Android
# itself can decode video frames (MediaMetadataRetriever) and play videos
# (any installed player, via an ACTION_VIEW intent).
#
# Every function returns None / False on any failure instead of raising, so
# callers can fall back gracefully. Safe to import anywhere: jnius is only
# imported inside the functions.
import mimetypes


def _retriever(path):
    from jnius import autoclass
    MMR = autoclass("android.media.MediaMetadataRetriever")
    r = MMR()
    r.setDataSource(path)
    return r, MMR


def video_meta(path):
    """(duration_seconds, width, height) or None."""
    try:
        r, MMR = _retriever(path)
        try:
            dur = int(r.extractMetadata(MMR.METADATA_KEY_DURATION) or 0) / 1000.0
            w = int(r.extractMetadata(MMR.METADATA_KEY_VIDEO_WIDTH) or 0)
            h = int(r.extractMetadata(MMR.METADATA_KEY_VIDEO_HEIGHT) or 0)
            rot = int(r.extractMetadata(MMR.METADATA_KEY_VIDEO_ROTATION) or 0)
        finally:
            r.release()
        if rot in (90, 270):
            w, h = h, w
        return dur, w, h
    except Exception as e:
        print(f"video_meta failed: {e}")
        return None


def video_frame_jpeg(path, out_path, pct=0.05, quality=80):
    """Save the frame at `pct` (0..1) of the video to out_path as JPEG."""
    try:
        from jnius import autoclass
        r, MMR = _retriever(path)
        try:
            dur_ms = int(r.extractMetadata(MMR.METADATA_KEY_DURATION) or 0)
            bmp = r.getFrameAtTime(int(dur_ms * 1000 * max(0.0, min(pct, 1.0))),
                                   MMR.OPTION_CLOSEST_SYNC)
            if bmp is None:
                return False
            fos = autoclass("java.io.FileOutputStream")(out_path)
            fmt = autoclass("android.graphics.Bitmap$CompressFormat").JPEG
            bmp.compress(fmt, quality, fos)
            fos.flush()
            fos.close()
            bmp.recycle()
            return True
        finally:
            r.release()
    except Exception as e:
        print(f"video_frame_jpeg failed: {e}")
        return False


def view_file(path, mime=None):
    """Open a file in whatever app the phone offers (video player, etc.)."""
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        File = autoclass("java.io.File")
        StrictMode = autoclass("android.os.StrictMode")
        VmPolicy = autoclass("android.os.StrictMode$VmPolicy$Builder")
        # Android refuses file:// URIs handed to other apps unless this
        # check is relaxed (public API; avoids needing a FileProvider).
        StrictMode.setVmPolicy(VmPolicy().build())
        mime = mime or mimetypes.guess_type(path)[0] or "*/*"
        intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(Uri.fromFile(File(path)), mime)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                        | Intent.FLAG_GRANT_READ_URI_PERMISSION)
        autoclass("org.kivy.android.PythonActivity").mActivity.startActivity(intent)
        return True
    except Exception as e:
        print(f"view_file failed: {e}")
        return False
