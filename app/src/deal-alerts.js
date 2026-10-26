// The public client never receives subscriber lists or private stored records.
export function mountDealAlerts({ api, product = () => '' }) {
  const overlay = document.createElement('div');
  overlay.className = 'alert-overlay';
  overlay.hidden = true;
  overlay.innerHTML = `
    <section class="alert-sheet" role="dialog" aria-modal="true" aria-labelledby="alert-title">
      <button type="button" class="alert-close" aria-label="Close notification form">×</button>
      <div class="eyebrow">YOUR NEXT FIND</div>
      <h2 id="alert-title">Get notified</h2>
      <p class="alert-intro">Tell us what you’re looking for. We’ll save your request and notification preferences.</p>
      <form id="deal-alert-form">
        <label>Product<input name="product" required minlength="3" maxlength="120" placeholder="e.g. Headphones or iPhone 17 Pro" autocomplete="off"></label>
        <label>Email address<input name="email" type="email" required maxlength="254" placeholder="you@example.com" autocomplete="email"></label>
        <div class="alert-preferences">
          <label>Emails per day<select name="daily_limit"><option value="1">Up to 1</option><option value="2">Up to 2</option><option value="3">Up to 3</option><option value="5">Up to 5</option></select></label>
          <label>Notify me for<select name="days"><option value="1">1 day</option><option value="3">3 days</option><option value="7" selected>7 days</option><option value="14">14 days</option><option value="30">30 days</option></select></label>
        </div>
        <p class="alert-hint">Choose your preferred daily email limit and how many days you want updates for.</p>
        <label class="alert-consent"><input name="consent" type="checkbox" required><span>I agree to SuperDeals storing my email and preferences for product deal notifications.</span></label>
        <button class="alert-submit" type="submit">Save my request</button>
      </form>
      <div class="alert-link-actions" hidden><button class="alert-submit" type="button" id="alert-link-action">Confirm</button></div>
      <p class="alert-status" role="status" aria-live="polite"></p>
    </section>`;
  document.body.append(overlay);
  const form = overlay.querySelector('form');
  const status = overlay.querySelector('.alert-status');
  const actions = overlay.querySelector('.alert-link-actions');
  let previousFocus, linkAction;
  function open(value = '') {
    previousFocus = document.activeElement;
    form.hidden = false;
    actions.hidden = true;
    status.textContent = '';
    overlay.querySelector('#alert-title').textContent = 'Get notified';
    overlay.querySelector('.eyebrow').hidden = false;
    overlay.querySelector('.alert-intro').hidden = false;
    overlay.querySelector('.alert-intro').textContent = 'Tell us what you’re looking for. We’ll save your request and notification preferences.';
    form.elements.product.value = value.slice(0, 120);
    overlay.hidden = false;
    document.body.classList.add('alert-modal-open');
    form.elements.product.focus();
  }
  function close() {
    overlay.hidden = true;
    document.body.classList.remove('alert-modal-open');
    previousFocus?.focus();
  }
  overlay.querySelector('.alert-close').addEventListener('click', close);
  overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
  overlay.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.stopPropagation(); close(); }
    if (event.key !== 'Tab') return;
    const nodes = [...overlay.querySelectorAll('button, input, select')].filter(node => !node.disabled && !node.closest('[hidden]'));
    const first = nodes[0], last = nodes.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  async function post(path, payload) {
    const response = await fetch(api(path), { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), cache: 'no-store' });
    let result;
    try { result = await response.json(); }
    catch { throw new Error('The alert API did not return JSON. Restart the API and frontend, then try again.'); }
    if (!response.ok) {
      const messages = {
        400: 'Check your details, or request a new confirmation link.',
        403: 'This website address is not allowed by the alert API. Check SUPERDEAL_ALERT_ORIGINS in .env.',
        404: 'The alert endpoint is unavailable. Restart the updated MongoDB API.',
        405: 'The running API does not support alerts. Restart the updated MongoDB API.',
        429: 'Too many requests. Please try again later.',
        503: 'We couldn’t save your request. Please try again shortly.',
      };
      throw new Error((messages[response.status] || 'Could not save this request. Please try again.') + ' (HTTP ' + response.status + ')');
    }
    return result;
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const button = form.querySelector('[type=submit]');
    button.disabled = true;
    status.textContent = 'Saving your request…';
    try {
      await post('/api/v1/alerts', {
        product: form.elements.product.value.trim(), email: form.elements.email.value.trim(),
        daily_limit: Number(form.elements.daily_limit.value), days: Number(form.elements.days.value), consent: form.elements.consent.checked,
      });
      form.hidden = true;
      overlay.querySelector('.eyebrow').hidden = true;
      overlay.querySelector('#alert-title').innerHTML = '<img class="alert-success-logo" src="/brand/superdeals-logo.png" alt="SuperDeals" width="2048" height="683">';
      overlay.querySelector('.alert-intro').textContent = 'Thank you!!';
      status.textContent = 'We have saved your response. We will notify you once the deals show up!';
      overlay.querySelector('.alert-close').focus();
    } catch (error) { status.textContent = error.message || 'Connection failed. Please try again.'; }
    finally { button.disabled = false; }
  });
  document.querySelector('#get-notified')?.addEventListener('click', () => open(product()));
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-notify-product]');
    if (trigger) open(trigger.dataset.notifyProduct);
  });
  // Fragments keep bearer tokens out of server access logs and HTTP referrers.
  const params = new URLSearchParams(location.hash.slice(1));
  const action = params.has('alert_confirm') ? 'confirm' : params.has('alert_stop') ? 'stop' : null;
  if (action) {
    const token = params.get(`alert_${action}`);
    history.replaceState(null, '', location.pathname + location.search);
    open();
    form.hidden = true;
    actions.hidden = false;
    overlay.querySelector('.alert-intro').hidden = true;
    overlay.querySelector('#alert-title').textContent = action === 'confirm' ? 'Confirm your deal alert' : 'Stop these deal alerts';
    const button = overlay.querySelector('#alert-link-action');
    button.textContent = action === 'confirm' ? 'Activate my alert' : 'Unsubscribe';
    linkAction = async () => {
      button.disabled = true;
      try {
        await post(`/api/v1/alerts/${action}`, {token});
        status.textContent = action === 'confirm' ? 'Your alert is active. We’ll email you only when a new matching deal is available.' : 'You’re unsubscribed from this product alert.';
        actions.hidden = true;
      } catch (error) { status.textContent = error.message; button.disabled = false; }
    };
    button.addEventListener('click', linkAction);
    button.focus();
  }
  return { open, close };
}
