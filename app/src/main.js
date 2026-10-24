import { priceFacts, displayRetailer } from './deal-facts.js';
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
  ['drops', 'With savings', 'newest'],
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
      <p>Discover offers from your favourite stores. Compare the details, save your finds and shop directly with the retailer.</p>
    </div>
    <div class="hero-stats">
      <div><strong id="fresh-count">—</strong><span>fresh deals</span></div>
      <div><strong id="hot-count">—</strong><span>hot right now</span></div>
    </div>
  </section>

  <section class="search-wrap">
    <span>⌕</span><input id="search" aria-label="Search deals, brands or stores" type="search" placeholder="Search deals, brands or stores…" autocomplete="off">
    <button id="clear" class="clear hidden" aria-label="Clear search">×</button>
  </section>

  <section class="filter-panel" aria-label="Browse and filter offers">
    <div class="filter-panel-heading"><span>Find your next deal</span><button id="reset-filters" type="button">Reset filters</button></div>
    <div class="filters" aria-label="Quick deal filters">
      ${FILTERS.map(([id,label], i) => `<button class="filter ${i===0?'active':''}" aria-pressed="${i===0}" data-filter="${id}">${label}</button>`).join('')}
      <button class="filter" data-filter="saved" aria-pressed="false">♡ Saved</button>
    </div>
    <div class="browse-controls">
      <label>Store <select id="merchant-filter"><option value="">All stores</option></select></label>
      <label>Category <select id="category-filter"><option value="">All categories</option></select></label>
      <label>Sort by <select id="sort" aria-label="Sort deals">
        <option value="newest">Newest</option><option value="popular">Most clicked</option>
        <option value="price_asc">Lowest price</option><option value="price_desc">Highest price</option>
      </select></label>
      <span id="result-count" role="status"></span>
    </div>
  </section>
  <section class="section-head">
    <div><div class="eyebrow" id="section-kicker">JUST IN</div><h2 id="section-title">Latest deals</h2></div>

  </section>

  <section id="deals" class="deal-grid" aria-live="polite"></section>
</main>
<footer><span>SuperDeal · Discover. Save. Shop.</span></footer>
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

const money = v => v == null ? 'View price at website' : `₹${Number(v).toLocaleString('en-IN')}`;
const displayMerchant = displayRetailer;
const displayTitle = d => String(d.product_name || d.page_title || 'View offer details').trim();
const hasImage = d => !!d.image_url && !/placeholder/i.test(d.image_url) && /^https?:\/\//i.test(d.image_url);
const offerType = d => d.offer_type || (priceFacts(d).current !== null ? 'Product deal' : 'Offer');
function priceMarkup(d) {
  const p = priceFacts(d);
  return `<div class="price-row"><strong class="${p.current === null ? 'unknown-price' : ''}">${money(p.current)}</strong>${p.mrp !== null ? `<s>${money(p.mrp)}</s><span class="saving">Save ${money(p.saving)}</span>` : ''}</div>`;
}
const shareIcon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4"/></svg>';
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
  const title = displayTitle(d), merchant = displayMerchant(d), p = priceFacts(d);
  const saved = state.saved.has(String(d.id));
  return `<article class="deal-card ${hasImage(d)?'':'without-image'}" data-open="${esc(d.id)}">
    <div class="image-wrap ${hasImage(d)?'':'image-fallback'}">
      <img src="${esc(hasImage(d) ? d.image_url : '/brand/superdeals-logo.png')}" alt="${esc(hasImage(d) ? title : 'SuperDeals — product image unavailable')}" loading="lazy" ${hasImage(d) ? '' : 'data-brand-fallback="true"'}>
      <div class="card-top">${p.discount ? `<span class="discount-badge">${p.discount}% off</span>` : ''}</div>
      <button class="save ${saved?'saved':''}" data-save="${esc(d.id)}" aria-pressed="${saved}" aria-label="${saved?'Remove from saved':'Save deal'}">${saved?'♥':'♡'}</button>
    </div>
    <div class="card-content"><div class="card-meta"><div class="merchant">${esc(merchant)}</div>${d.last_seen_at && Number.isFinite(Date.parse(d.last_seen_at)) ? `<span class="posted-badge" title="Posted ${esc(d.last_seen_at)}">Posted ${esc(age(d.last_seen_at))}</span>` : ''}</div>
      <h3><button class="title-button" data-open="${esc(d.id)}">${esc(title)}</button></h3>
      <div class="card-middle">
      ${priceMarkup(d)}
      <div class="offer-conditions">${d.has_coupon?'<span>Coupon required</span>':''}${d.has_card_offer?'<span>Bank offer · check eligibility</span>':''}</div>
      <div class="demand-row"><span>${Number(d.click_count)>=5?`${Number(d.click_count)} clicks`:''}</span></div>
      </div>
      <div class="card-actions"><button class="get-deal" data-go="${esc(d.id)}">${merchant==='SuperDeals Find'?'Get deal':`Shop ${esc(merchant)}`} ↗</button><button class="share" data-share="${esc(d.id)}" aria-label="Share ${esc(title)}">${shareIcon}</button></div>
    </div></article>`;
}

