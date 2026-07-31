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

  document.querySelectorAll('[data-criteria-multichoice]').forEach(picker => {
    const form = picker.closest('form');
    const options = [...picker.querySelectorAll('[data-criteria-option]')];
    const checkboxes = options.map(option => option.querySelector('input[type="checkbox"]'));
    const search = picker.querySelector('[data-criteria-search]');
    const count = picker.querySelector('[data-criteria-count]');
    const summaryCount = picker.closest('details')?.querySelector('[data-criteria-summary-count]');
    const selection = picker.querySelector('[data-criteria-selection]');
    const updateSelection = () => {
      const selected = options.filter(option => option.querySelector('input').checked);
      if (count) count.textContent = `${selected.length}/${options.length}`;
      if (summaryCount) summaryCount.textContent = String(selected.length);
      if (selection) {
        const labels = selected.map(option => option.querySelector('span').textContent.trim());
        selection.textContent = labels.length ? `Đã chọn: ${labels.join(', ')}` : 'Chưa chọn trường dữ liệu nào.';
      }
    };
    checkboxes.forEach(input => input.addEventListener('change', updateSelection));
    search?.addEventListener('input', () => {
      const query = search.value.trim().toLocaleLowerCase('vi');
      options.forEach(option => {
        option.hidden = Boolean(query) && !option.textContent.toLocaleLowerCase('vi').includes(query);
      });
    });
    picker.querySelector('[data-criteria-all]')?.addEventListener('click', () => {
      options.filter(option => !option.hidden).forEach(option => { option.querySelector('input').checked = true; });
      updateSelection();
    });
    picker.querySelector('[data-criteria-clear]')?.addEventListener('click', () => {
      checkboxes.forEach(input => { input.checked = false; });
      updateSelection();
    });
    form?.addEventListener('submit', event => {
      if (!checkboxes.some(input => input.checked)) {
        event.preventDefault();
        search?.focus();
        if (selection) selection.textContent = 'Hãy chọn ít nhất một trường dữ liệu.';
      }
    });
    updateSelection();
  });

  const batchItems = [...document.querySelectorAll('[data-batch-item]')];
  const batchCount = document.querySelector('[data-batch-count]');
  const selectAll = document.querySelector('[data-batch-select-all]');
  if (batchItems.length) {
    const updateBatchCount = () => {
      const count = batchItems.filter(input => input.checked).length;
      if (batchCount) {
        batchCount.textContent = `(${count})`;
        batchCount.hidden = count === 0;
      }
      if (selectAll) selectAll.checked = count === batchItems.length;
    };
    batchItems.forEach(input => input.addEventListener('change', updateBatchCount));
    selectAll?.addEventListener('change', () => {
      batchItems.forEach(input => { input.checked = selectAll.checked; });
      updateBatchCount();
    });
    updateBatchCount();
  }

  const updatePanel = document.querySelector('[data-web-update]');
  if (updatePanel?.dataset.updateActive === 'true') {
    const statusUrl = updatePanel.dataset.updateStatusUrl;
    const message = updatePanel.querySelector('[data-update-message]');
    const target = updatePanel.querySelector('[data-update-target]');
    const progress = updatePanel.querySelector('[data-update-progress]');
    let timer = null;

    const pollUpdate = async () => {
      try {
        const response = await fetch(statusUrl, {credentials: 'same-origin', cache: 'no-store'});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const state = await response.json();
        if (message) message.textContent = state.message || 'Đang cập nhật...';
        if (target) target.textContent = state.target_version ? `Phiên bản phát hành: v${state.target_version}` : '';
        if (progress) {
          progress.hidden = !state.active;
          if (Number.isFinite(state.progress_percent)) progress.value = state.progress_percent;
          else progress.removeAttribute('value');
        }
        if (!state.active) {
          if (timer) window.clearInterval(timer);
          if (state.status === 'complete') window.setTimeout(() => window.location.reload(), 1200);
        }
      } catch (_) {
        if (message) message.textContent = 'Dịch vụ đang khởi động lại; trình duyệt sẽ tự kết nối lại...';
        if (progress) progress.removeAttribute('value');
      }
    };

    timer = window.setInterval(pollUpdate, 2000);
    window.setTimeout(pollUpdate, 500);
  }
})();
