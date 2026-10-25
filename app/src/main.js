import { fetchDealWindow } from './deal-feed.js';
import { mountDealAlerts } from './deal-alerts.js';
import { priceFacts, displayRetailer, isHotDeal } from './deal-facts.js';
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
  ['hot', '🔥 Hot', 'newest'],
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
  counts: null,
  visibleCount: 24,
  merchants: new Set(),
};
try {
  const saved = JSON.parse(localStorage.getItem('superdeal-saved') || '[]');
  if (Array.isArray(saved)) state.saved = new Set(saved.map(String));
} catch {}

const app = document.querySelector('#app');
app.innerHTML = `
<header class="topbar">
  <a class="brand-mark" href="#" aria-label="SuperDeals home">
    <span class="brand-identity"><img class="header-logo" src="/brand/superdeals-logo.png" alt="SuperDeals" width="2048" height="683"></span>
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
      <div><strong id="fresh-count" aria-label="Fresh deals in 30 minutes / deals in 24 hours">—/—</strong><span>Fresh / 24-hour deals</span></div>
      <div><strong id="hot-count">—</strong><span>hot right now</span></div>
    </div>
  </section>

  <div class="search-actions">
  <section class="search-wrap">
    <span>⌕</span><input id="search" aria-label="Search deals, brands or stores" type="search" placeholder="Search deals, brands or stores…" autocomplete="off">
    <button id="clear" class="clear hidden" aria-label="Clear search">×</button>
  </section>
  <aside class="deal-alert-feature" aria-label="Personal product deal alerts">
    <div class="alert-feature-copy"><strong>Don’t miss the right deal.</strong><span>Your product. A deal. An email.</span></div>
    <button id="get-notified" class="search-notify" type="button"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg><span>Get notified</span><span aria-hidden="true">↗</span></button>
  </aside>
  </div>

  <section class="filter-panel" aria-label="Browse and filter offers">
    <div class="filter-panel-heading"><span>Find your next deal</span><button id="reset-filters" type="button">Reset filters</button></div>
    <div class="filters" aria-label="Quick deal filters">
      ${FILTERS.map(([id,label], i) => `<button class="filter ${i===0?'active':''}" aria-pressed="${i===0}" data-filter="${id}">${label}</button>`).join('')}
      <button class="filter" data-filter="saved" aria-pressed="false">♡ Saved</button>
    </div>
    <div class="browse-controls">
      <label>Category <select id="category-filter"><option value="">All categories</option></select></label>

    </div>
  </section>
  <section class="section-head">
    <div class="deals-heading"><div class="eyebrow" id="section-kicker">JUST IN</div><h2 id="section-title">Latest deals</h2></div>
    <div class="store-control"><span id="store-label" class="control-label">Stores</span>
      <select id="merchant-filter" hidden aria-hidden="true" tabindex="-1"><option value="">All stores</option></select>
      <details id="store-picker" class="store-picker">
        <summary id="store-summary" aria-labelledby="store-label store-value"><span id="store-value">All</span><svg class="store-chevron" width="12" height="12" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></summary>
        <div class="store-popover" role="region" aria-label="Choose stores">
          <div class="store-popover-head"><strong>Choose stores</strong><button type="button" id="store-done">Done</button></div>
          <input id="store-search" type="search" aria-label="Search stores" placeholder="Search stores…" autocomplete="off">
          <div id="store-options" class="store-options"></div>
          <button id="clear-stores" type="button">Clear store filters</button>
        </div>
      </details>
    </div>
      <label class="sort-control">Sort by <select id="sort" aria-label="Sort deals">
        <option value="newest">Newest</option><option value="popular">Most clicked</option>
        <option value="price_asc">Lowest price</option><option value="price_desc">Highest price</option>
      </select></label>
  </section>

  <div id="selected-stores" class="selected-stores" role="group" aria-label="Selected stores" hidden></div>
  <section id="deals" class="deal-grid" aria-live="polite"></section>
  <div id="feed-pagination" class="feed-pagination" hidden><button id="load-more-deals" class="filter" type="button">Show more deals</button></div>
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
const displayTitle = d => shopperText(d.product_name) || shopperText(d.page_title) || 'SuperDeals Find';
const hasImage = d => !!d.image_url && !privateText.test(d.image_url) && !/placeholder/i.test(d.image_url) && /^https?:\/\//i.test(d.image_url);
const offerType = d => priceFacts(d).current !== null ? 'Product deal' : 'Offer';
function discountLabel(d) {
  const pct=priceFacts(d).discount;
  return pct===null?'':(d.offer_facts?.discount_kind==='up_to'?'Up to ':'')+pct+'% off';
}
function priceMarkup(d) {
  const p = priceFacts(d);
  const from=Number(d.offer_facts?.starting_price);
  const displayed=p.current===null && Number.isFinite(from) && from>0 ? 'From '+money(from) : money(p.current);
  return `<div class="price-row"><strong class="${p.current === null ? 'unknown-price' : ''}">${esc(displayed)}</strong>${p.mrp !== null ? `<s>${money(p.mrp)}</s><span class="saving">Save ${money(p.saving)}</span>` : (p.saving!==null?`<span class="saving">Save ${money(p.saving)}</span>`:'')+(p.discount!==null?`<span class="saving">${esc(discountLabel(d))}</span>`:'')}</div>`;
}
// Defence in depth for old APIs and cached records: never render source metadata.
const privateText = /earn\s*karo|telegram|(?:https?:\/\/)?(?:t\.me|telegram\.me)\/|@[A-Za-z0-9_]+|untrusted\s+merchant|merchant\s+page\s+research/i;
const shopperText = value => String(value ?? '').split('\n').filter(line=>!privateText.test(line)).join('\n').trim();
function supportedTerms(d) {
  const t=d.deal_terms;
  return t && typeof t==='object' ? t : null;
}
function termsMarkup(d) {
  const t=supportedTerms(d)||{};
  const lines=key=>Array.isArray(t[key])?t[key].filter(v=>typeof v==='string').map(shopperText).filter(Boolean):[];
  const codes=lines('coupon_codes');
  // Older published records may contain only a short explicit coupon excerpt.
  for (const line of lines('source_excerpts')) {
    const match=line.match(/^coupon\s*:\s*([A-Za-z0-9][A-Za-z0-9_-]{1,29})\s*$/i);
    if (match && !codes.includes(match[1]) && !/^\d+$/.test(match[1])) codes.push(match[1]);
  }
  const extra=Array.isArray(d.offer_facts?.conditional_offers)?d.offer_facts.conditional_offers.map(o=>shopperText(o?.label)).filter(Boolean):[];
  const advertised=d.offer_facts?.advertised_discount;
  if(advertised?.kind==='up_to' && d.offer_facts?.discount_kind==='calculated' && Number(advertised.value)>0 && Number(advertised.value)<=100)extra.push('Advertised offer: Up to '+Number(advertised.value)+'% off');
  const details=[...new Set([...lines('instructions'),...lines('conditions'),...extra])];
  if (!codes.length && !details.length) return '';
  return `<section class="deal-terms" aria-label="Deal details"><h3>Below are details:</h3>
    ${codes.map(code=>`<div class="coupon-code"><code>${esc(code)}</code><button type="button" data-copy-code="${esc(code)}">Copy code</button></div>`).join('')}
    ${details.length?`<ul>${details.map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`:''}</section>`;
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
  const conditional = Array.isArray(d.offer_facts?.conditional_offers)?d.offer_facts.conditional_offers.find(o=>typeof o?.label==='string' && /%|₹/.test(o.label)):null;
  return `<article class="deal-card ${hasImage(d)?'':'without-image'}" data-open="${esc(d.id)}">
    <div class="image-wrap ${hasImage(d)?'':'image-fallback'}">
      <img src="${esc(hasImage(d) ? d.image_url : '/brand/superdeals-logo.png')}" alt="${esc(hasImage(d) ? title : 'SuperDeals — product image unavailable')}" loading="lazy" ${hasImage(d) ? '' : 'data-brand-fallback="true"'}>
      <div class="card-top">${isHotDeal(d)?'<span class="hot-badge">🔥 HOT</span>':''}${p.discount ? `<span class="discount-badge">${esc(discountLabel(d))}</span>` : conditional?`<span class="discount-badge">${esc(shopperText(conditional.label))}</span>`:''}${supportedTerms(d)?.has_coupon?'<span class="coupon-badge">Coupon available</span>':supportedTerms(d)?.has_bank_offer?'<span class="coupon-badge">Bank offer</span>':''}</div>
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

