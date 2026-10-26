export function buildThemeRegistry(manifests, styles) {
  const seen = new Set();
  const themes = Object.entries(manifests).map(([file, theme]) => {
    const id = file.split('/').pop().replace(/\.json$/, '');
    if (!theme || theme.id !== id || !/^[a-z0-9][a-z0-9-]*$/.test(id) ||
        typeof theme.name !== 'string' || !theme.name.trim() ||
        !Number.isFinite(theme.order) || seen.has(id)) {
      throw new Error('Invalid theme manifest: ' + file);
    }
    if (!(file.replace(/\.json$/, '.css') in styles)) {
      throw new Error('Theme stylesheet missing: ' + id);
    }
    seen.add(id);
    return { id, name: theme.name, order: theme.order };
  });
  for (const file of Object.keys(styles)) {
    if (!(file.replace(/\.css$/, '.json') in manifests)) {
      throw new Error('Theme manifest missing: ' + file);
    }
  }
  if (!seen.has('default')) throw new Error('Default theme is required');
  const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  return themes.sort((a, b) => Number(b.id === 'default') - Number(a.id === 'default') ||
    a.order - b.order || compare(a.name, b.name) || compare(a.id, b.id));
}
