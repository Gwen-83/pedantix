(() => {
  const themeColors = {
    'dark-colorful': '#273238',
    midnight: '#070b14',
    'light-colorful': '#f4e9e8',
    'light-grey': '#e8edf3',
    'dark-grey': '#18181b',
    parchment: '#eae2d3',
  };
  const themes = new Set(Object.keys(themeColors));
  const themeSelect = document.getElementById('shared-theme-select');
  if (!themeSelect) return;

  const theme = localStorage.getItem('pedantix_theme');
  const selectedTheme = themes.has(theme) ? theme : 'dark-colorful';
  function applyTheme(nextTheme) {
    document.documentElement.dataset.theme = nextTheme;
    themeSelect.value = nextTheme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', themeColors[nextTheme]);
  }

  applyTheme(selectedTheme);

  themeSelect.addEventListener('change', () => {
    const nextTheme = themeSelect.value;
    if (!themes.has(nextTheme)) return;
    localStorage.setItem('pedantix_theme', nextTheme);
    applyTheme(nextTheme);
  });
})();
