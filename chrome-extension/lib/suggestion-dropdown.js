/**
 * Suggestion dropdown UI component.
 * Renders a floating dropdown near input fields with defect suggestions.
 */
const SuggestionDropdown = (() => {
  let _container = null;
  let _items = [];
  let _highlightIndex = -1;
  let _onSelect = null;
  let _targetElement = null;

  function _createContainer() {
    if (_container) return _container;

    _container = document.createElement('div');
    _container.id = 'bv-suggestion-dropdown';
    _container.className = 'bv-dropdown';
    _container.setAttribute('role', 'listbox');
    _container.style.display = 'none';
    document.body.appendChild(_container);
    return _container;
  }

  function show(items, targetEl, onSelectCb) {
    _items = items || [];
    _highlightIndex = -1;
    _onSelect = onSelectCb;
    _targetElement = targetEl;

    if (_items.length === 0) {
      hide();
      return;
    }

    const container = _createContainer();
    container.innerHTML = '';

    // Header
    const header = document.createElement('div');
    header.className = 'bv-dropdown-header';
    header.textContent = 'BV AI Suggestions';
    container.appendChild(header);

    // Items
    _items.forEach((item, idx) => {
      const row = document.createElement('div');
      row.className = 'bv-dropdown-item';
      row.setAttribute('role', 'option');
      row.dataset.index = idx;

      const text = document.createElement('div');
      text.className = 'bv-dropdown-text';
      text.textContent = item.text_en || item.standard_text_en || '';
      row.appendChild(text);

      const meta = document.createElement('div');
      meta.className = 'bv-dropdown-meta';

      const ref = item.regulation_ref || '';
      const risk = item.detention_risk || '';
      const metaParts = [];
      if (ref) metaParts.push(ref);
      if (risk) metaParts.push(`Risk: ${risk}`);
      meta.textContent = metaParts.join(' | ');
      row.appendChild(meta);

      row.addEventListener('mouseenter', () => _setHighlight(idx));
      row.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        _selectItem(idx);
      });

      container.appendChild(row);
    });

    // Footer
    const footer = document.createElement('div');
    footer.className = 'bv-dropdown-footer';
    footer.innerHTML = '<kbd>&uarr;&darr;</kbd> Navigate <kbd>Enter</kbd> Select <kbd>Esc</kbd> Close';
    container.appendChild(footer);

    _positionDropdown(targetEl, container);
    container.style.display = 'block';
  }

  function _positionDropdown(targetEl, container) {
    const rect = targetEl.getBoundingClientRect();
    const top = rect.bottom + window.scrollY + 4;
    const left = rect.left + window.scrollX;

    container.style.position = 'absolute';
    container.style.top = `${top}px`;
    container.style.left = `${left}px`;
    container.style.width = `${Math.max(rect.width, 400)}px`;
    container.style.zIndex = '2147483647';
  }

  function hide() {
    if (_container) {
      _container.style.display = 'none';
      _container.innerHTML = '';
    }
    _items = [];
    _highlightIndex = -1;
    _targetElement = null;
  }

  function _setHighlight(idx) {
    _highlightIndex = idx;
    if (!_container) return;
    const items = _container.querySelectorAll('.bv-dropdown-item');
    items.forEach((el, i) => {
      el.classList.toggle('bv-dropdown-item--active', i === idx);
    });
  }

  function highlightNext() {
    if (_items.length === 0) return;
    _setHighlight((_highlightIndex + 1) % _items.length);
  }

  function highlightPrev() {
    if (_items.length === 0) return;
    _setHighlight((_highlightIndex - 1 + _items.length) % _items.length);
  }

  function _selectItem(idx) {
    if (idx >= 0 && idx < _items.length && _onSelect) {
      _onSelect(_items[idx], _targetElement);
    }
    hide();
  }

  function selectHighlighted() {
    if (_highlightIndex >= 0) {
      _selectItem(_highlightIndex);
    }
  }

  function isVisible() {
    return _container && _container.style.display !== 'none' && _items.length > 0;
  }

  return {
    show,
    hide,
    highlightNext,
    highlightPrev,
    selectHighlighted,
    isVisible,
  };
})();