function renderStoreFilters() {
  const select=document.querySelector('#merchant-filter');
  const query=document.querySelector('#store-search').value.toLowerCase().trim();
  const names=[...new Set([...select.options].map(o=>o.value).filter(Boolean).concat([...state.merchants]))].sort();
  const matches=names.filter(name=>name.toLowerCase().includes(query));
  document.querySelector('#store-options').innerHTML=matches.map(name=>`<label class="store-option"><input type="checkbox" value="${esc(name)}" ${state.merchants.has(name)?'checked':''}><span>${esc(name)}</span></label>`).join('') || '<p class="no-store-match">No stores match your search.</p>';
  document.querySelector('#store-value').textContent=state.merchants.size?state.merchants.size+' selected':'All';
  const selected=document.querySelector('#selected-stores');
  selected.hidden=!state.merchants.size;
  selected.innerHTML=[...state.merchants].map(name=>`<button class="selected-store" data-remove-store="${esc(name)}" aria-label="Remove ${esc(name)} filter">${esc(name)} <span aria-hidden="true">×</span></button>`).join('')+(state.merchants.size?'<button id="clear-selected-stores" type="button">Clear all stores</button>':'');
}

function render(list, {keepPage = false} = {}) {
  if (!keepPage) state.visibleCount = 24;
  document.querySelector('#feed-pagination').hidden = list.length <= state.visibleCount;
  renderStoreFilters();
  const counts=state.counts;
  freshCount.textContent = counts ? `${counts.fresh_30m.toLocaleString('en-IN')}/${counts.total_24h.toLocaleString('en-IN')}` : '—/—';
  hotCount.textContent = state.deals.filter(isHotDeal).length;
  if (!list.length) {
    dealsEl.innerHTML = '<div class="empty"><div>✦</div><strong>No fresh deals match this.</strong><p>Try another search or filter.</p></div>';
    return;
  }
  dealsEl.innerHTML = list.slice(0, state.visibleCount).map(card).join('');
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
  let result = list.filter(d => !q || `${displayTitle(d)} ${displayMerchant(d)} ${shopperText(d.product_name)}`.toLowerCase().includes(q));
  const merchants = state.merchants;
  const category = document.querySelector('#category-filter').value;
  result = result.filter(d => (!merchants.size || merchants.has(displayMerchant(d))) && (!category || d.category === category));
  if (state.active === 'drops') result = result.filter(d => priceFacts(d).saving > 0 || (d.offer_facts?.discount_kind !== 'up_to' && priceFacts(d).discount > 0));
  if (state.active === 'under499') result = result.filter(d => priceFacts(d).current !== null && priceFacts(d).current < 500);
  if (state.active === 'discount') result = result.filter(d => d.offer_facts?.discount_kind !== 'up_to' && priceFacts(d).discount >= 50);
  if (state.active === 'hot') result = result.filter(isHotDeal);
  if (state.active === 'saved') result = result.filter(d => state.saved.has(String(d.id)));
  return result;
}

