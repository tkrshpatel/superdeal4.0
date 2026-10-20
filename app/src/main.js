import './style.css';
import { Capacitor } from '@capacitor/core';
import { SplashScreen } from '@capacitor/splash-screen';
import { Browser } from '@capacitor/browser';

const IS_NATIVE = Capacitor.isNativePlatform();
document.documentElement.classList.toggle('native-app', IS_NATIVE);
const API_BASE = (globalThis.__SUPERDEAL_API__ || '').replace(/\/$/, '');
const API = (path) => `${API_BASE}${path}`;

function openDeal(id) {
  const url = API('/go/' + encodeURIComponent(String(id)));
  if (IS_NATIVE) {
    // Open outside the embedded WebView. The OS/browser handles supported app links.
    Browser.open({url}).catch(() => { window.location.href = url; });
  } else {
    window.open(url, '_blank', 'noopener');
  }
}


const FILTERS = [
  ['latest', 'Latest', 'newest'],
  ['hot', '🔥 Hot', 'popular'],
  ['drops', '↓ Price drops', 'newest'],
  ['under499', '₹ Under 499', 'newest'],
  ['discount', '50%+ off', 'newest'],
];
const state = {
  deals: [],
  active: 'latest',
  saved: new Set(),
  query: '',
  loading: false,
};
try {
  const saved = JSON.parse(localStorage.getItem('superdeal-saved') || '[]');
  if (Array.isArray(saved)) state.saved = new Set(saved.map(String));
} catch {}

const app = document.querySelector('#app');
app.innerHTML = `
<header class="topbar">
  <a class="brand-mark" href="#" aria-label="SuperDeal home">
    <span class="logo">SD</span>
    <span><b>SuperDeal</b><small>Deals worth your click.</small></span>
  </a>
  <div class="live-pill"><i></i> LIVE DEALS</div>
</header>
<main>
  <section class="hero">
    <div class="hero-copy">
      <div class="eyebrow">FRESH FOR YOU</div>
      <h1>Good deals.<br><span>Less scrolling.</span></h1>
      <p>Fresh finds from the last 24 hours, ranked by what's getting attention right now.</p>
    </div>
    <div class="hero-stats">
      <div><strong id="fresh-count">—</strong><span>fresh deals</span></div>
      <div><strong id="hot-count">—</strong><span>hot right now</span></div>
    </div>
  </section>

  <section class="search-wrap">
    <span>⌕</span><input id="search" type="search" placeholder="Search deals, brands or stores…" autocomplete="off">
    <button id="clear" class="clear hidden" aria-label="Clear search">×</button>
  </section>

  <section class="filters" aria-label="Deal filters">
    ${FILTERS.map(([id,label], i) => `<button class="filter ${i===0?'active':''}" data-filter="${id}">${label}</button>`).join('')}
    <button class="filter" data-filter="saved">♡ Saved</button>
  </section>

  <section class="section-head">
    <div><div class="eyebrow" id="section-kicker">JUST IN</div><h2 id="section-title">Latest deals</h2></div>
    <select id="sort" aria-label="Sort deals">
      <option value="newest">Newest</option>
      <option value="popular">Most clicked</option>
      <option value="price_asc">Lowest price</option>
      <option value="price_desc">Highest price</option>
    </select>
  </section>

  <section id="deals" class="deal-grid" aria-live="polite"></section>
</main>
<footer><span>SuperDeal</span><span>Fresh window: 24 hours</span></footer>
<div id="toast" class="toast" role="status"></div>
<div id="detail" class="detail hidden"></div>
`;

const dealsEl = document.querySelector('#deals');
const searchEl = document.querySelector('#search');
const clearEl = document.querySelector('#clear');
const sectionTitle = document.querySelector('#section-title');
const sectionKicker = document.querySelector('#section-kicker');
const sortEl = document.querySelector('#sort');
const toast = document.querySelector('#toast');
const detail = document.querySelector('#detail');
const freshCount = document.querySelector('#fresh-count');
const hotCount = document.querySelector('#hot-count');

