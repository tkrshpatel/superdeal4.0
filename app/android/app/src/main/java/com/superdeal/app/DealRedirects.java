package com.superdeal.app;

import java.net.URI;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/** Resolve tracking redirects only; never fetch a retailer product page. */
public final class DealRedirects {
    public interface Transport { Reply get(URI uri) throws Exception; }
    public static final class Reply {
        public final int status; public final String location;
        public Reply(int status,String location) {this.status=status;this.location=location;}
    }
    public static final class Result {
        public final String appUrl, fallbackUrl;
        Result(String appUrl,String fallbackUrl) {this.appUrl=appUrl;this.fallbackUrl=fallbackUrl;}
    }
    private static final Set<String> TRACKERS=new HashSet<>(Arrays.asList(
        "amzn-to.co","amzn.to","amzn.in","amzn.eu","amzn.asia","fkrt.cc","fkrt.co","flkt.cc",
        "myntr.in","ekaro.in","earnkaro.com","bit.ly","bitli.in"));
    private static final String[] RETAILERS={"amazon.in","amazon.com","flipkart.com","myntra.com","ajio.com",
        "nykaa.com","meesho.com","jiomart.com","croma.com","tatacliq.com","reliancedigital.in","snapdeal.com"};
    static boolean hostIs(String host,String domain) {
        return host!=null && (host.equalsIgnoreCase(domain)||host.toLowerCase(java.util.Locale.ROOT).endsWith("."+domain));
    }
    public static boolean publicHttps(URI uri) {
        String host=uri.getHost();
        return "https".equalsIgnoreCase(uri.getScheme()) && host!=null && uri.getRawUserInfo()==null
            && (uri.getPort()==-1||uri.getPort()==443) && !host.equalsIgnoreCase("localhost")
            && !host.endsWith(".local") && !host.matches("[0-9.]+") && !host.contains(":");
    }
    public static boolean trackedStart(URI uri) {
        return publicHttps(uri) && "thesuperdeals.in".equalsIgnoreCase(uri.getHost())
            && uri.getPath()!=null && uri.getPath().matches("/go/[A-Za-z0-9_-]{1,64}")
            && uri.getRawQuery()==null && uri.getRawFragment()==null;
    }
    static boolean retailer(URI uri) {
        for(String domain:RETAILERS) if(hostIs(uri.getHost(),domain)) return true;
        return false;
    }
    public static String retailerPackage(URI uri) {
        String host=uri.getHost();
        if(hostIs(host,"amazon.in")||hostIs(host,"amazon.com")) return "com.amazon.mShop.android.shopping";
        if(hostIs(host,"flipkart.com")) return "com.flipkart.android";
        if(hostIs(host,"myntra.com")) return "com.myntra.android";
        if(hostIs(host,"ajio.com")) return "com.ril.ajio";
        if(hostIs(host,"nykaa.com")) return "com.fsn.nykaa";
        if(hostIs(host,"meesho.com")) return "com.meesho.supply";
        return null;
    }
    public static Result resolve(String start,Transport transport) {
        URI current=URI.create(start);
        if(!trackedStart(current)) throw new IllegalArgumentException("Invalid deal redirect");
        String fallback=start;
        Set<URI> seen=new HashSet<>();
        long deadline=System.nanoTime()+8_000_000_000L;
        for(int hop=0;hop<8 && System.nanoTime()<deadline;hop++) {
            if(!seen.add(current)||!publicHttps(current)) break;
            if(retailer(current)) return new Result(current.toString(),fallback);
            if(hop>0 && !TRACKERS.contains(current.getHost().toLowerCase(java.util.Locale.ROOT))) return new Result(current.toString(),fallback);
            try {
                Reply reply=transport.get(current);
                if(!Arrays.asList(301,302,303,307,308).contains(reply.status)||reply.location==null) break;
                URI next=current.resolve(reply.location);
                if(!publicHttps(next)) break;
                if(hop==0) fallback=next.toString(); // Keep the exact original converted affiliate URL.
                current=next;
            } catch(Exception ignored) {break;}
        }
        return new Result(null,fallback);
    }
}
