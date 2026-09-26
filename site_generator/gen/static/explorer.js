// Sample explorer v2: DuckDB-WASM over sample_metadata_wide.parquet, fully client-side.
// Features: README-rule toggle (B13) applied to results AND exports; exact accession match before LIKE (B15);
// age_scope / Sandpiper filters; detail panel with evidence, value history (B3), top-genera bars (A6) and Flag/Confirm (B4).
const DUCKDB_URL = 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm'; // F5: imported dynamically inside init()'s try so a blocked CDN reaches the failure message

const CFG = window.EXPLORER_CFG;
const FIELDS = CFG.fields; // metadata fields having __confidence/__route companions
const PAGE = 100;
const SHOW_COLS = ['sample_key','sample_unit','biosample_accession','run_accession','study_accession','age_scope','role','age_at_collection_days','delivery_mode','feeding_mode','preterm_status','antibiotic_exposure','sex','country','subject_key','t_index','n_runs','sp_top_genus','sp_ra_g_Bifidobacterium'];
const INT_COLS = new Set(['n_runs','t_index','age_at_collection_days','n_timepoints_subject','read_count_total','sp_n_runs_total','sp_n_runs_profiled','sp_n_genera_ge1pct']);
const PCT_COLS = new Set(['sp_ra_g_Bifidobacterium']);
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/'/g, "''");
const h = s => String(s === null || s === undefined ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmtV = (v, c) => {
  if (v === null || v === undefined) return '';
  if (typeof v === 'bigint') return v.toString();
  if (typeof v === 'number') { if (INT_COLS.has(c)) return String(Math.round(v)); if (PCT_COLS.has(c)) return (100*v).toFixed(1) + '%'; return Number.isInteger(v) ? String(v) : (Math.round(v*1000)/1000).toString(); }
  return String(v);
};
const TAXON_COLORS = ['#CFB87C','#565A5C','#A88B4A','#8C8F91','#7A6A3C','#3C3C3C','#8A7A48','#7F7060','#6E6A5E','#8F7418','#6F6D62','#6B6F73','#7D7461','#4A4A4A','#75604A','#5F6366']; // F11: identical to build_site.py TAXON_PALETTE

let duckdb, db, conn, detReady = false, vhReady = false, tgReady = false, page = 0, total = 0, sortCol = 'sample_key', sortDir = 'ASC';

function setBoot(msg){ $('boot-msg').textContent = msg; }
function ruleOn(){ return $('f-rule').checked; }
function table(){ return ruleOn() ? 'samples_rule' : 'samples'; }

function bootFail(e){
  $('boot').innerHTML = '<b>The explorer could not start.</b> ' + h(e && e.message || e) + '<br>DuckDB-WASM (pinned 1.29.0) is loaded from cdn.jsdelivr.net; this message means the browser blocks WebAssembly/Workers or the CDN is unreachable on your network. Everything the explorer shows is also downloadable: <a href="' + CFG.parquet + '">sample_metadata_wide.parquet</a> · <a href="' + CFG.csvgz + '">sample_metadata_wide.csv.gz</a> · <a href="' + CFG.det + '">sample_determinations.parquet</a> · per-study CSVs on each study page.';
  console.error(e);
}
window.__explorerBootFail = bootFail;

async function init(){
  try {
    setBoot('loading DuckDB-WASM module…');
    duckdb = await import(DUCKDB_URL);
    setBoot('selecting bundle…');
    const bundles = duckdb.getJsDelivrBundles();
    const bundle = await duckdb.selectBundle(bundles);
    const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], {type:'text/javascript'}));
    const worker = new Worker(workerUrl);
    db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), worker);
    await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
    URL.revokeObjectURL(workerUrl);
    setBoot('fetching sample table…');
    const resp = await fetch(CFG.parquet);
    if(!resp.ok) throw new Error('fetch of parquet failed: HTTP '+resp.status);
    const buf = new Uint8Array(await resp.arrayBuffer());
    await db.registerFileBuffer('samples.parquet', buf);
    conn = await db.connect();
    await conn.query(`CREATE VIEW samples AS SELECT * FROM read_parquet('samples.parquet')`);
    // README rule view: R3/R4 values with confidence < 0.5 are masked (value -> NULL); __route/__confidence kept so exports show what was hidden
    const cols = (await conn.query(`SELECT column_name FROM information_schema.columns WHERE table_name='samples' ORDER BY ordinal_position`)).toArray().map(r => r.toJSON().column_name);
    const sel = cols.map(c => {
      if (FIELDS.includes(c) && cols.includes(c+'__route') && cols.includes(c+'__confidence'))
        return `CASE WHEN "${c}__route" IN ('R3','R4') AND COALESCE("${c}__confidence",0) < 0.5 THEN NULL ELSE "${c}" END AS "${c}"`;
      return `"${c}"`; });
    await conn.query(`CREATE VIEW samples_rule AS SELECT ${sel.join(',')} FROM samples`);
    window.__explorerReady = true;
    $('boot').style.display = 'none'; $('exp').style.display = '';
    readUrl();
    await run();
    const sk = new URLSearchParams(location.search).get('sample');
    if (sk) showDetail(sk);
  } catch (e) {
    bootFail(e);
  }
}

