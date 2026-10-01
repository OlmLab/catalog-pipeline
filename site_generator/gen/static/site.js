// Shared behaviour: external links open in a new tab; prefilled GitHub issue URLs (B4).
document.addEventListener('DOMContentLoaded', () => {
  for (const a of document.querySelectorAll('a[href^="http"]')) { a.target = '_blank'; a.rel = 'noopener'; }
});
// Build a GitHub issue-form URL. Keys must equal the field ids of the installed issue form (config/site.yaml github.issues.template;
// site_generator/gen/issue_templates/simple-finding.yml: accession, release_id, page_url, problem, details).
window.catalogIssueUrl = function (fields) {
  const C = window.CATALOG || {issueRepo: 'https://github.com/OlmLab/microbiome_repo/issues/new', issueTemplate: 'simple-finding.yml', issueLabel: 'finding', release: ''};
  const p = [['template', C.issueTemplate], ['labels', C.issueLabel || 'finding']];
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

// R2026.15 drop-down navigation: click / tap toggles a menu (hover and keyboard focus are handled in CSS); Escape or an outside click closes it
(function(){
  const dds=[...document.querySelectorAll('.topnav .navdd')];
  const closeAll=(except)=>dds.forEach(d=>{if(d!==except){d.classList.remove('open');const b=d.querySelector('.navbtn');if(b)b.setAttribute('aria-expanded','false');}});
  dds.forEach(d=>{const b=d.querySelector('.navbtn'); if(!b) return;
    b.addEventListener('click',e=>{e.stopPropagation();const o=!d.classList.contains('open');closeAll(d);d.classList.toggle('open',o);b.setAttribute('aria-expanded',o?'true':'false');});});
  document.addEventListener('click',()=>closeAll(null));
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeAll(null);});
})();
