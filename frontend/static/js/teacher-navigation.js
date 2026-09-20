(() => {
    const sidebar = document.getElementById('teacher-sidebar');
    const main = document.querySelector('body > main');
    if (!sidebar || !main) return;
    let header = main.querySelector(':scope > header');
    if (!header) { header = document.createElement('header'); main.prepend(header); }
    const toggle = document.createElement('button');
    toggle.type = 'button'; toggle.className = 'teacher-menu-toggle';
    toggle.setAttribute('aria-label', 'Mở menu giáo viên');
    toggle.setAttribute('aria-controls', 'teacher-sidebar');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = '<i class="ph-bold ph-list" aria-hidden="true"></i>';
    header.prepend(toggle);
    const overlay = document.createElement('div');
    overlay.className = 'teacher-menu-overlay'; overlay.hidden = true;
    document.body.append(overlay);
    const desktop = window.matchMedia('(min-width:1024px)');
    let open = false;
    function setOpen(value, focus = true) {
        open = value && !desktop.matches;
        sidebar.classList.toggle('is-open', open);
        overlay.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
        sidebar.inert = !desktop.matches && !open;
        main.inert = open;
        if (focus) { if (open) sidebar.querySelector('.teacher-menu-close').focus(); else if (!desktop.matches) toggle.focus(); }
    }
    toggle.addEventListener('click', () => setOpen(!open));
    sidebar.querySelector('.teacher-menu-close').addEventListener('click', () => setOpen(false));
    overlay.addEventListener('click', () => setOpen(false));
    sidebar.querySelectorAll('nav a').forEach(link => {
        const active = new URL(link.href).pathname === location.pathname;
        link.classList.toggle('active', active);
        if (active) link.setAttribute('aria-current', 'page');
        link.addEventListener('click', () => setOpen(false, false));
    });
    document.addEventListener('keydown', event => {
        if (!open) return;
        if (event.key === 'Escape') { event.preventDefault(); setOpen(false); }
        if (event.key === 'Tab') {
            const items = [...sidebar.querySelectorAll('a[href],button')].filter(el => el.getClientRects().length && !el.disabled);
            const first = items[0], last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
    });
    desktop.addEventListener('change', () => setOpen(false, false));
    setOpen(false, false);
})();
