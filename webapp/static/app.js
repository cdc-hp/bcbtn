(() => {
  const body = document.body;
  const toggle = document.querySelector('[data-sidebar-toggle]');
  const close = () => {
    body.classList.remove('cdc-menu-open');
    toggle?.setAttribute('aria-expanded', 'false');
  };
  toggle?.addEventListener('click', () => {
    const open = body.classList.toggle('cdc-menu-open');
    toggle.setAttribute('aria-expanded', String(open));
  });
  document.querySelector('[data-sidebar-close]')?.addEventListener('click', close);
  document.querySelectorAll('.cdc-sidebar a').forEach(link => link.addEventListener('click', close));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });

  const columnSettings = document.querySelector('[data-column-settings]');
  const recordsTable = document.querySelector('[data-records-table]');
  if (columnSettings && recordsTable) {
    const toggles = [...columnSettings.querySelectorAll('[data-column-toggle]')];
    const options = [...columnSettings.querySelectorAll('[data-column-option]')];
    const columnSearch = columnSettings.querySelector('[data-column-search]');
    const storageKey = `cdc-visible-columns:${window.location.pathname}`;
    let savedColumns = null;
    try {
      const parsed = JSON.parse(window.localStorage.getItem(storageKey));
      if (Array.isArray(parsed)) savedColumns = new Set(parsed);
    } catch (_) {
      savedColumns = null;
    }

    const setColumnVisible = (key, visible) => {
      recordsTable.querySelectorAll(`[data-column-key="${CSS.escape(key)}"]`).forEach(cell => {
        cell.classList.toggle('cdc-column-hidden', !visible);
      });
    };
    const saveColumns = () => {
      const visible = toggles.filter(input => input.checked).map(input => input.value);
      window.localStorage.setItem(storageKey, JSON.stringify(visible));
    };
    toggles.forEach(input => {
      if (savedColumns) input.checked = savedColumns.has(input.value);
      setColumnVisible(input.value, input.checked);
      input.addEventListener('change', () => {
        setColumnVisible(input.value, input.checked);
        saveColumns();
      });
    });
    columnSettings.querySelector('[data-column-reset]')?.addEventListener('click', () => {
      toggles.forEach(input => {
        const visible = input.dataset.defaultVisible === 'true';
        input.checked = visible;
        setColumnVisible(input.value, visible);
      });
      window.localStorage.removeItem(storageKey);
    });
    columnSettings.querySelector('[data-column-all]')?.addEventListener('click', () => {
      toggles.forEach(input => {
        input.checked = true;
        setColumnVisible(input.value, true);
      });
      saveColumns();
    });
    columnSearch?.addEventListener('input', () => {
      const query = columnSearch.value.trim().toLocaleLowerCase('vi');
      options.forEach(option => {
        option.hidden = Boolean(query) && !option.textContent.toLocaleLowerCase('vi').includes(query);
      });
    });
    document.addEventListener('click', event => {
      if (!columnSettings.contains(event.target)) columnSettings.removeAttribute('open');
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') columnSettings.removeAttribute('open');
    });
  }

  const batchItems = [...document.querySelectorAll('[data-batch-item]')];
  const batchCount = document.querySelector('[data-batch-count]');
  if (batchItems.length && batchCount) {
    const updateBatchCount = () => {
      const count = batchItems.filter(input => input.checked).length;
      batchCount.textContent = `(${count})`;
      batchCount.hidden = count === 0;
    };
    batchItems.forEach(input => input.addEventListener('change', updateBatchCount));
    updateBatchCount();
  }
})();
