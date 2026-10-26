/* Per-mode capability is server-owned. Missing registration is HOLD. */
window.G076Rating = (() => {
  async function json(url, options) {
    const response = await fetch(url, {credentials:'include', cache:'no-store', ...options});
    const value = await response.json();
    if (!response.ok || value.error) throw new Error(value.error || 'Rating Trial HOLD');
    return value;
  }
  async function mode() {
    try {
      const value = await json('/api/g076/rating/capability');
      if (!['legacy', 'steps'].includes(value.mode)) throw new Error('invalid capability');
      return value.mode;
    } catch (error) { throw new Error('Rating Trial HOLD', {cause:error}); }
  }
  async function post(url, body, retries=0) {
    const options = {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
    for (let i=0;;i++) {
      try { return await json(url, options); }
      catch (error) { if (i>=retries) throw error; }
    }
  }
  return Object.freeze({mode, post, json});
})();
