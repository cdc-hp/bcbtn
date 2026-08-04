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

  const dedupTable = document.querySelector('[data-dedup-table]');
  if (dedupTable) {
    const rowChecks = [...dedupTable.querySelectorAll('[data-dedup-row-check]')];
    const selectAll = dedupTable.querySelector('[data-dedup-select-all]');
    const keepSelect = document.querySelector('[data-dedup-keep]');
    const countEl = document.querySelector('[data-dedup-selected-count]');
    const sync = () => {
      const checkedIds = new Set(rowChecks.filter(input => input.checked).map(input => input.value));
      if (countEl) countEl.textContent = `Đã chọn ${checkedIds.size}/${rowChecks.length} bản ghi`;
      if (selectAll) selectAll.checked = checkedIds.size === rowChecks.length;
      if (keepSelect) {
        [...keepSelect.options].forEach(option => { option.disabled = !checkedIds.has(option.value); });
        if (keepSelect.selectedOptions[0]?.disabled) {
          const firstEnabled = [...keepSelect.options].find(option => !option.disabled);
          if (firstEnabled) keepSelect.value = firstEnabled.value;
        }
      }
    };
    rowChecks.forEach(input => input.addEventListener('change', sync));
    selectAll?.addEventListener('change', () => {
      rowChecks.forEach(input => { input.checked = selectAll.checked; });
      sync();
    });
    sync();
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

  // Kéo dãn độ rộng cột — áp dụng chung cho MỌI bảng trong .table-responsive, không cần gắn
  // class riêng ở từng template. Tay cầm là 1 dải hẹp sát mép phải mỗi <th> (trừ ô cuối) để
  // không đè lên link sắp xếp (.cdc-sort-link) đã lấp đầy <th> ở các trang có sort.
  const RESIZE_STORAGE_PREFIX = 'cdc_col_width::';
  document.querySelectorAll('.table-responsive table').forEach(table => {
    const headerCells = [...table.querySelectorAll('thead th')];
    headerCells.forEach((th, index) => {
      if (index === headerCells.length - 1) return; // ô cuối (hành động) không cần kéo dãn
      const columnKey = th.dataset.columnKey || th.textContent.trim() || `col-${index}`;
      const storageKey = RESIZE_STORAGE_PREFIX + window.location.pathname + '::' + columnKey;
      const savedWidth = window.localStorage.getItem(storageKey);
      if (savedWidth) th.style.width = savedWidth;

      const handle = document.createElement('span');
      handle.className = 'cdc-col-resize';
      handle.setAttribute('aria-hidden', 'true');
      th.appendChild(handle);

      let startX = 0, startWidth = 0;
      const onMouseMove = event => {
        const delta = event.clientX - startX;
        th.style.width = `${Math.max(60, startWidth + delta)}px`;
      };
      const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        handle.classList.remove('cdc-col-resize--active');
        try { window.localStorage.setItem(storageKey, th.style.width); } catch (_) {}
      };
      handle.addEventListener('mousedown', event => {
        event.preventDefault();
        event.stopPropagation();
        startX = event.clientX;
        startWidth = th.getBoundingClientRect().width;
        handle.classList.add('cdc-col-resize--active');
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    });
  });
})();
