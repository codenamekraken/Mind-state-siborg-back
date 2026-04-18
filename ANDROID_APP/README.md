# Mind-state-siborg Android APK

This folder contains a lightweight Android wrapper app for your Mind-state-siborg web experience.

## What it does
- Opens the deployed HTTPS frontend in a Chrome Custom Tab
- Keeps the web app’s camera, microphone, and BLE flow available through Chrome
- Gives you a real installable APK for hackathon demos
- Lets users copy the frontend and backend URLs quickly

## Why this approach
Your project already has:
- a deployed frontend on Netlify
- a deployed backend on Render
- Web Bluetooth, camera, and microphone logic in the browser

A browser-based Android wrapper is the fastest stable way to package this into an APK while keeping the full web experience intact.

## URLs used
- Frontend: `https://mind-state-siborg.netlify.app/index.html`
- Backend: `https://mind-state-siborg-back.onrender.com`

## How to build the APK
1. Open `ANDROID_APP` in Android Studio.
2. Let Gradle sync complete.
3. Use an Android phone or emulator with Chrome installed.
4. Run the app.
5. To create a release APK:
   - Build > Generate Signed Bundle / APK
   - Choose APK
   - Create or select a keystore
   - Finish the wizard

## Notes
- The app uses Chrome Custom Tabs, not a plain WebView, so browser features are more likely to work.
- For Web Bluetooth, use Chrome on Android.
- If you later want a stricter trusted-web-activity APK, we can upgrade this wrapper and add asset links + signing flow.

## Files included
- `settings.gradle.kts`
- `build.gradle.kts`
- `app/build.gradle.kts`
- `app/src/main/AndroidManifest.xml`
- `app/src/main/java/com/mindstate/siborg/MainActivity.kt`
- resources for theme, colors, layout, and launcher icon
