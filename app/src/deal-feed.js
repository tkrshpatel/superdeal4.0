// Fetch the complete 24-hour window in bounded API pages, without a total-card cap.
// UI pagination below this layer keeps the rendered grid small.
export async function fetchDealWindow(api, sort, fetcher = fetch) {
  const deals = [], seen = new Set();
  let offset = 0, snapshot, first;
  while (true) {
    const params = new URLSearchParams({limit:'48', sort});
    if (offset) params.set('offset', String(offset));
    if (snapshot) params.set('as_of', snapshot);
    const response = await fetcher(api('/deals?' + params), {cache:'no-store'});
    if (!response.ok) throw new Error('API unavailable');
    const page = await response.json();
    if (!Array.isArray(page.deals)) throw new Error('Invalid deal page');
    first ||= page;
    snapshot ||= page.as_of;
    let added = 0;
    for (const deal of page.deals) {
      const id = String(deal.id);
      if (!seen.has(id)) {seen.add(id);deals.push(deal);added++;}
    }
    if (!page.has_more) break;
    const next = page.next_offset ?? offset + page.deals.length;
    if (!added || !Number.isInteger(next) || next <= offset) throw new Error('Pagination did not advance');
    offset = next;
  }
  return {...first, deals};
}
