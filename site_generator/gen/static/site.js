// Shared behaviour: external links open in a new tab; prefilled GitHub issue URLs (B4).
document.addEventListener('DOMContentLoaded', () => {
  for (const a of document.querySelectorAll('a[href^="http"]')) { a.target = '_blank'; a.rel = 'noopener'; }
});
// Build a GitHub issue-form URL. Keys must equal the field ids of .github/ISSUE_TEMPLATE/catalog-finding.yml.
window.catalogIssueUrl = function (fields) {
  const C = window.CATALOG || {issueRepo: 'https://github.com/OlmLab/infant-gut-catalog/issues/new', issueTemplate: 'catalog-finding.yml', release: ''};
  const p = [['template', C.issueTemplate], ['labels', 'finding']];
  if (fields.title) p.push(['title', String(fields.title).slice(0, 200)]);
  for (const k of Object.keys(fields).sort()) {
    if (k === 'title') continue;
    let v = fields[k]; if (v === null || v === undefined || v === '') continue;
    v = String(v); if (k === 'current_state') v = v.slice(0, 2500);
    p.push([k, v]);
  }
  const url = C.issueRepo + '?' + p.map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');
  return url.slice(0, 6000);
};
