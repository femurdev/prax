(function () {
  const views = {
    login: document.getElementById('view-login'),
    menu: document.getElementById('view-menu'),
    game: document.getElementById('view-game'),
  };
  const navUser = document.getElementById('nav-user');
  const btnLogout = document.getElementById('btn-logout');
  const btnBackToMenu = document.getElementById('btn-back-to-menu');

  function showView(id) {
    Object.values(views).forEach((v) => v.classList.add('d-none'));
    const v = views[id];
    if (v) v.classList.remove('d-none');
    if (id === 'menu' || id === 'game') {
      navUser.classList.remove('d-none');
      btnLogout.classList.remove('d-none');
      if (id === 'game' && window.praxGame) window.praxGame.start();
    } else {
      navUser.classList.add('d-none');
      btnLogout.classList.add('d-none');
      if (window.praxGame) window.praxGame.stop();
    }
  }

  async function checkAuth() {
    try {
      const res = await fetch('/me', { credentials: 'include' });
      const data = await res.json();
      if (data.authenticated && data.user) {
        window.__praxUser = data.user;
        navUser.textContent = data.user.global_name || data.user.username || 'User';
        showView('menu');
        return;
      }
    } catch (_) {}
    showView('login');
  }

  btnLogout.addEventListener('click', async () => {
    try {
      await fetch('/logout', { method: 'POST', credentials: 'include' });
    } catch (_) {}
    showView('login');
  });

  btnBackToMenu.addEventListener('click', () => {
    if (window.praxGame) window.praxGame.stop();
    showView('menu');
  });

  const gameModeBadge = document.getElementById('game-mode-badge');
  function setGameMode(mode) {
    const labels = { 'join-public': 'Public', 'create-private': 'Private', 'local': 'Local' };
    gameModeBadge.textContent = labels[mode] || mode;
  }

  document.querySelectorAll('[data-action]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.action;
      if (action === 'join-public' || action === 'create-private' || action === 'local') {
        setGameMode(action);
        showView('game');
      }
    });
  });

  // Collapsible Inspector and Docs panels
  document.querySelectorAll('.game-collapse-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const panel = document.getElementById('panel-' + btn.dataset.panel);
      if (!panel) return;
      const expanded = panel.classList.toggle('collapsed');
      btn.setAttribute('aria-expanded', !expanded);
    });
  });

  checkAuth();
})();
