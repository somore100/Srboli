package org.somore100.srboli;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;
import android.os.PowerManager;

/**
 * Plays the sound the mini player was opened with, so it keeps playing when
 * the popup is dismissed or the user switches apps. Lives in the app process;
 * MiniPlayerActivity talks to it through the static fields below.
 */
public class PlayerService extends Service {
    public static final String ACTION_PLAY = "org.somore100.srboli.PLAY";
    public static final String ACTION_STOP = "org.somore100.srboli.STOP";
    public static final String PREFS = "srboli_player";

    public static MediaPlayer player;
    public static Uri current;
    public static String title = "";
    public static boolean looping = false;
    public static float volume = 0.8f;

    private static final String CHANNEL = "srboli_player";
    private static final int NOTIFICATION_ID = 4711;

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            release();
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        if (intent != null && ACTION_PLAY.equals(intent.getAction())
                && intent.getData() != null) {
            String t = intent.getStringExtra("title");
            title = (t == null) ? "" : t;
            SharedPreferences sp = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            volume = sp.getFloat("volume", 0.8f);
            goForeground();
            play(intent.getData());
        } else if (player == null) {
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    private void goForeground() {
        NotificationManager nm =
                (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            if (nm.getNotificationChannel(CHANNEL) == null) {
                nm.createNotificationChannel(new NotificationChannel(
                        CHANNEL, "Srboli player", NotificationManager.IMPORTANCE_LOW));
            }
            b = new Notification.Builder(this, CHANNEL);
        } else {
            b = new Notification.Builder(this);
        }
        Intent open = new Intent(this, MiniPlayerActivity.class);
        open.setAction("org.somore100.srboli.SHOW");
        open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        int piFlags = Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0;
        PendingIntent show = PendingIntent.getActivity(this, 0, open, piFlags);
        Intent stop = new Intent(this, PlayerService.class);
        stop.setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 1, stop, piFlags);
        b.setContentTitle(title.length() > 0 ? title : "Srboli player")
                .setContentText("Tap to open the player")
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentIntent(show)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(
                        android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopPi).build());
        Notification n = b.build();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, n,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        } else {
            startForeground(NOTIFICATION_ID, n);
        }
    }

    private void play(Uri uri) {
        release();
        MediaPlayer mp = new MediaPlayer();
        try {
            mp.setAudioAttributes(new AudioAttributes.Builder()
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                    .setUsage(AudioAttributes.USAGE_MEDIA).build());
            mp.setWakeMode(this, PowerManager.PARTIAL_WAKE_LOCK);
            if ("file".equals(uri.getScheme())) {
                mp.setDataSource(uri.getPath());
            } else {
                ParcelFileDescriptor pfd = getContentResolver().openFileDescriptor(uri, "r");
                mp.setDataSource(pfd.getFileDescriptor());
                pfd.close();
            }
            mp.setLooping(looping);
            mp.setVolume(volume, volume);
            mp.prepare();
            mp.start();
            player = mp;
            current = uri;
        } catch (Exception e) {
            try {
                mp.release();
            } catch (Exception ignored) {
            }
            player = null;
            current = null;
            stopForeground(true);
            stopSelf();
        }
    }

    public static void release() {
        if (player != null) {
            try {
                player.stop();
            } catch (Exception ignored) {
            }
            try {
                player.release();
            } catch (Exception ignored) {
            }
            player = null;
            current = null;
        }
    }

    @Override
    public void onDestroy() {
        release();
        super.onDestroy();
    }
}