function selectedStudies(){ return [...$('f-study').selectedOptions].map(o => o.value); }
function routes(){ return [...document.querySelectorAll('.rt:checked')].map(c => c.value); }

function whereClause(){
  const w = [];
  const conf = parseFloat($('f-conf').value); const rts = routes();
  const guard = f => { if (!isNaN(conf)) w.push(`"${f}__confidence" >= ${conf}`);
    if (rts.length < 4) w.push(rts.length ? `"${f}__route" IN (${rts.map(r=>`'${r}'`).join(',')})` : `FALSE`); };
  const q = $('f-q').value.trim().toUpperCase();
  if (q) w.push(`(sample_key = '${esc(q)}' OR biosample_accession = '${esc(q)}' OR run_accession = '${esc(q)}' OR secondary_sample = '${esc(q)}' OR run_accessions LIKE '%${esc(q)}%')`);
  const st = selectedStudies(); if (st.length) w.push(`study_accession IN (${st.map(s=>`'${esc(s)}'`).join(',')})`);
  if ($('f-cohort').value) w.push(`cohort_id = '${esc($('f-cohort').value)}'`);
  for (const sel of document.querySelectorAll('select[data-field]')){
    const f = sel.dataset.field, v = sel.value; if (!v) continue;
    if (v === '__has__') w.push(`"${f}" IS NOT NULL`);
    else if (v === '__infant__') w.push(`age_scope IN ('infant_evidenced','study_all_infant')`);
    else w.push(`"${f}" = '${esc(v)}'`);
    if (FIELDS.includes(f)) guard(f);
  }
  const amin = $('f-age_min').value, amax = $('f-age_max').value;
  if (amin !== '') w.push(`age_at_collection_days >= ${parseFloat(amin)}`);
  if (amax !== '') w.push(`age_at_collection_days <= ${parseFloat(amax)}`);
  if ($('f-has_age').checked) w.push(`age_at_collection_days IS NOT NULL`);
  if (amin !== '' || amax !== '' || $('f-has_age').checked) guard('age_at_collection_days');
  if ($('f-no_adult').checked) w.push(`(adult_age_flag IS NULL OR adult_age_flag = FALSE)`);
  if ($('f-sp').checked) w.push(`sp_profiled = TRUE`);
  const bif = parseInt($('f-bifido').value || '0'); if (bif > 0) w.push(`sp_ra_g_Bifidobacterium >= ${bif/100}`);
  return w.length ? 'WHERE ' + w.join(' AND ') : '';
}

function writeUrl(){
  const p = new URLSearchParams();
  if ($('f-q').value.trim()) p.set('q', $('f-q').value.trim());
  const st = selectedStudies(); if (st.length) p.set('study', st.join(','));
  if ($('f-cohort').value) p.set('cohort', $('f-cohort').value);
  for (const sel of document.querySelectorAll('select[data-field]')) if (sel.value) p.set(sel.dataset.field, sel.value);
  if ($('f-age_min').value !== '') p.set('age_min', $('f-age_min').value);
  if ($('f-age_max').value !== '') p.set('age_max', $('f-age_max').value);
  if ($('f-has_age').checked) p.set('has_age', '1');
  if ($('f-no_adult').checked) p.set('no_adult', '1');
  if ($('f-sp').checked) p.set('sp', '1');
  if (parseInt($('f-bifido').value || '0') > 0) p.set('bifido', $('f-bifido').value);
  if (!ruleOn()) p.set('rule', '0');
  if ($('f-conf').value !== '') p.set('conf', $('f-conf').value);
  const r = routes(); if (r.length < 4) p.set('routes', r.join(','));
  if (page) p.set('page', page+1);
  if (sortCol !== 'sample_key' || sortDir !== 'ASC') p.set('sort', sortCol + ':' + sortDir);
  const keep = new URLSearchParams(location.search).get('sample'); if (keep && $('detail').classList.contains('open')) p.set('sample', keep);
  history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p.toString() : ''));
}