function render(list) {
  freshCount.textContent = state.deals.length;
  document.querySelector('#result-count').textContent = `${list.length} offers in this feed`;
  hotCount.textContent = state.deals.filter(d => Number(d.click_count||0) >= 5).length;
  if (!list.length) {
    dealsEl.innerHTML = '<div class="empty"><div>✦</div><strong>No fresh deals match this.</strong><p>Try another search or filter.</p></div>';
    return;
  }
  dealsEl.innerHTML = list.map(card).join('');
  applyImageFallbacks(dealsEl);
}

function applyImageFallbacks(container) {
  container.querySelectorAll('img').forEach(img => img.addEventListener('error', () => {
    img.parentElement.classList.add('image-fallback');
    if (img.dataset.brandFallback === 'true') {
      // Fail once to plain brand text if the local logo itself cannot load.
      img.replaceWith(Object.assign(document.createElement('span'), {className:'fallback-brand-text', textContent:'SuperDeals'}));
      return;
    }
    img.dataset.brandFallback='true';
    img.alt='SuperDeals — product image unavailable';
    img.src='/brand/superdeals-logo.png';
  }));
}

function localFilter(list) {
  const q = state.query.toLowerCase();
  let result = list.filter(d => !q || `${displayTitle(d)} ${displayMerchant(d)} ${d.product_name} ${d.raw_text||''}`.toLowerCase().includes(q));
  const merchant = document.querySelector('#merchant-filter').value;
  const category = document.querySelector('#category-filter').value;
  result = result.filter(d => (!merchant || displayMerchant(d) === merchant) && (!category || d.category === category));
  if (state.active === 'drops') result = result.filter(d => priceFacts(d).saving > 0);
  if (state.active === 'under499') result = result.filter(d => priceFacts(d).current !== null && priceFacts(d).current < 500);
  if (state.active === 'discount') result = result.filter(d => priceFacts(d).discount >= 50);
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
    for (const [id, values, label] of [
      ['merchant-filter', [...new Set(state.deals.map(displayMerchant))].sort(), 'All stores'],
      ['category-filter', [...new Set(state.deals.map(d=>d.category).filter(Boolean))].sort(), 'All categories']
    ]) {
      const el = document.getElementById(id), previous = el.value;
      el.innerHTML = `<option value="">${label}</option>` + values.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
      if (values.includes(previous)) el.value = previous;
      if (id === 'category-filter') el.closest('label').hidden = values.length === 0;
    }
    render(localFilter(state.deals));
  } catch {
    dealsEl.innerHTML = '<div class="empty"><div>⚡</div><strong>We are warming up.</strong><p>We couldn’t load offers. Check your connection and try again.</p><button class="filter" data-retry>Try again</button></div>';
    freshCount.textContent = '—'; hotCount.textContent = '—';
  } finally {
    state.loading = false;
  }
}

