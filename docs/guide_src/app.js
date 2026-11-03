(function () {
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role=tab]'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('[role=tabpanel]'));
  function show(slug, focus) {
    tabs.forEach(function (t) {
      var on = t.dataset.tab === slug;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      if (on && focus) t.focus();
    });
    panels.forEach(function (p) { p.hidden = p.id !== 'tab-' + slug; });
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  function route() {
    var h = decodeURIComponent(location.hash.slice(1));
    if (h.indexOf('tab-') === 0) { show(h.slice(4)); return; }
    if (h.indexOf('log-') === 0) {
      show('found');
      var el = document.getElementById(h);
      if (el) { var d = el.querySelector('details'); if (d) d.open = true; el.scrollIntoView(); }
      return;
    }
    show(h && document.getElementById('tab-' + h) ? h : 'start');
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { history.replaceState(null, '', '#tab-' + t.dataset.tab); show(t.dataset.tab); });
    t.addEventListener('keydown', function (e) {
      var j = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : -1;
      if (j < 0) return;
      e.preventDefault();
      var n = tabs[(j + tabs.length) % tabs.length];
      history.replaceState(null, '', '#tab-' + n.dataset.tab);
      show(n.dataset.tab, true);
    });
  });
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (a) { setTimeout(route, 0); }
  });
  function setAll(open) {
    var p = document.querySelector('[role=tabpanel]:not([hidden])');
    if (p) p.querySelectorAll('details').forEach(function (d) { d.open = open; });
  }
  document.getElementById('expand').addEventListener('click', function () { setAll(true); });
  document.getElementById('collapse').addEventListener('click', function () { setAll(false); });
  window.addEventListener('hashchange', route);
  route();
})();