const money = v => v == null ? 'Check price' : `₹${Number(v).toLocaleString('en-IN')}`;
const merchantFromUrl = value => {
  if (!value) return '';
  try {
    const host = new URL(value).hostname.toLowerCase().replace(/^www\./, '');
    if (host === 'amazon.in' || host.endsWith('.amazon.in')) return 'Amazon';
    if (host === 'flipkart.com' || host.endsWith('.flipkart.com')) return 'Flipkart';
    if (host === 'myntra.com' || host.endsWith('.myntra.com')) return 'Myntra';
    if (host === 'ajio.com' || host.endsWith('.ajio.com')) return 'AJIO';
  } catch {}
  return '';
};
const displayMerchant = d => d.enriched_merchant || d.merchant || merchantFromUrl(d.canonical_url) || 'SuperDeal find';
const displayTitle = d => {
  const title = String(d.page_title || '').trim();
  if (!title) return d.product_name;
  const merchant = displayMerchant(d);
  const suffixes = merchant === 'Amazon'
    ? [/\s*:\s*Amazon\.in(?::.*)?$/i]
    : merchant === 'Flipkart'
      ? [/\s*[-|:]\s*Buy .*? Online at Best Price in India.*$/i, /\s*[-|:]\s*Flipkart\.com.*$/i]
      : [];
  return suffixes.reduce((value, pattern) => value.replace(pattern, '').trim(), title) || d.product_name;
};
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const age = value => {
  const ms = Date.now() - Date.parse(value);
  if (!Number.isFinite(ms) || ms < 0) return 'Just now';
  const m = Math.floor(ms / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
};

function card(d) {
  const title = displayTitle(d);
  const merchant = displayMerchant(d);
  const saved = state.saved.has(String(d.id));
  const hot = Number(d.click_count || 0) >= 5;
  return `
  <article class="deal-card" data-open="${esc(d.id)}">
    <div class="image-wrap">
      <img src="${esc(d.image_url || '/superdeal-placeholder.svg')}" alt="${esc(title)}" loading="lazy">
      <div class="card-top">
        ${hot ? '<span class="hot-badge">🔥 HOT</span>' : ''}
        ${(d.page_discount_pct || d.discount_pct) ? `<span class="discount-badge">${esc(d.page_discount_pct || d.discount_pct)}% OFF</span>` : ''}
      </div>
      <button class="save ${saved?'saved':''}" data-save="${esc(d.id)}" aria-label="${saved?'Remove from saved':'Save deal'}">${saved?'♥':'♡'}</button>
    </div>
    <div class="card-content">
      <div class="merchant">${esc(merchant)}</div>
      <h3>${esc(title)}</h3>
      <div class="price-row"><strong>${money(d.current_price)}</strong>${d.verified_price ? '<span class="verified">✓ Verified</span>' : ''}</div>
      <div class="demand-row">
        <span class="${hot?'demand hot':'demand'}">⌁ ${Number(d.click_count||0).toLocaleString('en-IN')} ${Number(d.click_count||0)===1?'person':'people'} clicked</span>
        <span>${age(d.last_seen_at)}</span>
      </div>
      <div class="card-actions">
        <button class="get-deal" data-go="${esc(d.id)}">Get deal <span>↗</span></button>
        <button class="share" data-share="${esc(d.id)}" aria-label="Share">⌁</button>
      </div>
    </div>
  </article>`;
}

function render(list) {
  freshCount.textContent = state.deals.length;
  hotCount.textContent = state.deals.filter(d => Number(d.click_count||0) >= 5).length;
  if (!list.length) {
    dealsEl.innerHTML = '<div class="empty"><div>✦</div><strong>No fresh deals match this.</strong><p>Try another search or filter.</p></div>';
    return;
  }
  dealsEl.innerHTML = list.map(card).join('');
}

function localFilter(list) {
  const q = state.query.toLowerCase();
  let result = list.filter(d => !q || `${displayTitle(d)} ${displayMerchant(d)} ${d.product_name} ${d.raw_text||''}`.toLowerCase().includes(q));
  if (state.active === 'drops') result = result.filter(d => Number(d.discount_pct||0) > 0);
  if (state.active === 'under499') result = result.filter(d => d.current_price != null && Number(d.current_price) < 500);
  if (state.active === 'discount') result = result.filter(d => Number(d.discount_pct||0) >= 50);
  if (state.active === 'hot') result = result.filter(d => Number(d.click_count||0) >= 5);
  if (state.active === 'saved') result = result.filter(d => state.saved.has(String(d.id)));
  return result;
}

async function load(sort = sortEl.value) {
  state.loading = true;
  dealsEl.innerHTML = '<div class="skeleton-grid">' + Array.from({length:6}, () => '<div class="skeleton"></div>').join('') + '</div>';
  try {
    const params = new URLSearchParams({limit:'100', sort});
    const response = await fetch(API(`/deals?${params}`), {cache:'no-store'});
    if (!response.ok) throw new Error('API unavailable');
    state.deals = (await response.json()).deals || [];
    render(localFilter(state.deals));
  } catch {
    dealsEl.innerHTML = '<div class="empty"><div>⚡</div><strong>We are warming up.</strong><p>Start the SuperDeal API and refresh this page.</p></div>';
    freshCount.textContent = '—'; hotCount.textContent = '—';
  } finally {
    state.loading = false;
  }
}

function setFilter(id) {
  state.active = id;
  document.querySelectorAll('.filter').forEach(b => b.classList.toggle('active', b.dataset.filter === id));
  const titles = {
    latest:['JUST IN','Latest deals'],
    hot:['HIGH DEMAND','Hot right now'],
    drops:['PRICE MOVEMENT','Price drops'],
    under499:['BUDGET FINDS','Under ₹499'],
    discount:['BIG SAVINGS','50%+ off'],
    saved:['YOUR LIST','Saved deals'],
  };
  [sectionKicker.textContent, sectionTitle.textContent] = titles[id] || titles.latest;
  if (id === 'hot') sortEl.value = 'popular';
  else if (id !== 'saved') sortEl.value = 'newest';
  render(localFilter(state.deals));
  if (id === 'hot') load('popular');
}

function save(id) {
  const key = String(id);
  state.saved.has(key) ? state.saved.delete(key) : state.saved.add(key);
  localStorage.setItem('superdeal-saved', JSON.stringify([...state.saved]));
  render(localFilter(state.deals));
  toast.textContent = state.saved.has(key) ? 'Saved ♥' : 'Removed from saved';
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 1500);
}

