package com.getcapacitor.myapp;

import static org.junit.Assert.*;

import android.content.Context;
import android.content.pm.ActivityInfo;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.superdeal.app.MainActivity;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.json.JSONObject;
import org.json.JSONTokener;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class ExampleInstrumentedTest {
    @Test
    public void useAppContext() {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertEquals("com.superdeal.app", context.getPackageName());
    }

    private JSONObject geometry(ActivityScenario<MainActivity> scenario) throws Exception {
        CompletableFuture<JSONObject> result = new CompletableFuture<>();
        scenario.onActivity(activity -> {
            android.webkit.WebView web = activity.getBridge().getWebView();
            int[] location = new int[2];
            web.getLocationOnScreen(location);
            WindowInsetsCompat root = ViewCompat.getRootWindowInsets(web);
            if (root == null) { result.complete(new JSONObject()); return; }
            Insets bars = root.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
            boolean darkIcons = WindowCompat.getInsetsController(activity.getWindow(), activity.getWindow().getDecorView()).isAppearanceLightStatusBars();
            web.evaluateJavascript("(function(){const logo=document.querySelector('.header-logo');if(!logo)return '{}';return JSON.stringify({top:logo.getBoundingClientRect().top,width:innerWidth,height:innerHeight});})()", value -> {
                try {
                    Object decoded = new JSONTokener(value).nextValue();
                    JSONObject data = new JSONObject((String) decoded);
                    if (data.has("width")) {
                        double scale = web.getWidth() / data.getDouble("width");
                        data.put("screenTop", location[1] + data.getDouble("top") * scale);
                        data.put("statusBottom", bars.top);
                        data.put("darkIcons", darkIcons);
                    }
                    result.complete(data);
                } catch (Exception error) { result.completeExceptionally(error); }
            });
        });
        return result.get(5, TimeUnit.SECONDS);
    }

    private void checkLogo(ActivityScenario<MainActivity> scenario, boolean landscape) throws Exception {
        long deadline = System.currentTimeMillis() + 10000;
        JSONObject data = new JSONObject();
        while (System.currentTimeMillis() < deadline) {
            data = geometry(scenario);
            if (data.has("screenTop") && (data.getDouble("width") > data.getDouble("height")) == landscape
                    && data.getDouble("screenTop") >= data.getDouble("statusBottom") - 1 && data.getBoolean("darkIcons")) return;
            Thread.sleep(100);
        }
        fail("Logo must clear system bars with dark clock/battery icons: " + data);
    }

    @Test
    public void logoClearsSystemBarsInPortraitAndLandscape() throws Exception {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
            checkLogo(scenario, false);
            scenario.onActivity(activity -> activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE));
            checkLogo(scenario, true);
        }
    }

    private JSONObject evaluate(ActivityScenario<MainActivity> scenario, String expression) throws Exception {
        CompletableFuture<JSONObject> result = new CompletableFuture<>();
        scenario.onActivity(activity -> activity.getBridge().getWebView().evaluateJavascript(
            "JSON.stringify(" + expression + ")", value -> {
                try { result.complete(new JSONObject((String) new JSONTokener(value).nextValue())); }
                catch (Exception error) { result.completeExceptionally(error); }
            }));
        return result.get(5, TimeUnit.SECONDS);
    }

    private void pointer(long down, int action, float x, float y) {
        android.view.MotionEvent event = android.view.MotionEvent.obtain(down, android.os.SystemClock.uptimeMillis(), action, x, y, 0);
        event.setSource(android.view.InputDevice.SOURCE_TOUCHSCREEN);
        InstrumentationRegistry.getInstrumentation().sendPointerSync(event);
        event.recycle();
    }

    @Test
    public void realPullRevealsArrowAndRefreshesLandingAtHalfScreen() throws Exception {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT));
            checkLogo(scenario, false);
            JSONObject ready = evaluate(scenario, "(function(){const q=document.querySelector('#search');q.value='old query';q.dispatchEvent(new Event('input'));window.scrollTo(0,0);return {query:q.value};})()");
            assertEquals("old query", ready.getString("query"));
            final float[] bounds = new float[4];
            scenario.onActivity(activity -> {
                android.webkit.WebView web = activity.getBridge().getWebView();
                int[] location = new int[2];
                web.getLocationOnScreen(location);
                bounds[0] = location[0] + web.getWidth()/2f;
                bounds[1] = location[1] + 115f * activity.getResources().getDisplayMetrics().density;
                bounds[2] = web.getHeight();
                bounds[3] = activity.getResources().getDisplayMetrics().density;
            });
            long down = android.os.SystemClock.uptimeMillis();
            float x=bounds[0], y=bounds[1];
            pointer(down, android.view.MotionEvent.ACTION_DOWN, x, y);
            for (int step=1;step<=12;step++) {
                pointer(down, android.view.MotionEvent.ACTION_MOVE, x, y+bounds[2]*step/48f);
                Thread.sleep(16);
            }
            JSONObject pulled=evaluate(scenario, "(function(){const p=document.querySelector('.pull-refresh');return {distance:parseFloat(document.documentElement.style.getPropertyValue('--pull-distance'))||0,shown:!!p&&!p.hidden,label:p?p.textContent:''};})()");
            assertTrue("The feed must move with a real finger drag: "+pulled, pulled.getDouble("distance")>20);
            assertTrue(pulled.getBoolean("shown"));
            assertTrue(pulled.getString("label").contains("Pull down to refresh"));
            assertEquals("old query", evaluate(scenario, "({query:document.querySelector('#search').value})").getString("query"));
            for (int step=13;step<=27;step++) {
                pointer(down, android.view.MotionEvent.ACTION_MOVE, x, y+bounds[2]*step/48f);
                Thread.sleep(16);
            }
            // Verify sync starts at the threshold, while the finger is still down.
            JSONObject refreshed=evaluate(scenario, "({query:document.querySelector('#search').value,latest:document.querySelector('[data-filter=latest]').getAttribute('aria-pressed')})");
            pointer(down, android.view.MotionEvent.ACTION_UP, x, y+bounds[2]*27/48f);
            assertEquals("", refreshed.getString("query"));
            assertEquals("true", refreshed.getString("latest"));
        }
    }

}
