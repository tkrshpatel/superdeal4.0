const validPrice = v => v != null && v !== '' && Number.isFinite(Number(v)) && Number(v) > 0;
export function priceFacts(d) {
  const current = validPrice(d.current_price) ? Number(d.current_price) : validPrice(d.verified_price) ? Number(d.verified_price) : null;
  const mrp = validPrice(d.mrp) && current !== null && Number(d.mrp) > current ? Number(d.mrp) : null;
  return {current, mrp, saving: mrp === null ? null : mrp-current, discount: mrp === null ? null : Math.round((mrp-current)*100/mrp)};
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
  // EarnKaro is the affiliate service, not evidence of the destination retailer.
  if (/^(earn\s*karo|earnkaro\.(com|in)|retailer|unknown|superdeal find|n\/a|null|none)$/.test(key)) return '';
  return text.toLowerCase().replace(/\b\p{L}/gu, char => char.toUpperCase());
}
export function displayRetailer(deal) {
  return normalizeRetailer(deal.merchant) || normalizeRetailer(deal.enriched_merchant) || 'Retailer';
}
