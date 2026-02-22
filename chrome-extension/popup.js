/**
 * Popup — settings and status display.
 */
document.addEventListener('DOMContentLoaded', async () => {
  const apiUrlInput = document.getElementById('apiUrl');
  const saveBtn = document.getElementById('saveBtn');
  const apiDot = document.getElementById('apiDot');
  const apiStatus = document.getElementById('apiStatus');
  const kbDot = document.getElementById('kbDot');
  const kbStatus = document.getElementById('kbStatus');

  // Load saved settings
  chrome.runtime.sendMessage({ type: 'GET_SETTINGS' }, (resp) => {
    if (resp && resp.apiBaseUrl) {
      apiUrlInput.value = resp.apiBaseUrl;
    }
    checkHealth(resp?.apiBaseUrl || 'http://localhost:8000');
  });

  // Save settings
  saveBtn.addEventListener('click', () => {
    const url = apiUrlInput.value.trim().replace(/\/+$/, '');
    chrome.runtime.sendMessage({ type: 'SAVE_SETTINGS', apiBaseUrl: url }, () => {
      saveBtn.textContent = 'Saved!';
      setTimeout(() => { saveBtn.textContent = 'Save'; }, 1500);
      checkHealth(url);
    });
  });

  async function checkHealth(baseUrl) {
    try {
      const resp = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(3000) });
      if (resp.ok) {
        apiDot.className = 'status-dot status-dot--ok';
        apiStatus.textContent = 'Connected';
      } else {
        apiDot.className = 'status-dot status-dot--err';
        apiStatus.textContent = `Error ${resp.status}`;
      }
    } catch {
      apiDot.className = 'status-dot status-dot--err';
      apiStatus.textContent = 'Offline';
    }

    // Check KB version
    try {
      const kbResp = await fetch(`${baseUrl}/api/v1/extension/kb-version`, {
        signal: AbortSignal.timeout(3000),
      });
      if (kbResp.ok) {
        const data = await kbResp.json();
        kbDot.className = 'status-dot status-dot--ok';
        kbStatus.textContent = `v${data.version} (${data.defect_count} defects)`;
      }
    } catch {
      kbDot.className = 'status-dot status-dot--err';
      kbStatus.textContent = 'Unavailable';
    }
  }
});
