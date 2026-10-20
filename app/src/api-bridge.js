import { Capacitor } from '@capacitor/core';
import './api-bridge.css';

const native = Capacitor.isNativePlatform();
const stored = (localStorage.getItem('superdeal-api-base') || '').trim().replace(/\/$/, '');
if (stored) globalThis.__SUPERDEAL_API__ = stored;

function showSetup() {
  if (!native || document.querySelector('#api-setup-overlay')) return;
  const overlay = document.createElement('div');
  overlay.id = 'api-setup-overlay';
  overlay.innerHTML = `
    <div class="api-setup-card">
      <div class="api-setup-kicker">ONE-TIME SETUP</div>
      <h1>Connect your PC</h1>
      <p>Start the SuperDeal API on your PC, then enter its IPv4 address below. Your phone and PC must be on the same Wi-Fi.</p>
      <input id="api-setup-input" placeholder="http://192.168.1.10:8000" inputmode="url" autocomplete="off">
      <button id="api-setup-save">Connect</button>
      <div id="api-setup-status"></div>
    </div>`;
  document.body.appendChild(overlay);
  const input = overlay.querySelector('#api-setup-input');
  const button = overlay.querySelector('#api-setup-save');
  const status = overlay.querySelector('#api-setup-status');
  button.addEventListener('click', async () => {
    const value = input.value.trim().replace(/\/$/, '');
    if (!/^https?:\/\//i.test(value)) {
      status.textContent = 'Enter a full address, for example http://192.168.1.10:8000';
      return;
    }
    button.disabled = true;
    status.textContent = 'Checking PC…';
    try {
      const response = await fetch(`${value}/health`, { cache: 'no-store' });
      if (!response.ok) throw new Error('API unavailable');
      localStorage.setItem('superdeal-api-base', value);
      globalThis.__SUPERDEAL_API__ = value;
      location.reload();
    } catch {
      status.textContent = 'PC not reachable. Check the API, Wi-Fi and Windows Firewall.';
      button.disabled = false;
    }
  });
}

if (native && !stored) {
  window.addEventListener('DOMContentLoaded', () => setTimeout(showSetup, 100));
  setTimeout(showSetup, 500);
}
