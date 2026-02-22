/**
 * Side Panel — Chatbot + Explain display.
 */
(() => {
  'use strict';

  const messagesEl = document.getElementById('messages');
  const chatInput = document.getElementById('chatInput');
  const sendBtn = document.getElementById('sendBtn');

  let _sessionId = null;
  let _apiBaseUrl = 'http://localhost:8000';

  // Load settings
  chrome.runtime.sendMessage({ type: 'GET_SETTINGS' }, (resp) => {
    if (resp?.apiBaseUrl) _apiBaseUrl = resp.apiBaseUrl;
  });

  // ── Chat ──

  sendBtn.addEventListener('click', () => sendMessage());
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    appendMessage(text, 'user');
    chatInput.value = '';
    sendBtn.disabled = true;

    const loadingEl = appendMessage('<span class="loading"></span> Thinking...', 'assistant');

    try {
      const resp = await fetch(`${_apiBaseUrl}/api/v1/extension/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, session_id: _sessionId }),
        signal: AbortSignal.timeout(30000),
      });

      const data = await resp.json();
      _sessionId = data.session_id || _sessionId;
      loadingEl.remove();

      const answer = data.answer_text || data.answer || 'No response.';
      appendMessage(answer, 'assistant');

      if (data.sources?.length) {
        const sourceText = data.sources
          .slice(0, 3)
          .map((s) => s.breadcrumb || s.url || '')
          .filter(Boolean)
          .join('\n');
        if (sourceText) {
          appendMessage(`Sources:\n${sourceText}`, 'assistant');
        }
      }
    } catch (err) {
      loadingEl.remove();
      appendMessage(`Error: ${err.message}`, 'assistant');
    } finally {
      sendBtn.disabled = false;
      chatInput.focus();
    }
  }

  // ── Explain handler (from context menu) ──

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'EXPLAIN_TEXT' && msg.selectedText) {
      handleExplain(msg.selectedText);
    }
  });

  async function handleExplain(text) {
    appendMessage(`Explain: "${text.slice(0, 100)}${text.length > 100 ? '...' : ''}"`, 'user');
    const loadingEl = appendMessage('<span class="loading"></span> Generating explanation...', 'explain');

    try {
      const resp = await fetch(`${_apiBaseUrl}/api/v1/extension/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selected_text: text }),
        signal: AbortSignal.timeout(10000),
      });

      const data = await resp.json();
      loadingEl.remove();
      appendMessage(data.explanation || 'No explanation generated.', 'explain');
    } catch (err) {
      loadingEl.remove();
      appendMessage(`Explain error: ${err.message}`, 'assistant');
    }
  }

  // ── UI helpers ──

  function appendMessage(content, type) {
    const div = document.createElement('div');
    div.className = `msg msg--${type}`;

    if (content.includes('<')) {
      div.innerHTML = content;
    } else {
      const pre = document.createElement('pre');
      pre.textContent = content;
      div.appendChild(pre);
    }

    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }
})();