function showDetail(id) {
  const d = state.deals.find(x => String(x.id) === String(id));
  if (!d) return;
  const title = displayTitle(d);
  const merchant = displayMerchant(d);
  detail.innerHTML = `
    <div class="detail-sheet">
      <button class="detail-close" data-close>×</button>
      <div class="detail-image"><img src="${esc(d.image_url || '/superdeal-placeholder.svg')}" alt="${esc(title)}"></div>
      <div class="eyebrow">${esc(merchant)}</div>
      <h2>${esc(title)}</h2>
      <div class="detail-price">${money(d.current_price)}</div>
      <div class="insights">
        ${Number(d.click_count||0) >= 5 ? '<span>🔥 High demand</span>' : ''}
        ${(d.page_discount_pct || d.discount_pct) ? `<span>${esc(d.page_discount_pct || d.discount_pct)}% off</span>` : ''}
        ${d.verified_price ? '<span>✓ Price verified</span>' : ''}
        <span>⌁ ${Number(d.click_count||0).toLocaleString('en-IN')} clicks</span>
      </div>
      <div class="detail-meta"><span>Fresh for 24h</span><span>Updated ${esc(age(d.last_seen_at))}</span></div>
      <p class="detail-note">Deals older than 24 hours are automatically removed from the live feed. Prices and availability can change at the merchant.</p>
      <a class="detail-cta" data-detail-go="${esc(d.id)}" href="${esc(API('/go/' + d.id))}" target="_blank" rel="noopener">Get this deal ↗</a>
    </div>`;
  detail.classList.remove('hidden');
  document.body.classList.add('modal-open');
}

function closeDetail() {
  detail.classList.add('hidden');
  document.body.classList.remove('modal-open');
}

searchEl.addEventListener('input', () => {
  state.query = searchEl.value.trim();
  clearEl.classList.toggle('hidden', !state.query);
  render(localFilter(state.deals));
});
clearEl.addEventListener('click', () => { searchEl.value=''; state.query=''; clearEl.classList.add('hidden'); render(localFilter(state.deals)); searchEl.focus(); });
sortEl.addEventListener('change', () => load(sortEl.value));
document.querySelectorAll('.filter').forEach(b => b.addEventListener('click', () => setFilter(b.dataset.filter)));

dealsEl.addEventListener('click', e => {
  const saveBtn = e.target.closest('[data-save]');
  if (saveBtn) { e.stopPropagation(); save(saveBtn.dataset.save); return; }
  const share = e.target.closest('[data-share]');
  if (share) {
    e.stopPropagation();
    const d = state.deals.find(x => String(x.id) === String(share.dataset.share));
    if (navigator.share) { const title = displayTitle(d); navigator.share({title, text:`${title} — ${money(d.current_price)}`, url:API('/go/'+d.id)}).catch(()=>{}); }
    else navigator.clipboard?.writeText(API('/go/'+d.id));
    return;
  }
  const go = e.target.closest('[data-go]');
  if (go) { e.stopPropagation(); openDeal(go.dataset.go); return; }
  const open = e.target.closest('[data-open]');
  if (open) showDetail(open.dataset.open);
});
detail.addEventListener('click', e => {
  const go = e.target.closest('[data-detail-go]');
  if (go && IS_NATIVE) { e.preventDefault(); openDeal(go.dataset.detailGo); return; }
  if (e.target.closest('[data-close]') || e.target === detail) closeDetail();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });
document.querySelector('.brand-mark').addEventListener('click', e => { e.preventDefault(); setFilter('latest'); });

if (!IS_NATIVE && 'serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
if (IS_NATIVE) SplashScreen.hide().catch(()=>{});
load();
