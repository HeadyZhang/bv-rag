/**
 * BV Maritime Extension — Content Script
 *
 * Runs on every page. Listens for focus/input events on text fields,
 * manages the suggestion dropdown, and handles right-click fill/explain.
 */
(() => {
  'use strict';

  // ── State ──
  let _activeField = null;
  let _debounceTimer = null;
  const DEBOUNCE_MS = 300;

  // ── Form context extraction ──

  function getFormContext(element) {
    const context = {
      field_label: '',
      ship_type: '',
      ship_name: '',
      inspection_type: '',
      inspection_area: '',
    };

    context.field_label = getFieldLabel(element);

    const form = element.closest('form')
      || element.closest('table')
      || element.closest('[role="form"]');
    if (!form) return context;

    const inputs = form.querySelectorAll('input, select, textarea');
    inputs.forEach((inp) => {
      if (inp === element) return;
      const key = getFieldLabel(inp).toLowerCase();
      const val = (inp.value || '').trim();
      if (!key || !val || val.length > 200) return;

      if (matchesAny(key, ['ship type', 'vessel type', 'type of ship'])) {
        context.ship_type = val;
      } else if (matchesAny(key, ['ship name', 'vessel name'])) {
        context.ship_name = val;
      } else if (matchesAny(key, ['inspection type', 'survey type'])) {
        context.inspection_type = val;
      } else if (matchesAny(key, ['area', 'location', 'space'])) {
        context.inspection_area = val;
      }
    });

    return context;
  }

  function getFieldLabel(element) {
    const id = element.id || element.name;
    if (id) {
      const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (label) return label.textContent.trim();
    }
    if (element.placeholder) return element.placeholder;
    if (element.getAttribute('aria-label')) return element.getAttribute('aria-label');

    const parent = element.closest('div, td, th, li, dt');
    if (parent) {
      const walker = document.createTreeWalker(parent, NodeFilter.SHOW_TEXT);
      let text = '';
      let node;
      while ((node = walker.nextNode())) {
        const t = node.textContent.trim();
        if (t && t.length < 100) {
          text = t;
          break;
        }
      }
      if (text) return text;
    }
    return '';
  }

  function matchesAny(text, patterns) {
    const t = text.toLowerCase();
    return patterns.some((p) => t.includes(p));
  }

  function isDefectField(element) {
    const label = getFieldLabel(element).toLowerCase();
    const defectKeywords = [
      'defect', 'deficiency', 'finding', 'observation',
      'description', 'detail', 'remark', 'comment', 'note',
    ];
    return defectKeywords.some((kw) => label.includes(kw));
  }

  // ── Event handlers ──

  function handleFocus(e) {
    const el = e.target;
    if (!isTextInput(el)) return;
    if (!isDefectField(el)) return;

    _activeField = el;

    const context = getFormContext(el);
    if (!context.inspection_area && !context.ship_type) return;

    // L1: Predict suggestions on focus
    BvApi.predict({
      ship_type: context.ship_type,
      inspection_area: context.inspection_area,
      inspection_type: context.inspection_type,
      form_context: context,
    })
      .then((resp) => {
        if (el !== _activeField) return;
        const suggestions = (resp.suggestions || []).map(formatSuggestion);
        SuggestionDropdown.show(suggestions, el, handleSuggestionSelect);
      })
      .catch((err) => {
        console.warn('[BV] predict failed:', err.message);
      });
  }

  function handleInput(e) {
    const el = e.target;
    if (!isTextInput(el) || el !== _activeField) return;

    const value = el.value.trim();
    if (value.length < 2) {
      SuggestionDropdown.hide();
      return;
    }

    // L2: Autocomplete with debounce
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => {
      const context = getFormContext(el);
      BvApi.complete(value, {
        field_label: context.field_label,
        ship_type: context.ship_type,
        inspection_area: context.inspection_area,
        form_context: context,
      })
        .then((resp) => {
          if (el !== _activeField) return;
          const suggestions = (resp.suggestions || []).map(formatSuggestion);
          SuggestionDropdown.show(suggestions, el, handleSuggestionSelect);
        })
        .catch((err) => {
          console.warn('[BV] complete failed:', err.message);
        });
    }, DEBOUNCE_MS);
  }

  function handleKeydown(e) {
    if (!SuggestionDropdown.isVisible()) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        SuggestionDropdown.highlightNext();
        break;
      case 'ArrowUp':
        e.preventDefault();
        SuggestionDropdown.highlightPrev();
        break;
      case 'Enter':
      case 'Tab':
        if (SuggestionDropdown.isVisible()) {
          e.preventDefault();
          SuggestionDropdown.selectHighlighted();
        }
        break;
      case 'Escape':
        SuggestionDropdown.hide();
        break;
    }
  }

  function handleBlur() {
    // Delay to allow click on dropdown item
    setTimeout(() => {
      if (!document.querySelector('.bv-dropdown-item:hover')) {
        SuggestionDropdown.hide();
      }
    }, 200);
  }

  function handleSuggestionSelect(suggestion, targetEl) {
    if (!targetEl) return;
    const text = suggestion.text_en || suggestion.standard_text_en || '';
    const ref = suggestion.regulation_ref || '';
    const fillText = ref ? `${text} (Ref: ${ref})` : text;

    targetEl.value = fillText;
    targetEl.dispatchEvent(new Event('input', { bubbles: true }));
    targetEl.dispatchEvent(new Event('change', { bubbles: true }));

    showToast('Filled successfully', 'success');
    showFeedbackBubble(targetEl, suggestion);
  }

  // ── Message handler (from background.js) ──

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === 'FILL_REQUEST') {
      handleFillRequest(msg);
      sendResponse({ ok: true });
    } else if (msg.type === 'EXPLAIN_REQUEST') {
      handleExplainRequest(msg);
      sendResponse({ ok: true });
    }
  });

  async function handleFillRequest(msg) {
    const activeEl = document.activeElement;
    showToast('Generating standard text...', 'info');

    try {
      const context = activeEl && isTextInput(activeEl) ? getFormContext(activeEl) : {};
      const result = await BvApi.fill(msg.selectedText, msg.targetLang || 'en', {
        field_label: context.field_label || '',
        form_context: context,
      });

      const filledText = result.filled_text || '';

      // Try to replace selection in active element
      if (activeEl && isTextInput(activeEl)) {
        const start = activeEl.selectionStart;
        const end = activeEl.selectionEnd;
        const original = activeEl.value;
        activeEl.value = original.substring(0, start) + filledText + original.substring(end);
        activeEl.dispatchEvent(new Event('input', { bubbles: true }));
        showToast('Filled!', 'success');
      } else {
        // Copy to clipboard as fallback
        await navigator.clipboard.writeText(filledText);
        showToast('Copied to clipboard!', 'success');
      }
    } catch (err) {
      showToast(`Fill failed: ${err.message}`, 'error');
    }
  }

  async function handleExplainRequest(msg) {
    // Send to side panel via background
    chrome.runtime.sendMessage({
      type: 'SHOW_EXPLANATION',
      selectedText: msg.selectedText,
    });
    showToast('Opening explanation in side panel...', 'info');
  }

  // ── Utility functions ──

  function isTextInput(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === 'textarea') return true;
    if (tag === 'input') {
      const type = (el.type || '').toLowerCase();
      return ['text', 'search', ''].includes(type);
    }
    return el.contentEditable === 'true';
  }

  function formatSuggestion(s) {
    return {
      id: s.id || '',
      text_en: s.text_en || s.standard_text_en || '',
      text_zh: s.text_zh || s.standard_text_zh || '',
      regulation_ref: s.regulation_ref || '',
      category: s.category || '',
      detention_risk: s.detention_risk || '',
      confidence: s.confidence || 0,
      frequency_rank: s.frequency_rank || 999,
    };
  }

  function showToast(message, type = 'info') {
    const existing = document.querySelector('.bv-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `bv-toast bv-toast--${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  function showFeedbackBubble(targetEl, suggestion) {
    const existing = document.querySelector('.bv-feedback');
    if (existing) existing.remove();

    const bubble = document.createElement('div');
    bubble.className = 'bv-feedback';

    const label = document.createElement('span');
    label.textContent = 'Filled.';
    bubble.appendChild(label);

    const accurateBtn = document.createElement('button');
    accurateBtn.className = 'bv-feedback-btn';
    accurateBtn.textContent = 'Accurate';
    accurateBtn.onclick = () => {
      BvApi.feedback({
        original_input: suggestion.text_en,
        generated_text: suggestion.text_en,
        is_accurate: true,
        defect_id: suggestion.id || '',
      }).catch(() => {});
      bubble.remove();
    };
    bubble.appendChild(accurateBtn);

    const inaccurateBtn = document.createElement('button');
    inaccurateBtn.className = 'bv-feedback-btn';
    inaccurateBtn.textContent = 'Inaccurate';
    inaccurateBtn.onclick = () => {
      BvApi.feedback({
        original_input: suggestion.text_en,
        generated_text: suggestion.text_en,
        is_accurate: false,
        defect_id: suggestion.id || '',
      }).catch(() => {});
      bubble.remove();
    };
    bubble.appendChild(inaccurateBtn);

    const undoBtn = document.createElement('button');
    undoBtn.className = 'bv-feedback-btn';
    undoBtn.textContent = 'Undo';
    undoBtn.onclick = () => {
      targetEl.value = '';
      targetEl.dispatchEvent(new Event('input', { bubbles: true }));
      bubble.remove();
    };
    bubble.appendChild(undoBtn);

    targetEl.parentElement.appendChild(bubble);
    setTimeout(() => bubble.remove(), 15000);
  }

  // ── Initialize ──

  document.addEventListener('focusin', handleFocus, true);
  document.addEventListener('input', handleInput, true);
  document.addEventListener('keydown', handleKeydown, true);
  document.addEventListener('focusout', handleBlur, true);
})();
