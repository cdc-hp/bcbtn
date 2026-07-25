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
})();
