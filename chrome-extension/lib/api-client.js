/**
 * BV-RAG API client for Chrome extension.
 * Wraps all backend communication with timeout, retry, and error handling.
 */
const BvApi = (() => {
  const DEFAULT_BASE_URL = 'http://localhost:8000';
  const TIMEOUT_MS = 10000;

  function getBaseUrl() {
    // Will be updated from storage in background.js
    return window.__BV_API_BASE_URL || DEFAULT_BASE_URL;
  }

  async function request(endpoint, options = {}) {
    const url = `${getBaseUrl()}/api/v1/extension${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), options.timeout || TIMEOUT_MS);

    try {
      const response = await fetch(url, {
        method: options.method || 'GET',
        headers: { 'Content-Type': 'application/json' },
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`);
      }
      return await response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        throw new Error(`Request timeout after ${options.timeout || TIMEOUT_MS}ms`);
      }
      throw err;
    }
  }

  return {
    predict(context) {
      return request('/predict', {
        method: 'POST',
        body: context,
        timeout: 3000,
      });
    },

    complete(partialInput, context) {
      return request('/complete', {
        method: 'POST',
        body: { partial_input: partialInput, ...context },
        timeout: 3000,
      });
    },

    fill(selectedText, targetLang, context) {
      return request('/fill', {
        method: 'POST',
        body: { selected_text: selectedText, target_lang: targetLang, ...context },
        timeout: 5000,
      });
    },

    explain(selectedText, pageContext) {
      return request('/explain', {
        method: 'POST',
        body: { selected_text: selectedText, page_context: pageContext || '' },
        timeout: 5000,
      });
    },

    chat(text, sessionId) {
      return request('/chat', {
        method: 'POST',
        body: { text, session_id: sessionId },
        timeout: 15000,
      });
    },

    feedback(data) {
      return request('/feedback', {
        method: 'POST',
        body: data,
        timeout: 3000,
      });
    },

    kbVersion() {
      return request('/kb-version', { timeout: 2000 });
    },

    kbUpdate(sinceVersion) {
      return request(`/kb-update?since_version=${encodeURIComponent(sinceVersion)}`, {
        timeout: 5000,
      });
    },

    setBaseUrl(url) {
      window.__BV_API_BASE_URL = url;
    },
  };
})();
