/* Daily adapter for the unmodified shared transport. No local answer authority. */
(function (global) {
  'use strict';
  function createClient({fetchImpl = global.fetch.bind(global)} = {}) {
    let csrf = null;
    const client = global.GoOdysseyG076NonMapSteps.createClient({
      fetchImpl(path, options) {
        return fetchImpl(path.replace('/api/g076/nonmap/', '/api/g076/daily/'), {
          ...options, headers: {...options.headers, 'X-G076-Daily-CSRF': csrf || ''},
        });
      },
    });
    async function load() {
      const response = await fetchImpl('/api/g076/daily/today', {
        credentials: 'same-origin', cache: 'no-store',
      });
      const data = await response.json();
      if (!response.ok || data.board_only !== true || typeof data.csrf_token !== 'string') {
        throw new Error(data.error || 'daily_authority_unavailable');
      }
      csrf = data.csrf_token;
      return data;
    }
    return Object.freeze({load, open: token => client.open('daily', token),
      play: client.play, retry: client.retry});
  }
  global.GoOdysseyG076DailySteps = Object.freeze({createClient});
})(globalThis);
