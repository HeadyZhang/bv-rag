/**
 * Local defect knowledge base cache.
 * Syncs with backend KB and provides fast local lookups.
 */
const DefectCache = (() => {
  const STORAGE_KEY = 'bv_defect_cache';
  const VERSION_KEY = 'bv_defect_cache_version';

  let _defects = [];
  let _byArea = {};
  let _byCategory = {};
  let _chineseKeywords = {};
  let _version = '';
  let _loaded = false;

  function load() {
    return new Promise((resolve) => {
      if (typeof chrome !== 'undefined' && chrome.storage) {
        chrome.storage.local.get([STORAGE_KEY, VERSION_KEY], (result) => {
          if (result[STORAGE_KEY]) {
            _setData(result[STORAGE_KEY]);
            _version = result[VERSION_KEY] || '';
          }
          _loaded = true;
          resolve();
        });
      } else {
        _loaded = true;
        resolve();
      }
    });
  }

  function _setData(data) {
    _defects = data.defects || [];
    _byArea = data.index?.by_area || {};
    _byCategory = data.index?.by_category || {};
    _chineseKeywords = data.index?.chinese_keyword_map || {};
    _version = data.version || '';
  }

  function save() {
    if (typeof chrome !== 'undefined' && chrome.storage) {
      const data = {
        defects: _defects,
        index: { by_area: _byArea, by_category: _byCategory, chinese_keyword_map: _chineseKeywords },
        version: _version,
      };
      chrome.storage.local.set({
        [STORAGE_KEY]: data,
        [VERSION_KEY]: _version,
      });
    }
  }

  async function sync() {
    try {
      const versionInfo = await BvApi.kbVersion();
      if (versionInfo.version === _version && _defects.length > 0) {
        return { synced: false, reason: 'up-to-date' };
      }
      const updateResp = await BvApi.kbUpdate(_version);
      if (updateResp.updates && updateResp.updates.length > 0) {
        _defects = updateResp.updates;
        _rebuildIndexes();
        _version = updateResp.current_version;
        save();
        return { synced: true, count: _defects.length };
      }
      return { synced: false, reason: 'no-updates' };
    } catch (err) {
      console.warn('[DefectCache] sync failed:', err.message);
      return { synced: false, reason: err.message };
    }
  }

  function _rebuildIndexes() {
    _byArea = {};
    _byCategory = {};
    _chineseKeywords = {};

    for (const defect of _defects) {
      const id = defect.id;
      const cat = defect.category;
      _byCategory[cat] = _byCategory[cat] || [];
      _byCategory[cat].push(id);
    }
  }

  function queryByArea(area, shipType, topK = 8) {
    const areaKey = _normalize(area);
    const ids = _byArea[areaKey] || [];
    const results = ids
      .map(id => _defects.find(d => d.id === id))
      .filter(Boolean)
      .sort((a, b) => (a.frequency_rank || 999) - (b.frequency_rank || 999));
    return results.slice(0, topK);
  }

  function searchByKeyword(keyword, topK = 5) {
    const kw = keyword.toLowerCase();
    const scored = [];
    for (const defect of _defects) {
      let score = 0;
      if ((defect.standard_text_en || '').toLowerCase().includes(kw)) score += 3;
      if ((defect.standard_text_zh || '').includes(kw)) score += 5;
      if ((defect.category || '').toLowerCase().includes(kw)) score += 1;
      if (score > 0) scored.push({ defect, score });
    }
    scored.sort((a, b) => b.score - a.score || (a.defect.frequency_rank || 999) - (b.defect.frequency_rank || 999));
    return scored.slice(0, topK).map(s => s.defect);
  }

  function _normalize(value) {
    return (value || '').trim().toLowerCase().replace(/[\s\-\/]+/g, '_');
  }

  return {
    load,
    sync,
    queryByArea,
    searchByKeyword,
    getVersion: () => _version,
    getCount: () => _defects.length,
    isLoaded: () => _loaded,
  };
})();
