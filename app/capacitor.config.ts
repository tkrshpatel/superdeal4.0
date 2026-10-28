import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.superdeal.app',
  appName: 'SuperDeals',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    cleartext: false,
  },
  android: {
    backgroundColor: '#f7f7f5',
    allowMixedContent: false,
  },
  plugins: {
    SystemBars: {
      insetsHandling: 'css',
      initialViewportFitValueHint: 'cover',
      style: 'LIGHT',
      hidden: false,
    },
    SplashScreen: {
      launchAutoHide: true,
      launchFadeOutDuration: 0,
      backgroundColor: '#f7f7f5',
      showSpinner: false,
    },
  },
};

export default config;
