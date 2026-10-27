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
}
