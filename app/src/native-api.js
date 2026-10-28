export const PRODUCTION_API = 'https://thesuperdeals.in';

export function resolveApiBase(native, override = '') {
  if (native) return PRODUCTION_API;
  return String(override || '').replace(/\/$/, '');
}

// Native HTTP uses Android's HTTPS stack; the website keeps same-origin fetch.
export function createApiFetch({native, request, webFetch = globalThis.fetch}) {
  if (!native) return (...args) => webFetch(...args);
  return async (url, options = {}) => {
    const parsed = new URL(url);
    if (parsed.origin !== PRODUCTION_API || !/^\/(deals|health|api\/v1\/alerts)(\/|$)/.test(parsed.pathname)) {
      throw new Error('Unsupported API address.');
    }
    const signal = options.signal;
    if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError');
    let cancel;
    const aborted = new Promise((_, reject) => {
      cancel = () => reject(new DOMException('Request cancelled', 'AbortError'));
      signal?.addEventListener('abort', cancel, {once:true});
    });
    try {
      const operation = request({url: parsed.href, method: options.method || 'GET',
        headers: {...Object.fromEntries(new Headers(options.headers)), Origin: PRODUCTION_API},
        ...(options.body ? {data: JSON.parse(options.body)} : {}),
        connectTimeout: 15000, readTimeout: 20000, responseType: 'json'});
      const result = await (signal ? Promise.race([operation, aborted]) : operation);
      // Native response headers are not needed by the feed/form. Keep a standard Response interface.
      return new Response(typeof result.data === 'string' ? result.data : JSON.stringify(result.data),
        {status: result.status, headers: {'Content-Type':'application/json'}});
    } finally {
      signal?.removeEventListener('abort', cancel);
    }
  };
}
