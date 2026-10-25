const validPrice = v => typeof v !== 'boolean' && v != null && v !== '' && Number.isFinite(Number(v)) && Number(v) > 0;
const evidence = d => [1,2,3,4,5,6,7,8].includes(d.offer_facts?.version) ? d.offer_facts : null;
export function priceFacts(d) {
  const f=evidence(d);
  const current = f ? (validPrice(f.current_price)?Number(f.current_price):null) : validPrice(d.current_price) ? Number(d.current_price) : validPrice(d.verified_price) ? Number(d.verified_price) : null;
  const original=f?f.mrp:d.mrp;
  const mrp=validPrice(original)&&current!==null&&Number(original)>current?Number(original):null;
  const stated=f&&['exact','up_to'].includes(f.discount_kind)&&validPrice(f.discount_pct)&&Number(f.discount_pct)<=100?Number(f.discount_pct):null;
  return {current,mrp,saving:mrp===null?(f&&validPrice(f.stated_savings)?Number(f.stated_savings):null):mrp-current,discount:stated??(mrp===null?null:Math.round((mrp-current)*100/mrp))};
}

export function isHotDeal(d) {
  const timestamp=d.published_at??d.last_seen_at;
  const posted=typeof timestamp==='string'?Date.parse(timestamp.replace(' ','T')):NaN;
  const age=Date.now()-posted;
  if(!Number.isFinite(posted)||age<0||age>30*60*1000)return false;
  const f=evidence(d),{current,mrp}=priceFacts(d);
  if(f?.discount_kind==='up_to')return false;
  if(f?.discount_kind==='exact')return Number(f.discount_pct)>75&&Number(f.discount_pct)<=100;
  return current!==null&&mrp!==null&&current<mrp/4;
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