function readUrl(){
  const p = new URLSearchParams(location.search);
  if (p.get('q')) $('f-q').value = p.get('q');
  if (p.get('study')) { const set = new Set(p.get('study').split(',')); for (const o of $('f-study').options) o.selected = set.has(o.value); }
  if (p.get('cohort')) $('f-cohort').value = p.get('cohort');
  for (const sel of document.querySelectorAll('select[data-field]')) { const v = p.get(sel.dataset.field); if (v) sel.value = v; }
  if (p.get('age_min')) $('f-age_min').value = p.get('age_min');
  if (p.get('age_max')) $('f-age_max').value = p.get('age_max');
  if (p.get('has_age')) $('f-has_age').checked = true;
  if (p.get('no_adult')) $('f-no_adult').checked = true;
  if (p.get('sp')) $('f-sp').checked = true;
  if (p.get('bifido')) { $('f-bifido').value = p.get('bifido'); $('f-bifido-val').textContent = p.get('bifido'); }
  if (p.get('rule') === '0') $('f-rule').checked = false;
  if (p.get('conf')) $('f-conf').value = p.get('conf');
  if (p.get('routes')) { const set = new Set(p.get('routes').split(',')); for (const c of document.querySelectorAll('.rt')) c.checked = set.has(c.value); }
  if (p.get('page')) page = Math.max(0, parseInt(p.get('page')) - 1);
  if (p.get('sort')) { const [c,d] = p.get('sort').split(':'); if (SHOW_COLS.includes(c)) { sortCol = c; sortDir = d === 'DESC' ? 'DESC' : 'ASC'; } }
}

async function run(){
  const where = whereClause(), T = table();
  $('count').textContent = 'counting…';
  const c = await conn.query(`SELECT COUNT(*) AS n FROM ${T} ${where}`);
  total = Number(c.toArray()[0].n);
  const maxPage = Math.max(0, Math.ceil(total / PAGE) - 1); if (page > maxPage) page = maxPage;
  const r = await conn.query(`SELECT ${SHOW_COLS.map(c=>`"${c}"`).join(',')} FROM ${T} ${where} ORDER BY "${sortCol}" ${sortDir} NULLS LAST, sample_key LIMIT ${PAGE} OFFSET ${page*PAGE}`);
  const rows = r.toArray().map(x => x.toJSON());
  const thead = $('result-table').querySelector('thead'), tbody = $('result-table').querySelector('tbody');
  thead.innerHTML = '<tr>' + SHOW_COLS.map(c => `<th data-col="${c}" tabindex="0" role="columnheader button" aria-sort="${c===sortCol ? (sortDir==='ASC'?'ascending':'descending') : 'none'}" title="sort by ${c} (Enter or Space)" style="cursor:pointer">${c}${c===sortCol ? (sortDir==='ASC'?' ▲':' ▼') : ''}</th>`).join('') + '</tr>';
  tbody.innerHTML = rows.map(row => `<tr data-key="${h(row.sample_key)}" tabindex="0" role="button" aria-label="open details for ${h(row.sample_key)}">` + SHOW_COLS.map(c => {
    let v = fmtV(row[c], c);
    if (c === 'study_accession' && v) v = `<a href="${CFG.studiesUrl}${h(v)}.html">${h(v)}</a>`;
    else if (c === 'sample_unit') v = v === 'run' ? '<span class="tag">ENA run</span>' : h(v);
    else if (c === 'sp_top_genus') v = v ? '<i>' + h(v.replace(/^g__/, '')) + '</i>' : '';
    else v = h(v);
    return `<td title="${h(fmtV(row[c], c))}">${v}</td>`; }).join('') + '</tr>').join('');
  $('count').textContent = total.toLocaleString() + ' samples match' + (ruleOn() ? ' · README rule on' : ' · README rule OFF (R3/R4 < 0.5 shown)');
  $('pageinfo').textContent = total ? `page ${page+1} / ${maxPage+1}` : '';
  $('prev').disabled = page <= 0; $('next').disabled = page >= maxPage;
  writeUrl();
}

