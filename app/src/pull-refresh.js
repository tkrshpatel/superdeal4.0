// Pull distance is measured in CSS pixels against the current visible viewport.
export function mountPullRefresh({refresh, onPullStart = () => false, onCancel = () => {}, win = window, doc = document}) {
  const indicator = doc.createElement('div');
  indicator.className = 'pull-refresh';
  indicator.hidden = true;
  indicator.setAttribute('role','status');
  indicator.setAttribute('aria-live','polite');
  indicator.innerHTML = '<svg class="pull-refresh-arrow" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3v17M5 13l7 7 7-7"/></svg><span class="pull-refresh-spinner" aria-hidden="true"></span><span class="pull-refresh-label">Pull down to refresh</span>';
  doc.body.appendChild(indicator);
  const label = indicator.querySelector('.pull-refresh-label');
  let gesture = null, generation = 0, dismiss;
  const top = () => (win.scrollY || doc.scrollingElement?.scrollTop || 0) <= 0;
  const blocked = () => doc.body.classList.contains('modal-open') || doc.body.classList.contains('alert-modal-open') || !!doc.querySelector('#store-picker[open]');
  function snapBack() {
    doc.documentElement.classList.remove('pulling-feed');
    doc.documentElement.style.setProperty('--pull-distance','0px');
  }
  function cancel() {
    const previous = gesture;
    gesture = null;
    snapBack();
    if (previous?.active) {
      indicator.hidden = true;
      onCancel(previous.interrupted);
    }
  }
  function onStart(event) {
    if (gesture) cancel();
    if (event.touches.length !== 1 || !top() || blocked() ||
      event.target.closest('input,textarea,select,button,a,summary,[role="dialog"],[contenteditable="true"]')) return;
    gesture = {x:event.touches[0].clientX,y:event.touches[0].clientY,active:false,
      threshold:Math.max(1,(win.visualViewport?.height || win.innerHeight || doc.documentElement.clientHeight)/4)};
  }
  async function sync(token) {
    let initialReady = false;
    snapBack();
    indicator.hidden = false;
    indicator.style.top = '';
    indicator.style.opacity = '1';
    indicator.dataset.loading = 'true';
    label.textContent = 'Syncing deals…';
    try {
      const success = await refresh({onInitialBatch: () => {
        if (token !== generation) return;
        initialReady = true;
        indicator.dataset.loading = 'false';
        indicator.hidden = true;
      }});
      if (token !== generation) return;
      if (initialReady) return;
      label.textContent = success === false ? 'Couldn’t sync. Pull down to retry.' : 'Deals updated';
    } catch {
      if (token !== generation) return;
      if (initialReady) return;
      label.textContent = 'Couldn’t sync. Pull down to retry.';
    } finally {
      if (token === generation && !initialReady) {
        indicator.dataset.loading = 'false';
        indicator.dataset.finished = 'true';
        dismiss = win.setTimeout(()=>{indicator.hidden=true;},1800);
      }
    }
  }
  function onMove(event) {
    if (!gesture) return;
    if (event.touches.length !== 1 || !top() || blocked()) {cancel();return;}
    const dx = event.touches[0].clientX-gesture.x;
    const dy = event.touches[0].clientY-gesture.y;
    if (dy <= 0 || Math.abs(dx) > Math.max(12,dy)) {cancel();return;}
    if (dy < 12) return;
    if (event.cancelable) event.preventDefault();
    if (!gesture.active) {
      gesture.active = true;
      generation++;
      win.clearTimeout(dismiss);
      gesture.interrupted = onPullStart();
    }
    const distance = Math.min(dy,gesture.threshold);
    doc.documentElement.classList.add('pulling-feed');
    doc.documentElement.style.setProperty('--pull-distance',distance+'px');
    indicator.hidden = false;
    indicator.dataset.loading = 'false';
    indicator.dataset.finished = 'false';
    indicator.style.opacity = String(Math.min(1,distance/80));
    indicator.style.top = 'calc(var(--app-safe-top,0px) + '+Math.max(8,distance/2-24)+'px)';
    label.textContent = 'Pull down to refresh';
    if (dy >= gesture.threshold) {
      const token = generation;
      gesture = null;
      void sync(token); // Start at quarter-screen, without waiting for finger release.
    }
  }
  doc.addEventListener('touchstart',onStart,{passive:true});
  doc.addEventListener('touchmove',onMove,{passive:false});
  doc.addEventListener('touchend',cancel,{passive:true});
  doc.addEventListener('touchcancel',cancel,{passive:true});
  return () => {
    generation++;
    win.clearTimeout(dismiss);
    snapBack();
    doc.removeEventListener('touchstart',onStart);
    doc.removeEventListener('touchmove',onMove);
    doc.removeEventListener('touchend',cancel);
    doc.removeEventListener('touchcancel',cancel);
    indicator.remove();
  };
}
