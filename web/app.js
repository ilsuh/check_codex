'use strict';
// Python и словарные правила исполняются локально в браузере.
const input = document.getElementById('input');
const button = document.getElementById('generate');
const status = document.getElementById('status');
const results = document.getElementById('results');
const summary = document.getElementById('summary');
const output = document.getElementById('output');
const copy = document.getElementById('copy');
let python;

document.getElementById('example').addEventListener('click', () => {
  input.value = JSON.stringify([{lemma:'столбе́ц', symbol:'м', grammar:'5*b'}, {lemma:'чита́ть', symbol:'нсв', grammar:'1a'}], null, 2);
});
copy.addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(output.textContent); status.textContent = 'JSON скопирован.'; }
  catch { status.textContent = 'Не удалось скопировать; выделите JSON вручную.'; }
});
function show(items) {
  results.replaceChildren();
  summary.textContent = `Обработано статей: ${items.length}.`;
  for (const article of items) {
    const section = document.createElement('article'); section.className = 'entry';
    const title = document.createElement('h3'); title.textContent = article.effective_lemma || 'Без заглавного слова';
    const badge = document.createElement('span'); badge.className = 'badge' + (article.generation.status === 'generated' ? '' : ' problem'); badge.textContent = article.generation.status; title.append(badge); section.append(title);
    const diagnostics = [...article.diagnostics, ...article.generation.diagnostics, ...article.generation.readings.flatMap(r => [...r.diagnostics, ...(r.aspect_partner?.diagnostics || [])])];
    for (const d of diagnostics) { const p = document.createElement('p'); p.className = 'diagnostic'; p.textContent = d.message; section.append(p); }
    for (const reading of article.generation.readings) {
      const forms = document.createElement('div'); forms.className = 'forms';
      const seen = new Set();
      for (const form of reading.forms) { if (!form.stressed || seen.has(form.stressed)) continue; seen.add(form.stressed); const chip = document.createElement('span'); chip.className = 'form'; chip.textContent = form.stressed; forms.append(chip); }
      section.append(forms);
      if (reading.aspect_partner?.words.length) { const p = document.createElement('p'); p.textContent = 'Видовой партнёр: ' + reading.aspect_partner.words.map(w => w.stressed).join(', '); section.append(p); }
    }
    results.append(section);
  }
}
button.addEventListener('click', () => {
  try {
    const payload = JSON.parse(input.value);
    python.globals.set('_input_json', JSON.stringify(payload));
    const result = JSON.parse(python.runPython('import json\nfrom zaliz import generate\njson.dumps(generate(json.loads(_input_json)), ensure_ascii=False)'));
    output.textContent = JSON.stringify(result, null, 2); copy.disabled = false; show(result);
    status.className = ''; status.textContent = 'Готово.';
  } catch (error) { results.replaceChildren(); output.textContent = ''; copy.disabled = true; summary.textContent = 'Не удалось обработать данные.'; status.className = 'error'; status.textContent = String(error); }
});
async function start() {
  try {
    python = await loadPyodide();
    python.FS.mkdirTree('/home/pyodide/zaliz');
    const files = ['__init__.py','__main__.py','model.py','text.py','parser.py','references.py','declension.py','conjugation.py','generation.py','special.py','aspect.py','endings.json'];
    await Promise.all(files.map(async name => { const response = await fetch(`zaliz/${name}`); if (!response.ok) throw new Error(`Не удалось загрузить ${name}: ${response.status}`); python.FS.writeFile(`/home/pyodide/zaliz/${name}`, new Uint8Array(await response.arrayBuffer())); }));
    python.runPython('import sys\nsys.path.insert(0, "/home/pyodide")\nimport zaliz');
    button.disabled = false; status.textContent = 'Готово к работе.';
  } catch (error) { status.className = 'error'; status.textContent = 'Не удалось загрузить программу: ' + String(error); }
}
start();
