import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.superdeal.app',
  appName: 'SuperDeal',
  webDir: 'dist',
  bundledWebRuntime: false,
  android: {
    backgroundColor: '#f7f7f5',
    cleartext: true,
  },
  plugins: {
    SplashScreen: {
      launchAutoHide: true,
      launchFadeOutDuration: 0,
      backgroundColor: '#f7f7f5',
      showSpinner: false,
    },
  },
};

export default config;
