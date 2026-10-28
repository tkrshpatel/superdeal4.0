import { Capacitor, CapacitorHttp } from '@capacitor/core';
import { createApiFetch, resolveApiBase } from './native-api.js';

const native = Capacitor.isNativePlatform();
// Release apps always connect to the public HTTPS service. Old local PC settings
// are intentionally ignored so existing testers can upgrade without a reset.
export const API_BASE = resolveApiBase(native, globalThis.__SUPERDEAL_API__);
export const apiFetch = createApiFetch({native, request: options => CapacitorHttp.request(options)});