async function download(kind){
  const where = whereClause(), T = table();
  const fname = kind === 'csv' ? 'samples_slice.csv' : 'samples_slice.parquet';
  $('dl-status').textContent = `preparing ${fname} (${total.toLocaleString()} rows, README rule ${ruleOn() ? 'applied' : 'off'})…`;
  try {
    const opts = kind === 'csv' ? `(HEADER, DELIMITER ',')` : `(FORMAT PARQUET)`;
    await conn.query(`COPY (SELECT * FROM ${T} ${where} ORDER BY study_accession, sample_key) TO '${fname}' ${opts}`);
    const buf = await db.copyFileToBuffer(fname);
    await db.dropFile(fname);
    const blob = new Blob([buf], {type: kind === 'csv' ? 'text/csv' : 'application/octet-stream'});
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = fname; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    $('dl-status').textContent = `${fname}: ${(buf.length/1e6).toFixed(1)} MB`;
  } catch (e) { $('dl-status').textContent = 'download failed: ' + (e.message || e); console.error(e); }
}

async function ensureFile(url, name, view){
  const resp = await fetch(url); if (!resp.ok) throw new Error('HTTP ' + resp.status + ' for ' + url);
  await db.registerFileBuffer(name, new Uint8Array(await resp.arrayBuffer()));
  await conn.query(`CREATE VIEW ${view} AS SELECT * FROM read_parquet('${name}')`);
}
async function ensureDet(){ if (!detReady) { await ensureFile(CFG.det, 'det.parquet', 'det'); detReady = true; } }
async function ensureVh(){ if (!vhReady) { await ensureFile(CFG.vh, 'vh.parquet', 'vh'); vhReady = true; } }
async function ensureTg(){ if (!tgReady) { await ensureFile(CFG.topgen, 'tg.parquet', 'tg'); tgReady = true; } }

function issueBtns(s, f, ev){
  const C = window.CATALOG, page = `${C.release} · samples/index.html?sample=${s.sample_key}`;
  const cur = f ? `${f} = ${fmtV(s[f], f)} · route ${s[f+'__route']} · scope ${s[f+'__scope'] || ''} · confidence ${s[f+'__confidence']}` + (ev ? ` · quote “${ev.evidence_quote}” (${ev.evidence_source} ${ev.evidence_locator || ''})` : '')
                : `sample ${s.sample_key} · study ${s.study_accession} · unit ${s.sample_unit} · role ${s.role} · age_scope ${s.age_scope}`;
  const base = {identifier: s.sample_key, sample_key: s.sample_key, field_name: f || '', current_state: cur, evidence_source: 'external_curation.human', release_tag: page};
  const flag = window.catalogIssueUrl({...base, title: `[finding] ${s.sample_key}: ${f || 'sample'}`, finding_type: 'value_error', action: f ? 'supersede_determination' : 'note_only'});
  const ok = window.catalogIssueUrl({...base, title: `[confirmed] ${s.sample_key}: ${f || 'sample'}`, finding_type: 'confirmed_correct', action: 'confirm', proposed_change: 'none — confirmed correct'});
  return `<a class="btn flag xs" href="${h(flag)}" target="_blank" rel="noopener">Flag</a> <a class="btn confirm xs" href="${h(ok)}" target="_blank" rel="noopener">Confirm</a>`;
}

