package com.superdeal.app;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.net.HttpURLConnection;
import java.net.URI;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@CapacitorPlugin(name="DealOpener")
public class DealOpenerPlugin extends Plugin {
    private volatile boolean destroyed=false;
    private final ExecutorService io=Executors.newSingleThreadExecutor();

    @PluginMethod
    public void open(PluginCall call) {
        String url=call.getString("url","");
        try {
            if(!DealRedirects.trackedStart(URI.create(url))) throw new IllegalArgumentException();
        } catch(Exception error) {call.reject("Invalid deal link");return;}
        io.execute(()->{
            DealRedirects.Result result=DealRedirects.resolve(url,uri->{
                HttpURLConnection connection=(HttpURLConnection)uri.toURL().openConnection();
                try {
                    connection.setInstanceFollowRedirects(false);
                    connection.setConnectTimeout(1500);
                    connection.setReadTimeout(2000);
                    connection.setRequestMethod("GET");
                    connection.setRequestProperty("User-Agent","SuperDeals-Android/1");
                    return new DealRedirects.Reply(connection.getResponseCode(),connection.getHeaderField("Location"));
                } finally {connection.disconnect();}
            });
            if(destroyed) {call.reject("App is closed");return;}
            getActivity().runOnUiThread(()->{
                if(destroyed) {call.reject("App is closed");return;}
                boolean opened=false;
                if(result.appUrl!=null) {
                    URI target=URI.create(result.appUrl);
                    for(String retailerPackage:DealRedirects.retailerPackages(target)) {
                        try {
                            Intent intent=new Intent(Intent.ACTION_VIEW,Uri.parse(result.appUrl));
                            intent.addCategory(Intent.CATEGORY_BROWSABLE);
                            intent.setPackage(retailerPackage);
                            getActivity().startActivity(intent);opened=true;break;
                        } catch(ActivityNotFoundException|SecurityException ignored) {}
                    }
                    if(!opened && Build.VERSION.SDK_INT>=Build.VERSION_CODES.R) {
                        try {
                            Intent intent=new Intent(Intent.ACTION_VIEW,Uri.parse(result.appUrl));
                            intent.addCategory(Intent.CATEGORY_BROWSABLE);
                            intent.addFlags(Intent.FLAG_ACTIVITY_REQUIRE_NON_BROWSER);
                            getActivity().startActivity(intent);opened=true;
                        } catch(ActivityNotFoundException|SecurityException ignored) {}
                    }
                }
                JSObject response=new JSObject();
                response.put("opened",opened);
                response.put("fallbackUrl",result.fallbackUrl);
                call.resolve(response);
            });
        });
    }

    @Override
    protected void handleOnDestroy() {
        destroyed=true;
        io.shutdownNow();
        super.handleOnDestroy();
    }
}
