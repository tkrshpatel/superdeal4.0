// Native feed pull-to-refresh. A gesture must start at the top, outside a dialog/control.
export function mountPullRefresh({refresh, busy = () => false, win = window, doc = document}) {
  const indicator = doc.createElement('div');
  indicator.className = 'pull-refresh';
  indicator.hidden = true;
  indicator.setAttribute('role', 'status');
  indicator.setAttribute('aria-live', 'polite');
  indicator.innerHTML = '<span class="pull-refresh-spinner" aria-hidden="true"></span><span class="pull-refresh-label">Pull to refresh</span>';
  doc.body.appendChild(indicator);
  const label = indicator.querySelector('.pull-refresh-label');
  let start = null, distance = 0, refreshing = false, dismiss;
  const top = () => (win.scrollY || doc.scrollingElement?.scrollTop || 0) <= 0;
  const blocked = () => busy() || refreshing || doc.body.classList.contains('modal-open') || doc.body.classList.contains('alert-modal-open') || !!doc.querySelector('#store-picker[open]');
  function reset() {start = null; distance = 0; if (!refreshing) indicator.hidden = true;}
  function onStart(event) {
    reset();
    if (event.touches.length !== 1 || !top() || blocked() ||
        event.target.closest('input,textarea,select,button,a,summary,[role="dialog"],[contenteditable="true"]')) return;
    win.clearTimeout(dismiss);
    start = {x:event.touches[0].clientX,y:event.touches[0].clientY};
    distance = 0;
  }
  function onMove(event) {
    if (!start) return;
    if (event.touches.length !== 1 || !top() || blocked()) {reset();return;}
    const dx = event.touches[0].clientX-start.x;
    const dy = event.touches[0].clientY-start.y;
    if (dy <= 0 || Math.abs(dx) > Math.max(12,dy)) {reset();return;}
    if (dy < 12) return;
    if (event.cancelable) event.preventDefault();
    distance = Math.min(dy,140);
    indicator.hidden = false;
    indicator.dataset.ready = String(distance >= 72);
    indicator.dataset.loading = 'false';
    label.textContent = distance >= 72 ? 'Release to refresh' : 'Pull to refresh';
  }
  async function onEnd() {
    if (!start) return;
    const ready = distance >= 72 && !blocked() && top();
    start = null;distance = 0;
    if (!ready) {indicator.hidden = true;return;}
    refreshing = true;
    indicator.hidden = false;
    indicator.dataset.loading = 'true';
    label.textContent = 'Refreshing…';
    try {
      const success = await refresh();
      label.textContent = success === false ? 'Couldn’t refresh. Pull to retry.' : 'Deals updated';
    } catch {
      label.textContent = 'Couldn’t refresh. Pull to retry.';
    } finally {
      refreshing = false;
      indicator.dataset.loading = 'false';
      dismiss = win.setTimeout(() => {indicator.hidden = true;},1800);
    }
  }
  doc.addEventListener('touchstart',onStart,{passive:true});
  doc.addEventListener('touchmove',onMove,{passive:false});
  doc.addEventListener('touchend',onEnd,{passive:true});
  doc.addEventListener('touchcancel',reset,{passive:true});
  return () => {
    win.clearTimeout(dismiss);
    doc.removeEventListener('touchstart',onStart);
    doc.removeEventListener('touchmove',onMove);
    doc.removeEventListener('touchend',onEnd);
    doc.removeEventListener('touchcancel',reset);
    indicator.remove();
  };
}
