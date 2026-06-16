(function() {
  try {
    if (localStorage.getItem('velocity_theme_preference') === 'light') {
      document.documentElement.classList.add('light-mode');
    }
  } catch (e) {}
})();