async function showDetail(key){
  const box = $('detail'), body = $('detail-body');
  if (!box.classList.contains('open')) lastFocus = document.activeElement;
  box.classList.add('open'); body.innerHTML = '<p class="status">loading…</p>';
  box.focus(); // F12: focus moves into the panel; Escape or the close button returns it
  let r = await conn.query(`SELECT * FROM samples WHERE sample_key = '${esc(key)}'`);
  let rows = r.toArray();
  if (!rows.length) { // F8: a run accession is a sample_key only for run-unit rows; fall back to the run columns and open the first hit
    r = await conn.query(`SELECT * FROM samples WHERE run_accession = '${esc(key)}' OR run_accessions LIKE '%${esc(key)}%' OR biosample_accession = '${esc(key)}' OR secondary_sample = '${esc(key)}' ORDER BY sample_key LIMIT 1`);
    rows = r.toArray();
  }
  if (!rows.length) { body.innerHTML = `<p>No sample, BioSample or run <b>${h(key)}</b> in the catalog.</p>`; box.focus(); return; }
  const s = rows[0].toJSON();
  if (s.sample_key !== key) body.dataset.resolvedFrom = key;
  key = s.sample_key;
  const p = new URLSearchParams(location.search); p.set('sample', key); history.replaceState(null, '', location.pathname + '?' + p.toString());
  const runs = (s.run_accessions || '').split(';').filter(Boolean);
  const isRun = s.sample_unit === 'run';
  let html = `<h2 style="margin-top:0">${h(s.sample_key)} ${isRun ? '<span class="tag">ENA run</span>' : ''}</h2>
  <p class="small"><a href="${h(s.ena_sample_url)}">${isRun ? 'ENA run' : 'ENA sample'}</a>${s.sandpiper_url ? ` · <a href="${h(s.sandpiper_url)}">Sandpiper</a>` : ''} · study <a href="${CFG.studiesUrl}${h(s.study_accession)}.html">${h(s.study_accession)}</a> (<a href="${h(s.ena_study_url)}">ENA</a>)${s.cohort_id ? ` · cohort <a href="${CFG.cohortsUrl}${h(s.cohort_id)}.html">${h(s.cohort_name)}</a>` : ''}</p>
  <p>${issueBtns(s, null, null)} <span class="small">for the sample as a whole; per-value buttons below.</span></p>
  <table class="tbl kv">
  <tr><td>Sample title</td><td>${h(s.sample_title)}</td></tr>
  <tr><td>BioSample / run</td><td class="mono">${h(s.biosample_accession)}${s.run_accession ? ' / ' + h(s.run_accession) : ''}${s.parent_biosample ? ' (parent BioSample <a href="https://www.ebi.ac.uk/ena/browser/view/'+h(s.parent_biosample)+'">'+h(s.parent_biosample)+'</a>)' : ''}</td></tr>
  <tr><td>Secondary accession</td><td>${h(s.secondary_sample)}</td></tr>
  <tr><td>Age scope / role</td><td>${h(s.age_scope)} <span class="small">(${h(s.age_scope_basis)})</span> / ${h(s.role)} <span class="small">(${h(s.role_source)})</span>${s.adult_age_flag ? ' <span class="tag">adult_age_flag</span>' : ''}${s.is_gold_heldout ? ' <span class="tag">gold held-out</span>' : ''}</td></tr>
  <tr><td>Body-site class</td><td>${h(s.body_site_class)}</td></tr>
  <tr><td>Subject / timepoint</td><td>${h(s.subject_key)} ${s.t_index != null ? `· t=${fmtV(s.t_index,'t_index')} of ${fmtV(s.n_timepoints_subject,'n_timepoints_subject')}` : ''}${s.linked_infant_subject_key ? ` · linked infant ${h(s.linked_infant_subject_key)}` : ''}</td></tr>
  <tr><td>Collection date (archive)</td><td>${h(s.collection_date)}</td></tr>
  <tr><td>Runs (${runs.length})</td><td>${runs.slice(0,40).map(x => `<a href="https://www.ebi.ac.uk/ena/browser/view/${h(x)}">${h(x)}</a> <a class="small" href="https://sandpiper.qut.edu.au/run/${h(x)}" title="Sandpiper run page">[sp]</a>`).join(', ')}${runs.length>40 ? ` … +${runs.length-40}` : ''}</td></tr>
  <tr><td>Instrument / layout / reads</td><td>${h(s.instrument_model)} / ${h(s.library_layout)} / ${fmtV(s.read_count_total,'read_count_total')}</td></tr>
  </table>
  <h3>Metadata fields</h3><p class="small">Confidence is an engine tier, not a probability. Scope <b>group</b> = R3/R4 statement applied to a defined group; the README rule hides those below 0.5${ruleOn() ? ' (on)' : ' (off)'} — masked values are marked.</p><table class="tbl"><thead><tr><th>field</th><th>value</th><th>tier</th><th>route / scope</th><th></th></tr></thead><tbody>`;
  for (const f of FIELDS) {
    const v = s[f]; if (v === null || v === undefined) continue;
    const masked = ruleOn() && ['R3','R4'].includes(s[f+'__route']) && (s[f+'__confidence'] ?? 0) < 0.5;
    html += `<tr${masked ? ' class="masked"' : ''}><td class="mono"><a href="${CFG.fieldsUrl}#${f}">${f}</a></td><td>${h(fmtV(v, f))}${masked ? ' <span class="tag">hidden by README rule</span>' : ''}</td><td class="conf">${fmtV(s[f+'__confidence'])}</td><td><span class="tag ${h(s[f+'__route'])}">${h(s[f+'__route'])}</span> ${h(s[f+'__scope'] || '')}</td><td id="btn-${f}"></td></tr>`;
  }
  html += `</tbody></table>
  <h3>Community profile (Sandpiper/SingleM, ${h(s.taxonomy_db || 'GTDB')} ${h(s.taxonomy_version || '')})</h3><div id="taxo" class="status">${s.sp_profiled ? 'loading top genera…' : 'not profiled in Sandpiper'}</div>
  <h3>Evidence</h3><div id="evidence" class="status">loading determinations…</div>
  <h3>Value history</h3><div id="history" class="status">loading…</div>`;
  body.innerHTML = html;
  for (const f of FIELDS) { const cell = $('btn-'+f); if (cell) cell.innerHTML = issueBtns(s, f, null); }
  if (s.sp_profiled) {
    try {
      await ensureTg();
      const t = await conn.query(`SELECT taxon, rel_abundance FROM tg WHERE sample_key = '${esc(key)}' ORDER BY rel_abundance DESC, taxon`);
      const tx = t.toArray().map(x => x.toJSON());
      const low = s.sp_low_depth;
      let bars = `<p class="small">Fraction of prokaryotic coverage (root ${fmtV(s.sp_root_coverage)}×${s.sp_n_runs_profiled > 1 ? `, ${s.sp_n_runs_profiled} runs summed` : ''}; prokaryotic read fraction ${fmtV(s.sp_spf)}%, known-species fraction ${fmtV(s.sp_known_species_fraction)}%${s.sp_flag_low_complexity ? '; low-complexity flag (expected in neonatal stool)' : ''}${s.sp_partial ? '; some runs unprofiled' : ''}${s.sp_runs_discordant ? '; runs discordant (BC > 0.5)' : ''}).${low ? ' <b>Low depth (root &lt; 2×): bars hidden.</b>' : ''}</p>`;
      if (!low) {
        let ci = 0;
        bars += '<div class="hbars">' + tx.map(x => { const un = x.taxon.startsWith('unassigned'); const col = un ? '#D9D9D9' : TAXON_COLORS[(ci++) % TAXON_COLORS.length];
          return `<div class="hbar"><span class="lbl">${un ? h(x.taxon) : '<i>'+h(x.taxon.replace(/^g__/,''))+'</i>'}</span><span class="trk"><span style="width:${Math.min(100, 100*x.rel_abundance).toFixed(1)}%;background:${col}"></span></span><span class="val">${(100*x.rel_abundance).toFixed(1)}%</span></div>`; }).join('') + '</div>';
      }
      $('taxo').className = ''; $('taxo').innerHTML = bars;
    } catch (e) { $('taxo').textContent = 'could not load top genera: ' + (e.message || e); }
  }
  try {
    await ensureDet();
    const d = await conn.query(`SELECT field_name, value_normalized, field_value, confidence, route, scope, evidence_source, evidence_locator, evidence_quote, parse_note, determined_by FROM det WHERE sample_key = '${esc(key)}' ORDER BY field_name`);
    const ev = d.toArray().map(x => x.toJSON());
    for (const e of ev) { const cell = $('btn-'+e.field_name); if (cell) cell.innerHTML = issueBtns(s, e.field_name, e); }
    $('evidence').className = '';
    $('evidence').innerHTML = ev.length ? '<table class="tbl"><thead><tr><th>field</th><th>value (raw)</th><th>route/scope</th><th>source · locator</th><th>quote</th></tr></thead><tbody>' +
      ev.map(e => `<tr><td class="mono">${h(e.field_name)}</td><td>${h(fmtV(e.value_normalized))}<br><span class="small">${h(fmtV(e.field_value))}</span></td><td><span class="tag ${h(e.route)}">${h(e.route)}</span> ${h(e.scope)}${e.scope === 'group' ? ' <span class="tag" title="group statement applied to samples">group statement</span>' : ''}<br><span class="conf">${fmtV(e.confidence)}</span></td><td class="small">${h(e.evidence_source)}<br>${h(e.evidence_locator)}${e.parse_note ? '<br><i>'+h(e.parse_note)+'</i>' : ''}</td><td class="quote">“${h(e.evidence_quote)}”</td></tr>`).join('') + '</tbody></table>'
      : '<p class="small">No determinations recorded for this sample.</p>';
  } catch (e) { $('evidence').textContent = 'could not load evidence: ' + (e.message || e); }
  try {
    await ensureVh();
    const d = await conn.query(`SELECT field_name, value_normalized, route, scope, confidence, status, reason, replaced_by, change_stage, evidence_source, evidence_quote, date FROM vh WHERE sample_key = '${esc(key)}' ORDER BY field_name, status`);
    const hv = d.toArray().map(x => x.toJSON());
    $('history').className = '';
    $('history').innerHTML = hv.length ? '<p class="small">Values that were once determined for this sample and are no longer current (from value_history.parquet).</p><table class="tbl small"><thead><tr><th>field</th><th>value</th><th>route/scope</th><th>status</th><th>reason</th><th>replaced by</th><th>stage · date</th></tr></thead><tbody>' +
      hv.map(e => `<tr class="hist ${h(e.status)}"><td class="mono">${h(e.field_name)}</td><td>${h(fmtV(e.value_normalized))} <span class="conf">${fmtV(e.confidence)}</span></td><td><span class="tag ${h(e.route)}">${h(e.route)}</span> ${h(e.scope)}</td><td><span class="tag">${h(e.status)}</span></td><td>${h(e.reason)}<br><span class="quote small">“${h(e.evidence_quote)}”</span> <span class="small">${h(e.evidence_source)}</span></td><td>${h(e.replaced_by)}</td><td class="small">${h(e.change_stage)} · ${h(e.date)}</td></tr>`).join('') + '</tbody></table>'
      : '<p class="small">No superseded, rejected or dropped values for this sample.</p>';
  } catch (e) { $('history').textContent = 'could not load value history: ' + (e.message || e); }
}

