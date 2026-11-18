/* KME Tracker — app.js */

// ─── CSRF helper ───
function getCookie(name) {
  return document.cookie.split('; ').find(r => r.startsWith(name + '='))?.split('=')[1] || '';
}

// ─── Theme: light / dark / auto (matches device), remembered per browser ───
function currentTheme() {
  try { return localStorage.getItem('pt_theme') || 'auto'; } catch (e) { return 'auto'; }
}
function setTheme(choice) {
  const root = document.documentElement;
  if (choice === 'auto') delete root.dataset.theme; else root.dataset.theme = choice;
  try { localStorage.setItem('pt_theme', choice); } catch (e) {}
  document.querySelectorAll('[data-theme-choice]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.themeChoice === choice)));
}
document.addEventListener('DOMContentLoaded', function () {
  setTheme(currentTheme());
  document.querySelectorAll('[data-theme-choice]').forEach(b => b.addEventListener('click', () => setTheme(b.dataset.themeChoice)));
});

// ─── Mobile sidebar menu ───
function toggleMenu(btn) {
  const open = document.getElementById('sidebar').classList.toggle('open');
  btn.setAttribute('aria-expanded', String(open));
  btn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
}

// ─── Auto-dismiss alerts ───
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.alert').forEach(el => {
    if (el.closest('.login-card')) return;
    el.style.transition = 'opacity .3s';
    setTimeout(() => el.style.opacity = '0', 6000);
    setTimeout(() => el.remove(), 6400);
  });
});

// ─── MAC address auto-formatter ───
document.addEventListener('input', function (e) {
  if (e.target.classList.contains('mac-input')) {
    const pos = e.target.selectionStart;
    let val = e.target.value.replace(/[^0-9A-Fa-f]/g, '');
    if (val.length > 12) val = val.slice(0, 12);
    const groups = val.match(/.{1,2}/g) || [];
    e.target.value = groups.join(':').toUpperCase();
  }
});

// ─── Table column drag-to-reorder ───
document.addEventListener('DOMContentLoaded', function () {
  const table = document.getElementById('mainTable');
  if (!table) return;

  let dragSrcIndex = null;

  table.querySelectorAll('th.draggable-col').forEach((th, idx) => {
    th.addEventListener('dragstart', function (e) {
      dragSrcIndex = Array.from(th.parentElement.children).indexOf(th);
      e.dataTransfer.effectAllowed = 'move';
      th.style.opacity = '0.4';
    });
    th.addEventListener('dragend', function () {
      th.style.opacity = '';
      table.querySelectorAll('th').forEach(t => t.classList.remove('drag-over'));
    });
    th.addEventListener('dragover', function (e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      table.querySelectorAll('th').forEach(t => t.classList.remove('drag-over'));
      th.classList.add('drag-over');
    });
    th.addEventListener('drop', function (e) {
      e.preventDefault();
      const destIndex = Array.from(th.parentElement.children).indexOf(th);
      if (dragSrcIndex === null || dragSrcIndex === destIndex) return;

      // Reorder header cells
      const headerRow = th.parentElement;
      const headers = Array.from(headerRow.children);
      const srcTh = headers[dragSrcIndex];
      if (destIndex < dragSrcIndex) {
        headerRow.insertBefore(srcTh, th);
      } else {
        headerRow.insertBefore(srcTh, th.nextSibling);
      }

      // Reorder all body cells accordingly
      table.querySelectorAll('tbody tr').forEach(row => {
        const cells = Array.from(row.children);
        const srcTd = cells[dragSrcIndex];
        const destTd = cells[destIndex];
        if (srcTd && destTd) {
          if (destIndex < dragSrcIndex) {
            row.insertBefore(srcTd, destTd);
          } else {
            row.insertBefore(srcTd, destTd.nextSibling);
          }
        }
      });

      // Persist order to backend
      const colId = srcTh.dataset.colId;
      const newOrder = Array.from(table.querySelectorAll('th.draggable-col')).map((t, i) => ({
        id: parseInt(t.dataset.colId),
        order: i
      }));
      if (colId) {
        fetch('/columns/reorder/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify({ order: newOrder })
        });
      }

      dragSrcIndex = null;
      table.querySelectorAll('th').forEach(t => t.classList.remove('drag-over'));
    });
  });
});

// ─── Sortable table header clicks ───
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', function () {
      const sortKey = th.dataset.sort;
      const url = new URL(window.location);
      const current = url.searchParams.get('sort');
      if (current === sortKey) {
        url.searchParams.set('sort', '-' + sortKey);
      } else if (current === '-' + sortKey) {
        url.searchParams.set('sort', sortKey);
      } else {
        url.searchParams.set('sort', sortKey);
      }
      window.location = url;
    });
  });
});

// ─── Export dropdown close on outside click ───
document.addEventListener('click', function (e) {
  if (!e.target.closest('.dropdown')) {
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
  }
});
