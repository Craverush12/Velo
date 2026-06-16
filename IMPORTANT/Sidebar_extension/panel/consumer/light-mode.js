(function() {
  const btnToggle = document.getElementById('railThemeToggle');
  if (!btnToggle) return;

  const ICONS = {
    moon: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>',
    sun: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>'
  };

  const isLightMode = () => document.documentElement.classList.contains('light-mode');

  function updateIcon() {
    const iconSpan = btnToggle.querySelector('.rail-theme-icon');
    if (!iconSpan) return;
    iconSpan.innerHTML = isLightMode() ? ICONS.sun : ICONS.moon;
  }

  // Set initial icon state based on the class set by the synchronous head script
  updateIcon();

  btnToggle.addEventListener('click', () => {
    const isLight = document.documentElement.classList.toggle('light-mode');
    try {
      localStorage.setItem('velocity_theme_preference', isLight ? 'light' : 'dark');
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ 'velocity_theme_preference': isLight ? 'light' : 'dark' });
      }
    } catch (e) {
      console.warn('[light-mode] could not save theme to localStorage');
    }
    updateIcon();
  });
})();