let feedRequest = 0;
async function load(sort = sortEl.value) {
  const request = ++feedRequest;
  state.loading = true;
  dealsEl.innerHTML = '<div class="skeleton-grid">' + Array.from({length:6}, () => '<div class="skeleton"></div>').join('') + '</div>';
  try {
    const payload = await fetchDealWindow(API, sort);
    if (request !== feedRequest) return;
    state.deals = payload.deals || [];
    const counts=payload.counts;
    state.counts = counts && Number.isInteger(counts.fresh_30m) && Number.isInteger(counts.total_24h) && counts.fresh_30m >= 0 && counts.total_24h >= counts.fresh_30m ? counts : null;
    for (const [id, values, label] of [
      ['merchant-filter', [...new Set(state.deals.map(displayMerchant))].sort(), 'All stores'],
      ['category-filter', [...new Set(state.deals.map(d=>d.category).filter(Boolean))].sort(), 'All categories']
    ]) {
      const el = document.getElementById(id), previous = el.value;
      el.innerHTML = `<option value="">${label}</option>` + values.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
      if (values.includes(previous)) el.value = previous;
      if (id === 'category-filter') {el.closest('label').hidden = values.length === 0;el.closest('.browse-controls').hidden=values.length===0;}
    }
    render(localFilter(state.deals));
  } catch {
    if (request !== feedRequest) return;
    document.querySelector('#feed-pagination').hidden = true;
    dealsEl.innerHTML = '<div class="empty"><div>⚡</div><strong>We are warming up.</strong><p>We couldn’t load offers. Check your connection and try again.</p><button class="filter" data-retry>Try again</button></div>';
    state.counts=null; freshCount.textContent = '—/—'; hotCount.textContent = '—';
  } finally {
    if (request === feedRequest) state.loading = false;
  }
}

