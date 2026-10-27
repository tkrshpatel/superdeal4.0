# SuperDeals Android release

Status: release preparation; not submitted to Google Play. Review eligibility,
phone testing, signing and Play Console declarations remain owner steps.

## First test build

The existing Android workflow builds a debug APK and an **unsigned** release AAB.
Download `superdeal-debug-apk` from GitHub Actions for installation on a test phone.
An unsigned AAB is a build validation artifact, not ready to upload to Play.
The app bundles the UI, connects only to `https://thesuperdeals.in`, and ignores
old `superdeal-api-base` LAN settings. The website continues using its same-origin
API. No API listener, MongoDB URI, database or alert origin configuration changes
are required. Android native HTTP carries API requests over HTTPS with the public
origin header, without opening browser CORS or allowing cleartext connections.

Local Windows debug build (Node 22+, JDK 21, Android SDK 36):

```powershell
cd C:\Users\Home\superdeal-staging\app
npm.cmd ci
npm.cmd test
npm.cmd run build
npx.cmd cap sync android
cd android
.\gradlew.bat assembleDebug
```

APK: `app\android\app\build\outputs\apk\debug\app-debug.apk`.
Existing app ID is `com.superdeal.app`; confirm ownership/availability in your Play
Console before first publication. Display name is SuperDeals. Target API is 36.

## Phone checks

- Fresh install on mobile data: no LAN/PC setup overlay; live deals load.
- Search, store filters, pagination and saved products work.
- Shop links open the intended retailer through the existing native browser flow.
- Back navigation, dialogs, keyboard, rotation, small screens and large text are usable.
- Get notified saves a consented request; with delivery disabled no email is sent.
- Offline/reconnect and server failures show retry instead of an empty success.
- Privacy opens locally in the app. Contact email launches the user's mail app.
- Confirm launcher icon, Android system splash, cold start and returning from retailer.
- Test Android 16 behavior and run Play Console's pre-launch report.

## Signed release bundle on your PC

Keep your upload key outside the repository. Generate it once using Android Studio
(Build > Generate Signed App Bundle or APK > Android App Bundle > Create new).
Store its passwords in a password manager and back up the keystore privately.
Enroll in Play App Signing when uploading the first release. Never reuse the debug
key, send a keystore/password in chat or commit it to Git.

The Gradle project optionally reads these process environment values:

- `SUPERDEAL_UPLOAD_STORE_FILE`: absolute path to your upload keystore.
- `SUPERDEAL_UPLOAD_STORE_PASSWORD`: keystore password.
- `SUPERDEAL_UPLOAD_KEY_ALIAS`: upload key alias.
- `SUPERDEAL_UPLOAD_KEY_PASSWORD`: key password.
- `SUPERDEAL_ANDROID_VERSION_CODE`: positive increasing integer, default 1.
- `SUPERDEAL_ANDROID_VERSION_NAME`: user-visible version, default 1.0.0.

Set passwords using PowerShell `Read-Host -AsSecureString`, converting them only
into the current process environment, then remove those environment variables when
finished. Alternatively let Android Studio manage the signing dialog locally.
With all four signing values provided, `gradlew.bat bundleRelease` signs the bundle.
With none, it builds an unsigned bundle; partial signing values fail the build.
Each update submitted to Play must increase versionCode.

AAB: `app\android\app\build\outputs\bundle\release\app-release.aab`.
Check the signed bundle using `jarsigner -verify -verbose -certs` before upload.

## Play Console preparation

1. Create/verify the owner's developer account; choose personal or organization accurately.
2. Create SuperDeals with the confirmed package name, support contact and intended audience.
3. Publish the privacy page by rebuilding/restarting the website through the existing deployment.
   Verify `https://thesuperdeals.in/privacy.html` returns the policy rather than the SPA.
4. Complete Data safety from actual behavior: notification email/product preferences,
   click events and technical network logs; review Cloudflare and Gmail processing.
   Do not claim that no user data is collected. No account is required to browse.
   Deletion/STOP requests are handled manually through the published support email.
5. Complete app access, content rating, ads and other applicable declarations accurately.
6. Provide real screenshots, app icon and feature graphic; no mock claims about push
   notifications, price history, email verification or matching accuracy.
7. Upload signed AAB to internal testing first, inspect reports and test on phones.
8. Complete any required closed testing before applying for production access.

Policy references (checked 27 October 2026):

- https://support.google.com/googleplay/android-developer/answer/9899034
  Affiliate traffic as the primary purpose is prohibited. Ownership of our website
  alone does not resolve that separate restriction. Evaluate the actual shopping
  utility and obtain policy clarification if needed; cosmetic/native wrapping does
  not guarantee acceptance. Do not submit misleading descriptions to hide purpose.
- https://support.google.com/googleplay/android-developer/answer/11926878
  New phone apps currently require target API 36 or higher.
- https://support.google.com/googleplay/android-developer/answer/14151465
  New personal accounts may require at least 12 testers continuously opted in for
  14 days before applying for production access. Follow the account's Console requirements.
- https://support.google.com/googleplay/android-developer/answer/10144311
  Review privacy and user-data requirements against the real app and providers.
- https://developer.android.com/studio/publish/app-signing
  Upload key and Play App Signing guidance.

The PC, MongoDB, API, Caddy and Cloudflare Tunnel remain the production backend.
A Play Store listing does not host those services: if the PC sleeps or crashes,
the installed app cannot fetch live deals or save notification requests.