function setFilter(id) {
  state.active = id;
  document.querySelectorAll('[data-filter]').forEach(b => {b.classList.toggle('active', b.dataset.filter === id);b.setAttribute('aria-pressed', String(b.dataset.filter === id));});
  const titles = {
    latest:['JUST IN','Latest deals'],
    hot:['HIGH DEMAND','Hot right now'],
    drops:['COMPARE & SAVE','Offers with savings'],
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
  try { localStorage.setItem('superdeal-saved', JSON.stringify([...state.saved])); } catch { /* Saving still works in this session. */ }
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
    <div class="detail-sheet" role="dialog" aria-modal="true" aria-labelledby="detail-title" tabindex="-1">
      <button class="detail-close" aria-label="Close deal details" data-close>×</button>
      <div class="detail-image ${hasImage(d)?'':'image-fallback'}"><img src="${esc(hasImage(d)?d.image_url:'/brand/superdeals-logo.png')}" alt="${esc(hasImage(d)?title:'SuperDeals — product image unavailable')}" ${hasImage(d)?'':'data-brand-fallback="true"'}></div>
      <div class="eyebrow">${esc(merchant)} · ${esc(offerType(d))}</div>
      <h2 id="detail-title">${esc(title)}</h2>
      ${priceMarkup(d)}
      <div class="insights">${d.has_coupon?'<span>Coupon required at checkout</span>':''}${d.has_card_offer?'<span>Bank offer: confirm eligibility at retailer</span>':''}</div>
      ${d.description?`<p class="offer-description">${esc(d.description)}</p>`:''}
      <div class="detail-meta">${d.last_seen_at?`<span>Posted ${esc(age(d.last_seen_at))}</span>`:''}${d.last_verified_at?`<span>Price checked ${esc(age(d.last_verified_at))}</span>`:''}</div>
      <p class="detail-note">Confirm the final price, variant, delivery charges and offer conditions at the retailer. Prices and availability may change.</p>
      <a class="detail-cta" data-detail-go="${esc(d.id)}" href="${esc(API('/go/' + d.id))}" target="_blank" rel="noopener">Shop ${esc(merchant)} ↗</a>
    </div>`;
  applyImageFallbacks(detail);
  detail.classList.remove('hidden');
  detail.previousFocus = document.activeElement;
  detail.querySelector('[data-close]').focus();
  document.body.classList.add('modal-open');
}

function closeDetail() {
  detail.classList.add('hidden');
  document.body.classList.remove('modal-open');
  detail.previousFocus?.focus();
}

searchEl.addEventListener('input', () => {
  state.query = searchEl.value.trim();
  clearEl.classList.toggle('hidden', !state.query);
  render(localFilter(state.deals));
});
clearEl.addEventListener('click', () => { searchEl.value=''; state.query=''; clearEl.classList.add('hidden'); render(localFilter(state.deals)); searchEl.focus(); });
document.querySelector('#reset-filters').addEventListener('click', () => {
  searchEl.value=''; state.query=''; clearEl.classList.add('hidden');
  document.querySelector('#merchant-filter').value='';
  document.querySelector('#category-filter').value='';
  setFilter('latest');
  load('newest');
});
document.querySelectorAll('.browse-controls select:not(#sort)').forEach(el=>el.addEventListener('change',()=>render(localFilter(state.deals))));
sortEl.addEventListener('change', () => load(sortEl.value));
document.querySelectorAll('.filter').forEach(b => b.addEventListener('click', () => setFilter(b.dataset.filter)));

dealsEl.addEventListener('click', e => {
  if (e.target.closest('[data-retry]')) { load(); return; }
  const saveBtn = e.target.closest('[data-save]');
  if (saveBtn) { e.stopPropagation(); save(saveBtn.dataset.save); return; }
  const share = e.target.closest('[data-share]');
  if (share) {
    e.stopPropagation();
    const d = state.deals.find(x => String(x.id) === String(share.dataset.share));
    if (navigator.share) { const title = displayTitle(d); navigator.share({title, text:`${title} — ${money(d.current_price)}`, url:new URL(API('/go/'+d.id), location.origin).href}).catch(()=>{}); }
    else navigator.clipboard?.writeText(new URL(API('/go/'+d.id), location.origin).href).then(()=>{toast.textContent='Deal link copied'; toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1500);}).catch(()=>{});
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
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail();
  if (e.key === 'Tab' && !detail.classList.contains('hidden')) {
    const nodes = [...detail.querySelectorAll('button, a[href]')];
    const first=nodes[0], last=nodes.at(-1);
    if (e.shiftKey && document.activeElement===first) {e.preventDefault();last.focus();}
    else if (!e.shiftKey && document.activeElement===last) {e.preventDefault();first.focus();}
  } });
document.querySelector('.brand-mark').addEventListener('click', e => { e.preventDefault(); setFilter('latest'); });

if (!IS_NATIVE && 'serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
if (IS_NATIVE) SplashScreen.hide().catch(()=>{});
load();
