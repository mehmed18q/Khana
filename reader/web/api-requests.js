/* A fetch-compatible transport for explicit Swagger Execute actions only. */
(() => {
  'use strict';
  const MAX_BYTES = 10 * 1024 * 1024;
  function base64(bytes) {
    let text = '';
    for (let offset = 0; offset < bytes.length; offset += 32768) text += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
    return btoa(text);
  }
  function create(native) {
    const pending = new Map();
    let changed = () => {};
    function finish(id, result, error) {
      const entry = pending.get(id); if (!entry) return;
      pending.delete(id); changed();
      entry.signal?.removeEventListener('abort', entry.abort);
      if (error) entry.reject(new Error(error)); else entry.resolve(result);
    }
    function cancel(documentId) {
      native()?.cancelApiRequests(documentId);
      for (const [id, entry] of pending) if (entry.documentId === documentId) finish(id, null, 'Request cancelled. The server may already have received it.');
    }
    async function fetch(documentId, url, request, valid) {
      if (!native()) throw new Error('The desktop request service is unavailable.');
      let address;
      try { address = new URL(url); } catch { throw new Error('Set an absolute HTTP or HTTPS server URL in Request settings.'); }
      if (!['http:', 'https:'].includes(address.protocol) || address.username || address.password || address.hash) {
        throw new Error('Set an absolute HTTP or HTTPS server URL without embedded credentials in Request settings.');
      }
      const headers = new Headers(request.headers || {}), method = (request.method || 'GET').toUpperCase();
      let bytes = new Uint8Array();
      if (request.body != null) {
        let size = 0;
        if (request.body instanceof Blob) size = request.body.size;
        else if (request.body instanceof FormData) {
          for (const [key, value] of request.body) size += key.length + (value instanceof Blob ? value.size : new TextEncoder().encode(value).length);
        } else size = new TextEncoder().encode(String(request.body)).length;
        if (size > MAX_BYTES) throw new Error('Request exceeds the 10 MB limit.');
        const encoded = new Response(request.body);
        if (!headers.has('content-type') && encoded.headers.has('content-type')) headers.set('content-type', encoded.headers.get('content-type'));
        bytes = new Uint8Array(await encoded.arrayBuffer());
      }
      if (bytes.length > MAX_BYTES) throw new Error('Request exceeds the 10 MB limit.');
      if (!valid() || request.signal?.aborted) throw new Error('Request cancelled.');
      const id = crypto.randomUUID();
      const payload = JSON.stringify({ url: address.href, method, headers: Object.fromEntries(headers), body: base64(bytes) });
      const response = await new Promise((resolve, reject) => {
        const abort = () => cancel(documentId);
        pending.set(id, { documentId, resolve, reject, signal: request.signal, abort });
        request.signal?.addEventListener('abort', abort, { once: true }); changed();
        try { native().executeApiRequest(documentId, id, payload); }
        catch { finish(id, null, 'Could not send the request to the desktop service.'); }
      });
      const body = method === 'HEAD' || [204, 205, 304].includes(response.status) ? null : Uint8Array.from(atob(response.body), char => char.charCodeAt(0));
      return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
    }
    return { fetch, cancel,
      count: documentId => [...pending.values()].filter(entry => entry.documentId === documentId).length,
      onChange: callback => { changed = callback; },
      receive(raw) { const result = JSON.parse(raw); if (pending.get(result.id)?.documentId === result.documentId) finish(result.id, result, result.error); }
    };
  }
  window.ReaderApiRequests = { create };
})();