// wiring
$('apply').addEventListener('click', () => { page = 0; run(); });
$('reset').addEventListener('click', () => { history.replaceState(null, '', location.pathname); for (const el of document.querySelectorAll('.filters select, .filters input')) { if (el.type === 'checkbox') el.checked = el.classList.contains('rt') || el.id === 'f-rule'; else if (el.type === 'range') { el.value = 0; $('f-bifido-val').textContent = '0'; } else if (el.tagName === 'SELECT') { for (const o of el.options) o.selected = false; el.value = ''; } else el.value = ''; } page = 0; sortCol = 'sample_key'; sortDir = 'ASC'; run(); });
$('prev').addEventListener('click', () => { page = Math.max(0, page-1); run(); });
$('next').addEventListener('click', () => { page++; run(); });
$('dl-csv').addEventListener('click', () => download('csv'));
$('dl-parquet').addEventListener('click', () => download('parquet'));
$('f-rule').addEventListener('change', () => { page = 0; run(); });
$('f-bifido').addEventListener('input', e => { $('f-bifido-val').textContent = e.target.value; });
$('detail-close').addEventListener('click', closeDetail);
function activate(e){ // F12: rows and sortable headers respond to click, Enter and Space
  const th = e.target.closest('th[data-col]'); if (th) { const c = th.dataset.col; if (sortCol === c) sortDir = sortDir === 'ASC' ? 'DESC' : 'ASC'; else { sortCol = c; sortDir = 'ASC'; } page = 0; run().then(() => { const nth = $('result-table').querySelector(`th[data-col="${c}"]`); if (nth) nth.focus(); }); return; }
  if (e.target.closest('a')) return;
  const tr = e.target.closest('tr[data-key]'); if (tr) showDetail(tr.dataset.key);
}
$('result-table').addEventListener('click', activate);
$('result-table').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { if (e.target.closest('th[data-col], tr[data-key]')) { e.preventDefault(); activate(e); } } });
let lastFocus = null;
function closeDetail(){ $('detail').classList.remove('open'); const p = new URLSearchParams(location.search); p.delete('sample'); history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : '')); if (lastFocus && document.body.contains(lastFocus)) lastFocus.focus(); }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('detail').classList.contains('open')) closeDetail(); });
$('f-study-filter').addEventListener('input', e => { const s = e.target.value.toLowerCase(); for (const o of $('f-study').options) o.hidden = s && !o.textContent.toLowerCase().includes(s); });
for (const el of document.querySelectorAll('.filters input[type=text], .filters input[type=number], .filters input:not([type])')) el.addEventListener('keydown', e => { if (e.key === 'Enter') { page = 0; run(); } });

init();
