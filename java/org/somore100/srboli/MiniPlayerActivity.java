package org.somore100.srboli;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

/**
 * The small player that pops up over whatever app the user was in when they
 * chose "Open with Srboli" on a sound. It is a translucent activity: the
 * other app stays visible behind it, and Srboli's main window is not started.
 * Tap outside the panel (or Back) to minimise: the sound keeps playing in
 * PlayerService. "Open in Srboli" hands the file to the full app.
 */
public class MiniPlayerActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView titleView, timeView, volView;
    private SeekBar seek, vol;
    private Button playBtn, loopBtn;
    private boolean seeking = false;
    private Uri uri;
    private String mime;

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            update();
            handler.postDelayed(this, 250);
        }
    };

    private int dp(int v) {
        return (int) (v * getResources().getDisplayMetrics().density + 0.5f);
    }

    private static String fmt(int ms) {
        int s = Math.max(0, ms) / 1000;
        return String.format("%02d:%02d", s / 60, s % 60);
    }

    private String displayName(Uri u) {
        try {
            Cursor c = getContentResolver().query(u, null, null, null, null);
            if (c != null) {
                try {
                    int i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                    if (i >= 0 && c.moveToFirst()) {
                        return c.getString(i);
                    }
                } finally {
                    c.close();
                }
            }
        } catch (Exception ignored) {
        }
        String last = u.getLastPathSegment();
        return last == null ? "Sound" : last;
    }

    private Button button(String text, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xFF2E3140);
        bg.setCornerRadius(dp(10));
        b.setBackground(bg);
        b.setOnClickListener(l);
        return b;
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        buildUi();
        handle(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handle(intent);
    }

    /** A new sound: ask the service to play it. A re-open (notification) just shows the panel. */
    private void handle(Intent in) {
        Uri u = in.getData();
        if (u != null) {
            uri = u;
            mime = in.getType();
            if (PlayerService.player == null || !u.equals(PlayerService.current)) {
                String name = displayName(u);
                titleView.setText(name);
                Intent svc = new Intent(this, PlayerService.class);
                svc.setAction(PlayerService.ACTION_PLAY);
                svc.setData(u);
                svc.putExtra("title", name);
                if (Build.VERSION.SDK_INT >= 26) {
                    startForegroundService(svc);
                } else {
                    startService(svc);
                }
            }
        } else {
            titleView.setText(PlayerService.title);
        }
        SharedPreferences sp = getSharedPreferences(PlayerService.PREFS, Context.MODE_PRIVATE);
        int v = Math.round(sp.getFloat("volume", 0.8f) * 100);
        vol.setProgress(v);
        volView.setText(v + "%");
        loopBtn.setText(PlayerService.looping ? "Loop: on" : "Loop: off");
    }

    private void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                finish();                      // tap outside = minimise
            }
        });

        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(18), dp(16), dp(18), dp(16));
        panel.setClickable(true);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xFF1E2128);
        bg.setCornerRadius(dp(24));
        panel.setBackground(bg);

        titleView = new TextView(this);
        titleView.setTextColor(Color.WHITE);
        titleView.setTextSize(16);
        titleView.setSingleLine(true);
        titleView.setEllipsize(android.text.TextUtils.TruncateAt.END);
        panel.addView(titleView);

        timeView = new TextView(this);
        timeView.setTextColor(0xFFA0A6B4);
        timeView.setTextSize(13);
        timeView.setText("Preparing...");
        panel.addView(timeView);

        seek = new SeekBar(this);
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar s, int p, boolean fromUser) {
            }

            @Override
            public void onStartTrackingTouch(SeekBar s) {
                seeking = true;
            }

            @Override
            public void onStopTrackingTouch(SeekBar s) {
                MediaPlayer p = PlayerService.player;
                if (p != null) {
                    p.seekTo(s.getProgress());
                }
                seeking = false;
            }
        });
        panel.addView(seek);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        playBtn = button("Pause", new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                MediaPlayer p = PlayerService.player;
                if (p != null) {
                    if (p.isPlaying()) {
                        p.pause();
                    } else {
                        p.start();
                    }
                }
                update();
            }
        });
        loopBtn = button("Loop: off", new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                PlayerService.looping = !PlayerService.looping;
                MediaPlayer p = PlayerService.player;
                if (p != null) {
                    p.setLooping(PlayerService.looping);
                }
                loopBtn.setText(PlayerService.looping ? "Loop: on" : "Loop: off");
            }
        });
        LinearLayout.LayoutParams half = new LinearLayout.LayoutParams(0, dp(48), 1f);
        half.setMargins(dp(3), dp(6), dp(3), dp(6));
        row.addView(playBtn, half);
        row.addView(loopBtn, half);
        panel.addView(row);

        LinearLayout vrow = new LinearLayout(this);
        vrow.setOrientation(LinearLayout.HORIZONTAL);
        vrow.setGravity(Gravity.CENTER_VERTICAL);
        TextView vl = new TextView(this);
        vl.setText("Volume");
        vl.setTextColor(0xFFA0A6B4);
        vl.setTextSize(12);
        vrow.addView(vl);
        vol = new SeekBar(this);
        vol.setMax(100);
        vol.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar s, int p, boolean fromUser) {
                float v = p / 100f;
                PlayerService.volume = v;
                volView.setText(p + "%");
                MediaPlayer mp = PlayerService.player;
                if (mp != null) {
                    mp.setVolume(v, v);
                }
                if (fromUser) {
                    getSharedPreferences(PlayerService.PREFS, Context.MODE_PRIVATE)
                            .edit().putFloat("volume", v).apply();
                }
            }

            @Override
            public void onStartTrackingTouch(SeekBar s) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar s) {
            }
        });
        vrow.addView(vol, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        volView = new TextView(this);
        volView.setTextColor(Color.WHITE);
        volView.setTextSize(12);
        vrow.addView(volView);
        panel.addView(vrow);

        LinearLayout row2 = new LinearLayout(this);
        row2.setOrientation(LinearLayout.HORIZONTAL);
        Button close = button("Stop and close", new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Intent stop = new Intent(MiniPlayerActivity.this, PlayerService.class);
                stop.setAction(PlayerService.ACTION_STOP);
                startService(stop);
                finish();
            }
        });
        Button open = button("Open in Srboli", new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                openInSrboli();
            }
        });
        GradientDrawable accent = new GradientDrawable();
        accent.setColor(0xFF4C9EF2);
        accent.setCornerRadius(dp(10));
        open.setBackground(accent);
        row2.addView(close, half);
        row2.addView(open, half);
        panel.addView(row2);

        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM);
        lp.setMargins(dp(10), dp(10), dp(10), dp(14));
        root.addView(panel, lp);
        setContentView(root);
    }

    /** Hand the sound to the full app (its own chooser), and stop playing here. */
    private void openInSrboli() {
        if (uri != null) {
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setClassName(getPackageName(), "org.kivy.android.PythonActivity");
            i.setDataAndType(uri, mime == null ? "audio/*" : mime);
            i.putExtra("srboli_from_overlay", true);
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        }
        Intent stop = new Intent(this, PlayerService.class);
        stop.setAction(PlayerService.ACTION_STOP);
        startService(stop);
        finish();
    }

    private void update() {
        MediaPlayer p = PlayerService.player;
        if (p == null) {
            return;
        }
        try {
            int dur = p.getDuration();
            seek.setMax(dur);
            if (!seeking) {
                seek.setProgress(p.getCurrentPosition());
            }
            timeView.setText(fmt(p.getCurrentPosition()) + " / " + fmt(dur));
            playBtn.setText(p.isPlaying() ? "Pause" : "Play");
        } catch (Exception ignored) {
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        handler.post(tick);
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(tick);
        super.onPause();
    }
}
