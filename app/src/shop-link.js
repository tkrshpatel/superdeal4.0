// Native plugin opens a retailer app, otherwise Custom Tabs stays inside SuperDeals.
export async function openShopLink(url,{native,handoff,browse,webOpen}) {
  if (!native) {webOpen(url);return;}
  let destination = url;
  try {
    const result = await handoff({url});
    if (result.opened) return;
    if (result.fallbackUrl) {
      const candidate = new URL(result.fallbackUrl);
      if (candidate.protocol === 'https:' && !candidate.username && !candidate.password) destination=result.fallbackUrl;
    }
  } catch { /* Keep the original tracked redirect for browser fallback. */ }
  await browse({url:destination});
}
