
const root = document.getElementById('app-root');
const dots = document.querySelectorAll('.theme-dot');

function setTheme(theme) {
  if (!root) return;
  root.classList.forEach(cls => {
    if (cls.startsWith('theme-')) root.classList.remove(cls);
  });
  root.classList.add('theme-' + theme);
  dots.forEach(dot => {
    dot.dataset.active = (dot.dataset.theme === String(theme));
  });
  try {
    localStorage.setItem('twe-theme', String(theme));
  } catch (e) {}
}

dots.forEach(dot => {
  dot.addEventListener('click', () => setTheme(dot.dataset.theme));
});

// restore theme on load
try {
  const saved = localStorage.getItem('twe-theme');
  if (saved) setTheme(saved);
} catch (e) {}
