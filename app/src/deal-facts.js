const validPrice = v => v != null && v !== '' && Number.isFinite(Number(v)) && Number(v) > 0;
export function priceFacts(d) {
  const current = validPrice(d.current_price) ? Number(d.current_price) : validPrice(d.verified_price) ? Number(d.verified_price) : null;
  const mrp = validPrice(d.mrp) && current !== null && Number(d.mrp) > current ? Number(d.mrp) : null;
  return {current, mrp, saving: mrp === null ? null : mrp-current, discount: mrp === null ? null : Math.round((mrp-current)*100/mrp)};
}
