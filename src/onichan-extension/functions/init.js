// Tab panel ID map — matches the required element IDs popup.js checks for
var TAB_PANEL = {
  bypass:   'bypassSection',
  bins:     'binSection',
  gateways: 'gatewaysSection',
  history:  'history-tab',
  settings: 'settings-tab'
};

// Tab switching
document.querySelectorAll('.tab-btn').forEach(function(btn) {
  btn.addEventListener('click', function() {
    var t = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
    document.querySelectorAll('.t-panel').forEach(function(p) { p.classList.add('hidden'); });
    btn.classList.add('active');
    var panelId = TAB_PANEL[t] || (t + '-tab');
    var panel = document.getElementById(panelId);
    if (panel) { panel.classList.remove('hidden'); panel.classList.add('active'); }
  });
});

// Section collapse/expand
document.querySelectorAll('.sec-hdr[data-toggle]').forEach(function(hdr) {
  hdr.addEventListener('click', function() {
    var body = document.getElementById(hdr.dataset.toggle);
    if (!body) return;
    var open = !body.classList.contains('hidden');
    body.classList.toggle('hidden', open);
    var ch = hdr.querySelector('.chevron');
    if (ch) ch.textContent = open ? '\u25b8' : '\u25be';
  });
});

// Logout button alias
var btn2 = document.getElementById('authLogoutBtn2');
if (btn2) {
  btn2.addEventListener('click', function() {
    var b = document.getElementById('authLogoutBtn');
    if (b) b.click();
  });
}
