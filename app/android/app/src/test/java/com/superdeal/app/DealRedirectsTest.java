package com.superdeal.app;
import static org.junit.Assert.*;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;

public class DealRedirectsTest {
    private static final String START="https://thesuperdeals.in/go/abc123";
    @Test public void preservesTrackingAndDoesNotFetchRetailerPage() {
        List<String> calls=new ArrayList<>();
        String affiliate="https://amzn-to.co/track?ref=original%2Bvalue";
        String destination="https://www.amazon.in/dp/B012345678?tag=owner-21&variant=blue%2Bgreen";
        DealRedirects.Result result=DealRedirects.resolve(START,uri->{
            calls.add(uri.toString());
            return new DealRedirects.Reply(302,calls.size()==1?affiliate:destination);
        });
        assertEquals(destination,result.appUrl);assertEquals(affiliate,result.fallbackUrl);
        assertEquals(2,calls.size());
        assertEquals("in.amazon.mShop.android.shopping",DealRedirects.retailerPackage(URI.create(destination)));
    }
    @Test public void unknownRetailerUsesAndroidHandlerWithoutFetchingItsPage() {
        int[] calls={0};
        DealRedirects.Result result=DealRedirects.resolve(START,uri->{calls[0]++;return new DealRedirects.Reply(302,"https://shop.example/product?affiliate=kept");});
        assertEquals(1,calls[0]);assertEquals("https://shop.example/product?affiliate=kept",result.appUrl);
    }
    @Test public void unsafeRedirectsCannotLaunchAnAppOrReachPrivateAddresses() {
        for(String target:new String[]{"http://amazon.in/dp/x","https://127.0.0.1/x","https://user:secret@amazon.in/x","intent://malicious","https://localhost/x"}) {
            int[] calls={0};
            DealRedirects.Result result=DealRedirects.resolve(START,uri->{calls[0]++;return new DealRedirects.Reply(302,target);});
            assertNull(result.appUrl);assertEquals(START,result.fallbackUrl);assertEquals(1,calls[0]);
        }
    }
    @Test public void rateLimitAndNetworkFailureFallBackToOriginalAffiliateLink() {
        String affiliate="https://fkrt.cc/track";
        DealRedirects.Result result=DealRedirects.resolve(START,uri->uri.toString().equals(START)?new DealRedirects.Reply(302,affiliate):new DealRedirects.Reply(429,null));
        assertNull(result.appUrl);assertEquals(affiliate,result.fallbackUrl);
    }
    @Test public void spoofedDomainsNeverSelectRetailerPackages() {
        assertNull(DealRedirects.retailerPackage(URI.create("https://amazon.in.evil.example/x")));
        assertEquals("com.flipkart.android",DealRedirects.retailerPackage(URI.create("https://www.flipkart.com/product?affid=keep")));
    }
    @Test public void supportsIndiaAndGlobalAmazonApps() {
        assertArrayEquals(new String[]{"in.amazon.mShop.android.shopping","com.amazon.mShop.android.shopping"},
            DealRedirects.retailerPackages(URI.create("https://amazon.in/dp/x")));
    }
    @Test public void sourceMustBeOurTrackedRedirect() {
        try {DealRedirects.resolve("https://evil.example/go/abc",uri->{fail("Must not connect");return null;});fail("Must reject");}
        catch(IllegalArgumentException expected) {}
    }
}
