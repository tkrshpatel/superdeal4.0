const validPrice = v => v != null && v !== '' && Number.isFinite(Number(v)) && Number(v) > 0;
export function priceFacts(d) {
  const current = validPrice(d.current_price) ? Number(d.current_price) : validPrice(d.verified_price) ? Number(d.verified_price) : null;
  const mrp = validPrice(d.mrp) && current !== null && Number(d.mrp) > current ? Number(d.mrp) : null;
  return {current, mrp, saving: mrp === null ? null : mrp-current, discount: mrp === null ? null : Math.round((mrp-current)*100/mrp)};
}

// Use the exact price ratio, not the rounded display percentage.
export function isHotDeal(deal) {
  const {current,mrp}=priceFacts(deal);
  return current !== null && mrp !== null && current < mrp / 2;
}

// Normalize labels only. Affiliate URLs are never changed or used to guess a store.
const RETAILERS = [
  ['Amazon', ['amazon', 'aamzon', 'amazon.in', 'amazon.com', 'aamzon.in', 'amz.cc', 'amzn.to']],
  ['Flipkart', ['flipkart', 'flipkart.com', 'flkt.cc', 'fkrt.cc']],
  ['Myntra', ['myntra', 'myntra.com']],
  ['AJIO', ['ajio', 'ajio.com']],
  ['Nykaa', ['nykaa', 'nykaa.com']],
  ['Croma', ['croma', 'croma.com']],
  ['Meesho', ['meesho', 'meesho.com']],
  ['JioMart', ['jiomart', 'jiomart.com']],
  ['Tata CLiQ', ['tata cliq', 'tatacliq', 'tatacliq.com']],
  ['Reliance Digital', ['reliance digital', 'reliancedigital.in']],
  ['Snapdeal', ['snapdeal', 'snapdeal.com']],
];
export function normalizeRetailer(value) {
  const text = String(value || '').trim().replace(/\s+/g, ' ');
  if (!text || text.startsWith('@')) return '';
  let key = text.toLowerCase().replace(/[./]+$/, '').replace(/^www\./, '');
  // A URL supplied as a merchant label may include a path or a query string.
  try {
    const url = new URL(/^https?:\/\//i.test(text) ? text : `https://${text}`);
    if (url.hostname.includes('.')) key = url.hostname.toLowerCase().replace(/^www\./, '').replace(/\.$/, '');
  } catch { /* A plain store name does not need URL parsing. */ }
  for (const [name, aliases] of RETAILERS) {
    if (aliases.some(alias => key === alias || (alias.includes('.') && key.endsWith(`.${alias}`)))) return name;
  }
  // Only recognized retailer labels are shown publicly; diagnostics, channel
  // handles and unknown values share the discovery label instead.
  return '';
}
export function displayRetailer(deal) {
  return normalizeRetailer(deal.merchant) || normalizeRetailer(deal.enriched_merchant) || 'SuperDeals Find';
}