function setFilter(id) {
  state.active = id;
  document.querySelectorAll('[data-filter]').forEach(b => {b.classList.toggle('active', b.dataset.filter === id);b.setAttribute('aria-pressed', String(b.dataset.filter === id));});
  const titles = {
    latest:['JUST IN','Latest deals'],
    hot:['OVER 50% OFF','Hot deals'],
    drops:['COMPARE & SAVE','Offers with savings'],
    under499:['BUDGET FINDS','Under ₹499'],
    discount:['BIG SAVINGS','50%+ off'],
    saved:['YOUR LIST','Saved deals'],
  };
  [sectionKicker.textContent, sectionTitle.textContent] = titles[id] || titles.latest;
  if (id !== 'saved') sortEl.value = 'newest';
  render(localFilter(state.deals));
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
      <div class="insights">${isHotDeal(d)?'<span>🔥 HOT · Over 50% off</span>':''}${d.has_coupon?'<span>Coupon required at checkout</span>':''}${d.has_card_offer?'<span>Bank offer: confirm eligibility at retailer</span>':''}</div>
      ${termsMarkup(d)}
      ${shopperText(d.description)?`<p class="offer-description">${esc(shopperText(d.description))}</p>`:''}
      <button class="notify-product" type="button" data-notify-product="${esc(title)}">Get notified about this product</button>
      <div class="detail-meta">${d.last_seen_at?`<span>Posted ${esc(age(d.last_seen_at))}</span>`:''}${d.last_verified_at?`<span>Price checked ${esc(age(d.last_verified_at))}</span>`:''}</div>
      <a class="detail-cta" data-detail-go="${esc(d.id)}" href="${esc(API('/go/' + d.id))}" target="_blank" rel="noopener">${merchant==='SuperDeals Find'?'Get deal':`Shop ${esc(merchant)}`} ↗</a>
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
  state.merchants.clear();
  document.querySelector('#store-search').value='';
  document.querySelector('#category-filter').value='';
  setFilter('latest');
  load('newest');
});
const storePicker=document.querySelector('#store-picker');
function closeStorePicker() {storePicker.open=false;document.querySelector('#store-summary').focus();}
function clearStoreFilters() {
  state.merchants.clear();document.querySelector('#merchant-filter').value='';
  render(localFilter(state.deals));
}
document.querySelector('#store-search').addEventListener('input',renderStoreFilters);
document.querySelector('#store-options').addEventListener('change',e=>{
  if (e.target.type!=='checkbox') return;
  const name=e.target.value;
  e.target.checked?state.merchants.add(name):state.merchants.delete(name);
  render(localFilter(state.deals));
  [...document.querySelectorAll('#store-options input')].find(input=>input.value===name)?.focus();
});
document.querySelector('#store-done').addEventListener('click',closeStorePicker);
document.querySelector('#clear-stores').addEventListener('click',clearStoreFilters);
document.querySelector('#selected-stores').addEventListener('click',e=>{
  const remove=e.target.closest('[data-remove-store]');
  if (remove) {state.merchants.delete(remove.dataset.removeStore);render(localFilter(state.deals));document.querySelector('#store-summary').focus();}
  if (e.target.closest('#clear-selected-stores')) {clearStoreFilters();document.querySelector('#store-summary').focus();}
});
document.addEventListener('click',e=>{if(storePicker.open && !storePicker.contains(e.target)) storePicker.open=false;});
storePicker.addEventListener('keydown',e=>{
  if (e.key==='Escape') {e.preventDefault();closeStorePicker();}
});
// Keep the internal single-select adapter synchronized for integrations.
document.querySelector('#merchant-filter').addEventListener('change',e=>{
  state.merchants=new Set(e.target.value?[e.target.value]:[]);render(localFilter(state.deals));
});
document.querySelector('#category-filter').addEventListener('change',()=>render(localFilter(state.deals)));
sortEl.addEventListener('change', () => load(sortEl.value));
document.querySelectorAll('.filter').forEach(b => b.addEventListener('click', () => setFilter(b.dataset.filter)));

document.querySelector('#load-more-deals').addEventListener('click', () => {
  const before = dealsEl.querySelectorAll('.deal-card').length;
  state.visibleCount += 24;
  render(localFilter(state.deals), {keepPage:true});
  const next = dealsEl.querySelectorAll('.title-button')[before];
  next?.focus();
});

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
detail.addEventListener('click', async e => {
  const copy=e.target.closest('[data-copy-code]');
  if (copy) {
    try {
      await navigator.clipboard.writeText(copy.dataset.copyCode);
      copy.textContent='Copied';
      setTimeout(()=>{copy.textContent='Copy code';},1500);
    } catch {
      copy.textContent='Select code to copy';
      const selection=window.getSelection(), range=document.createRange();
      range.selectNodeContents(copy.previousElementSibling);selection.removeAllRanges();selection.addRange(range);
    }
    return;
  }
  const go = e.target.closest('[data-detail-go]');
  if (go && IS_NATIVE) { e.preventDefault(); openDeal(go.dataset.detailGo); return; }
  if (e.target.closest('[data-close]') || e.target === detail) closeDetail();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail();
  if (e.key === 'Tab' && !detail.classList.contains('hidden')) {
    const nodes = [...detail.querySelectorAll('button, a[href], summary')];
    const first=nodes[0], last=nodes.at(-1);
    if (e.shiftKey && document.activeElement===first) {e.preventDefault();last.focus();}
    else if (!e.shiftKey && document.activeElement===last) {e.preventDefault();first.focus();}
  } });
document.querySelector('.brand-mark').addEventListener('click', e => { e.preventDefault(); setFilter('latest'); });

mountDealAlerts({api: API, product: () => state.query});

if (!IS_NATIVE && 'serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
if (IS_NATIVE) SplashScreen.hide().catch(()=>{});
load();
