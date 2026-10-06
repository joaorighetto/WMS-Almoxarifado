// Evidência local do laboratório. Node >=22 e Chrome instalado; sem dependências npm.
// Uso: node docs/redesign-observatory/capturar.mjs [http://127.0.0.1:8010] [--interacoes | --capturas] [--alvos=a,b]
import { spawn } from 'node:child_process';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const origin = process.argv.slice(2).find(arg => !arg.startsWith('--')) || 'http://127.0.0.1:8010';
if (!['localhost', '127.0.0.1'].includes(new URL(origin).hostname)) throw Error('Servidor local exigido');
const output = '.impeccable/review';
const onlyInteractions = process.argv.includes('--interacoes');
const onlyCaptures = process.argv.includes('--capturas');
const selectedNames = process.argv.find(arg => arg.startsWith('--alvos='))?.slice(8).split(',');
const profile = await mkdtemp(join(tmpdir(), 'wms-capturas-'));
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
  '--hide-scrollbars', 'about:blank',
], { stdio: 'ignore' });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let browser;

class CDP {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.id = 0;
    this.pending = new Map();
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true });
      this.ws.addEventListener('error', reject, { once: true });
    });
    this.ws.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(Error(JSON.stringify(message.error)));
      else pending.resolve(message.result);
    });
  }
  async call(method, params = {}) {
    await this.ready;
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(Error(`Timeout: ${method}`)); }, 20000);
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async evaluate(expression) {
    const result = await this.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  close() { this.ws.close(); }
}

try {
  let port;
  for (let attempt = 0; attempt < 100; attempt++) {
    try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; }
    catch { await delay(100); }
  }
  if (!port) throw Error('Chrome não iniciou CDP');
  const endpoint = `http://127.0.0.1:${port}`;
  const version = await (await fetch(`${endpoint}/json/version`)).json();
  browser = new CDP(version.webSocketDebuggerUrl);
  // Matriz versionada: `.impeccable/review/` é ignorada pelo git e guarda só a saída.
  // `acao`: expressão que envia um formulário depois do carregamento (estados de erro de validação);
  // a captura espera a nova página. Os envios usados aqui são inválidos e não alteram dado.
  const capture = (name, role, size, theme, url, touch = false, acao = null) => ({ name, role, size, theme, touch, url, acao });
  const enviar = (form, campos) => `(() => { const f = document.querySelector(${JSON.stringify(form)}); ${
    Object.entries(campos).map(([nome, valor]) => `f.elements[${JSON.stringify(nome)}].value = ${JSON.stringify(valor)};`).join(' ')
  } f.noValidate = true; f.requestSubmit(); })()`;
  const loginInvalido = enviar('[data-login-form]', { username: 'nao.existe', password: 'senha-errada' });
  // Senhas iguais: a divergência é barrada no navegador (`confirmacao-senha.js`) e não recarrega a página;
  // aqui o servidor recusa a senha atual vazia e a política (senha curta e comum).
  const senhaInvalida = enviar('[data-processing-form]', { old_password: '', new_password1: 'abc', new_password2: 'abc' });
  const busca = '/catalogo/?descricao=papel';
  const captures = [
    capture('desktop', 'chefe-almoxarifado', '1440x900', 'light', '/'),
    capture('home-chefe-1440-escuro', 'chefe-almoxarifado', '1440x900', 'dark', '/'),
    capture('home-chefe-1280', 'chefe-almoxarifado', '1280x800', 'light', '/'),
    capture('home-chefe-820-toque', 'chefe-almoxarifado', '820x1180', 'light', '/', true),
    capture('mobile', 'chefe-almoxarifado', '390x844', 'light', '/', true),
    capture('home-chefe-390-escuro', 'chefe-almoxarifado', '390x844', 'dark', '/', true),
    capture('menu-820-toque', 'chefe-almoxarifado', '820x1180', 'light', '/', true),
    capture('menu-390-claro', 'chefe-almoxarifado', '390x844', 'light', '/', true),
    capture('menu-390-escuro', 'chefe-almoxarifado', '390x844', 'dark', '/', true),
    capture('envio-catalogo-1440-escuro-herdada', 'chefe-almoxarifado', '1440x900', 'dark', '/catalogo/importacao/'),
    capture('home-requisitante-1440', 'requisitante', '1440x900', 'light', '/'),
    capture('home-requisitante-390', 'requisitante', '390x844', 'light', '/', true),
    capture('catalogo-1440-claro', 'requisitante', '1440x900', 'light', busca),
    capture('catalogo-1440-escuro', 'requisitante', '1440x900', 'dark', busca),
    capture('catalogo-1280', 'requisitante', '1280x800', 'light', busca),
    capture('catalogo-820-toque', 'requisitante', '820x1180', 'light', busca, true),
    capture('catalogo-390-claro', 'requisitante', '390x844', 'light', busca, true),
    capture('catalogo-390-escuro', 'requisitante', '390x844', 'dark', busca, true),
    capture('catalogo-invalido-1440', 'requisitante', '1440x900', 'light', '/catalogo/?codigo=123'),
    capture('catalogo-invalido-390', 'requisitante', '390x844', 'light', '/catalogo/?codigo=123', true),
    capture('catalogo-sem-resultado-1440-escuro', 'requisitante', '1440x900', 'dark', '/catalogo/?descricao=zzzqqqxx'),
    capture('catalogo-pagina-inicial-1440', 'requisitante', '1440x900', 'light', '/catalogo/'),
    capture('home-auditor-1440', 'auditor', '1440x900', 'light', '/'),
    capture('entradas-auditor-1440-herdada', 'auditor', '1440x900', 'dark', '/estoque/entradas/'),
    capture('home-admin-1440', 'administrador-sistema', '1440x900', 'light', '/'),
    capture('usuarios-admin-1440-herdada', 'administrador-sistema', '1440x900', 'light', '/organizacao/usuarios/'),
    capture('entrada-nova-390-herdada', 'funcionario-almoxarifado', '390x844', 'light', '/estoque/entradas/nova/', true),
    // P1 — credenciais.
    capture('login-1440-claro', 'anonimo', '1440x900', 'light', '/login/'),
    capture('login-1440-escuro', 'anonimo', '1440x900', 'dark', '/login/'),
    capture('login-820-toque', 'anonimo', '820x1180', 'light', '/login/', true),
    capture('login-390-claro', 'anonimo', '390x844', 'light', '/login/', true),
    capture('login-390-escuro', 'anonimo', '390x844', 'dark', '/login/', true),
    capture('login-erro-1440', 'anonimo', '1440x900', 'light', '/login/', false, loginInvalido),
    capture('login-erro-390-escuro', 'anonimo', '390x844', 'dark', '/login/', true, loginInvalido),
    capture('senha-1440-claro', 'requisitante', '1440x900', 'light', '/senha/'),
    capture('senha-1440-escuro', 'requisitante', '1440x900', 'dark', '/senha/'),
    capture('senha-390-claro', 'requisitante', '390x844', 'light', '/senha/', true),
    capture('senha-erro-1440', 'requisitante', '1440x900', 'light', '/senha/', false, senhaInvalida),
    capture('senha-erro-390-escuro', 'requisitante', '390x844', 'dark', '/senha/', true, senhaInvalida),
    capture('provisoria-1440', 'critica.provisoria', '1440x900', 'light', '/senha/'),
    capture('provisoria-1440-escuro', 'critica.provisoria', '1440x900', 'dark', '/senha/'),
    capture('provisoria-390', 'critica.provisoria', '390x844', 'light', '/senha/', true),
    capture('home-sem-papel-1440', 'admin', '1440x900', 'light', '/'),
  ];
  // P2 — consultas e históricos. As execuções com conteúdo são a 2ª de cada importação do banco local
  // (catálogo: `seed_dev_02_revisao_simulada.csv`; fornecedores: revisão simulada criada para o P2).
  const fa = 'funcionario-almoxarifado';
  const ca = 'chefe-almoxarifado';
  const buscaFornecedores = '/fornecedores/?nome=ltda';
  for (const [nome, papel, url, cenarios] of [
    ['fornecedores', fa, buscaFornecedores, ['1440-claro', '1440-escuro', '1280', '820-toque', '390-claro', '390-escuro']],
    ['fornecedores-inicial', fa, '/fornecedores/', ['1440-claro']],
    ['fornecedores-codigo-invalido', fa, '/fornecedores/?codigo=12a', ['1440-claro', '390-claro']],
    ['fornecedores-documento-invalido', fa, '/fornecedores/?documento=abc', ['1440-escuro']],
    ['fornecedores-sem-resultado', fa, '/fornecedores/?nome=zzzqqqxx', ['1440-escuro', '390-claro']],
    ['historico-catalogo', ca, '/catalogo/importacoes/', ['1440-claro', '1440-escuro', '1280', '820-toque', '390-claro', '390-escuro']],
    ['historico-fornecedores', ca, '/fornecedores/importacoes/', ['1440-claro', '1440-escuro', '390-claro']],
    ['execucao-catalogo', ca, '/catalogo/importacoes/2/', ['1440-claro', '1440-escuro', '1280', '820-toque', '390-claro', '390-escuro']],
    ['execucao-catalogo-vazia', ca, '/catalogo/importacoes/1/', ['1440-claro', '390-escuro']],
    ['execucao-fornecedores', ca, '/fornecedores/importacoes/2/', ['1440-claro', '1440-escuro', '820-toque', '390-claro']],
    ['execucao-fornecedores-vazia', ca, '/fornecedores/importacoes/1/', ['1440-claro']],
  ]) {
    for (const cenario of cenarios) {
      const [largura, variante] = cenario.split('-');
      const size = { 1440: '1440x900', 1280: '1280x800', 820: '820x1180', 390: '390x844' }[largura];
      const touch = ['820', '390'].includes(largura);
      captures.push(capture(`${nome}-${cenario}`, papel, size, variante === 'escuro' ? 'dark' : 'light', url, touch));
    }
  }
  for (const [prefix, role, url] of [
    ['entradas-auditor', 'auditor', '/estoque/entradas/'],
    ['usuarios-admin', 'administrador-sistema', '/organizacao/usuarios/'],
  ]) {
    for (const theme of ['light', 'dark']) captures.push(capture(`${prefix}-1440-${theme}-herdada`, role, '1440x900', theme, url));
  }
  await mkdir(output, { recursive: true });
  let previous = [];
  try { previous = JSON.parse(await readFile(`${output}/captures.json`, 'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }

  const results = [];
  for (const capture of onlyInteractions ? [] : captures.filter(item => !selectedNames || selectedNames.includes(item.name))) {
    const { targetId } = await browser.call('Target.createTarget', { url: 'about:blank' });
    const targets = await (await fetch(`${endpoint}/json/list`)).json();
    const page = new CDP(targets.find(item => item.id === targetId).webSocketDebuggerUrl);
    const [width, height] = capture.size.split('x').map(Number);
    try {
      await page.call('Page.enable');
      await page.call('Runtime.enable');
      await page.call('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: capture.touch });
      await page.call('Emulation.setTouchEmulationEnabled', { enabled: capture.touch, maxTouchPoints: capture.touch ? 5 : 1 });
      await page.call('Emulation.setEmulatedMedia', { features: [
        { name: 'prefers-color-scheme', value: capture.theme },
        { name: 'pointer', value: capture.touch ? 'coarse' : 'fine' },
        { name: 'hover', value: capture.touch ? 'none' : 'hover' },
      ] });
      await page.call('Page.addScriptToEvaluateOnNewDocument', { source: "try { localStorage.removeItem('wms-tema'); } catch {}" });
      const url = new URL(capture.url, origin);
      url.searchParams.set('dev_como', capture.role);
      await page.call('Page.navigate', { url: url.href });
      for (let attempt = 0; attempt < 100; attempt++) {
        if (await page.evaluate("document.readyState === 'complete' && !!document.querySelector('main') && !location.search.includes('dev_como=')")) break;
        if (attempt === 99) throw Error(`Página não carregou: ${capture.name}`);
        await delay(100);
      }
      if (capture.acao) {
        await page.evaluate(`window.__antesDoEnvio = true; ${capture.acao}; void 0`);
        for (let attempt = 0; attempt < 100; attempt++) {
          if (await page.evaluate("!window.__antesDoEnvio && document.readyState === 'complete' && !!document.querySelector('main')").catch(() => false)) break;
          if (attempt === 99) throw Error(`Envio não concluiu: ${capture.name}`);
          await delay(100);
        }
      }
      await page.evaluate('document.fonts.ready');
      if (capture.name.startsWith('menu-')) await page.evaluate("document.querySelector('[data-menu-toggle]').click()");
      await delay(150);
      const evidence = await page.evaluate(`(() => {
        const rect = node => node ? { x:node.getBoundingClientRect().x,y:node.getBoundingClientRect().y,w:node.getBoundingClientRect().width,h:node.getBoundingClientRect().height } : null;
        const table = document.querySelector('#resultados-consulta table');
        const wrap = document.querySelector('#resultados-consulta .table-wrapper');
        return { title:document.title,url:location.pathname+location.search,scrollW:document.documentElement.scrollWidth,vw:innerWidth,h:document.documentElement.scrollHeight,
          sides:document.querySelectorAll('.side').length,mains:document.querySelectorAll('main').length,scheme:getComputedStyle(document.documentElement).colorScheme,
          pointerCoarse:matchMedia('(pointer: coarse)').matches,hoverNone:matchMedia('(hover: none)').matches,touchPoints:navigator.maxTouchPoints,
          nav:[...document.querySelectorAll('nav[aria-label="Seções"] a')].map(a=>({text:a.textContent.trim(),href:a.getAttribute('href'),current:a.getAttribute('aria-current')})),
          tiles:[...document.querySelectorAll('.tiles .tile')].map(rect),description:rect(document.querySelector('.catalogo-descricao-cell')),
          table:rect(table),wrapper:rect(wrap),
          wrappers:[...document.querySelectorAll('.table-wrapper')].map(w=>({width:w.clientWidth,content:w.scrollWidth,overflowY:getComputedStyle(w).overflowY,maxHeight:getComputedStyle(w).maxHeight})),tableScroll:wrap?{width:wrap.clientWidth,content:wrap.scrollWidth,background:getComputedStyle(wrap).backgroundImage}:null,
          plannedColumns:document.querySelector('#home-planned-heading')?.closest('section').querySelector('tbody tr')?.children.length,
          logoutForms:document.querySelectorAll('form[action="/logout/"][method="post"]').length,
          csrfPresent:!!document.querySelector('form[action="/logout/"] input[name="csrfmiddlewaretoken"]'),
          themeButtonVisible:!!document.querySelector('[data-theme-toggle]')?.getBoundingClientRect().width,
          sidebar:rect(document.querySelector('.side')),main:rect(document.querySelector('main')),
          bodyStyle:{font:getComputedStyle(document.body).fontFamily,size:getComputedStyle(document.body).fontSize,line:getComputedStyle(document.body).lineHeight,bg:getComputedStyle(document.body).backgroundColor},
        };
      })()`);
      if (evidence.vw !== width || evidence.scrollW > width || evidence.mains !== 1 || evidence.scheme !== capture.theme) throw Error(`Evidência inválida: ${JSON.stringify(evidence)}`);
      if (evidence.pointerCoarse !== capture.touch || evidence.hoverNone !== capture.touch) throw Error(`Mídia de toque inválida: ${capture.name}`);
      const full = await page.call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: 0, width, height: Math.max(height, evidence.h), scale: 1 } });
      await writeFile(`${output}/${capture.name}.png`, Buffer.from(full.data, 'base64'));
      const viewport = await page.call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
      await writeFile(`${output}/${capture.name}-viewport.png`, Buffer.from(viewport.data, 'base64'));
      results.push({ ...capture, ...evidence, capturedAt: new Date().toISOString(), browser: version.Browser });
      console.log(`${capture.name}: ${width}x${height}, página ${evidence.h}px, ${capture.theme}`);
    } finally { page.close(); await browser.call('Target.closeTarget', { targetId }); }
  }
  if (!onlyInteractions) {
    const merged = selectedNames
      ? captures.map(item => results.find(result => result.name === item.name) || previous.find(old => old.name === item.name)).filter(Boolean)
      : results;
    await writeFile(`${output}/captures.json`, JSON.stringify(merged, null, 2) + '\n');
    console.log(`${results.length} capturas concluídas.`);
  }
  if (onlyCaptures) process.exitCode = 0;
  if (!onlyCaptures) {

  // Smoke real do navegador: nenhuma alteração de dado de negócio.
  const { targetId } = await browser.call('Target.createTarget', { url: 'about:blank' });
  const targets = await (await fetch(`${endpoint}/json/list`)).json();
  const page = new CDP(targets.find(item => item.id === targetId).webSocketDebuggerUrl);
  const checks = [];
  const waitFor = async expression => {
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await page.evaluate(expression)) return;
      await delay(100);
    }
    throw Error(`Condição não atingida: ${expression}`);
  };
  const check = async (name, expression) => {
    const evidence = await page.evaluate(expression);
    if (!evidence) throw Error(`Falha no smoke: ${name}`);
    checks.push({ name, passed: true, evidence });
    console.log(`OK: ${name}`);
  };
  try {
    await page.call('Page.enable');
    await page.call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    await page.call('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }] });
    await page.call('Page.navigate', { url: `${origin}/catalogo/?dev_como=requisitante` });
    await waitFor("document.readyState==='complete' && !!document.querySelector('#ordenar-descricao') && !location.search.includes('dev_como')");
    await page.evaluate("localStorage.removeItem('wms-tema'); document.documentElement.removeAttribute('data-theme'); window.__smokeOriginalBody=document.body; void 0");
    await page.evaluate("document.querySelector('[data-theme-toggle]').click()");
    await check('Tema claro → escuro', "getComputedStyle(document.documentElement).colorScheme==='dark' && localStorage.getItem('wms-tema')==='dark'");
    await page.call('Page.reload');
    await waitFor("document.readyState==='complete' && !!document.querySelector('#ordenar-descricao')");
    await check('Tema persistido após reload', "getComputedStyle(document.documentElement).colorScheme==='dark'");
    await page.evaluate("window.__smokeOriginalBody=document.body; document.querySelector('#ordenar-descricao').click()");
    await waitFor("document.querySelector('#ordenar-descricao')?.closest('th').getAttribute('aria-sort')==='ascending'");
    await check('Ordenação HTMX sem shell duplicado', "document.body===window.__smokeOriginalBody && document.querySelectorAll('.side').length===1 && document.querySelectorAll('script[src*=\"shell.js\"]').length===1");
    await page.evaluate("document.querySelector('#pagina-pagina-2-larga').click()");
    await waitFor("location.search.includes('pagina=2') && !document.querySelector('.htmx-request')");
    await check('Paginação HTMX e foco', "document.activeElement===document.querySelector('#resultados-consulta table') && document.querySelectorAll('.side').length===1");
    await page.evaluate('history.back()');
    await waitFor("!location.search.includes('pagina=2') && !!document.querySelector('a#pagina-pagina-2-larga')");
    await page.evaluate('history.forward()');
    // A URL muda antes de o HTMX restaurar o conteúdo; esperar só por ela deixa a restauração atropelar o submit seguinte.
    await waitFor("location.search.includes('pagina=2') && !document.querySelector('a#pagina-pagina-2-larga') && !document.querySelector('.htmx-request')");
    await check('Histórico e tema após restauração', "getComputedStyle(document.documentElement).colorScheme==='dark' && document.querySelectorAll('.side').length===1 && document.querySelectorAll('script[src*=\"shell.js\"]').length===1");
    await page.evaluate("document.querySelector('[data-theme-toggle]').click()");
    await check('Tema escuro → claro, listener único após histórico', "getComputedStyle(document.documentElement).colorScheme==='light' && localStorage.getItem('wms-tema')==='light'");
    // Exercita a validação do servidor, além da barreira nativa de pattern do campo.
    await page.evaluate("document.querySelector('#id_codigo').value='123'; document.querySelector('.filter-bar').noValidate=true; document.querySelector('.filter-bar').requestSubmit()");
    await waitFor("!!document.querySelector('#campo-codigo .field-error')");
    await check('Código inválido via HTMX e erro associado', "document.querySelector('#id_codigo').getAttribute('aria-invalid')==='true' && !!document.querySelector('#campo-codigo .field-error') && document.querySelectorAll('.side').length===1");
    // P2 — consulta de fornecedores (paginação HTMX, ordenação de página inteira, código inválido sem apagar a
    // tabela) e linha clicável do histórico.
    await page.call('Page.navigate', { url: `${origin}/fornecedores/?dev_como=funcionario-almoxarifado` });
    await waitFor("document.readyState==='complete' && !!document.querySelector('#pagina-pagina-2-larga') && !location.search.includes('dev_como')");
    await page.evaluate("window.__smokeOriginalBody=document.body; document.querySelector('#pagina-pagina-2-larga').click()");
    await waitFor("location.search.includes('pagina=2') && !document.querySelector('.htmx-request')");
    await check('Fornecedores: paginação HTMX sem shell duplicado', "document.body===window.__smokeOriginalBody && document.activeElement===document.querySelector('#resultados-consulta table') && document.querySelectorAll('.side').length===1 && document.querySelectorAll('main').length===1");
    await page.evaluate("document.querySelector('#ordenar-nome').click()");
    await waitFor("document.readyState==='complete' && document.querySelector('#ordenar-nome')?.closest('th').getAttribute('aria-sort')==='descending'");
    await check('Fornecedores: ordenação recarrega a página e volta à página 1', "!location.search.includes('pagina=2') && document.querySelector('input[name=ordem]').value==='-nome' && document.querySelectorAll('.side').length===1");
    await page.evaluate("window.__linhasAntes=document.querySelectorAll('#resultados-consulta tbody tr').length; document.querySelector('#id_codigo').value='12a'; document.querySelector('.filter-bar').noValidate=true; document.querySelector('.filter-bar').requestSubmit()");
    await waitFor("!!document.querySelector('#campo-codigo .field-error')");
    await check('Fornecedores: código inválido via HTMX marca o campo sem apagar a tabela', "document.querySelector('#id_codigo').getAttribute('aria-invalid')==='true' && document.querySelectorAll('#resultados-consulta tbody tr').length===window.__linhasAntes && window.__linhasAntes>1");
    await page.call('Page.navigate', { url: `${origin}/catalogo/importacoes/?dev_como=chefe-almoxarifado` });
    await waitFor("document.readyState==='complete' && !!document.querySelector('[data-linha-clicavel]') && !location.search.includes('dev_como')");
    await page.evaluate("document.querySelector('[data-linha-clicavel] td:nth-child(3)').click()");
    await waitFor("document.readyState==='complete' && /importacoes\\/\\d+\\/$/.test(location.pathname)");
    await check('Histórico: clique na linha abre a execução', "/importacoes\\/\\d+\\/$/.test(location.pathname) && document.querySelectorAll('.side').length===1");
    await page.call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await page.call('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
    await page.evaluate("document.querySelector('[data-menu-toggle]').click()");
    await check('Menu móvel aberto', "document.querySelector('[data-menu-toggle]').getAttribute('aria-expanded')==='true' && document.querySelector('.side').hasAttribute('data-open')");
    await page.call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await check('Escape fecha menu e devolve foco', "!document.querySelector('.side').hasAttribute('data-open') && document.activeElement===document.querySelector('[data-menu-toggle]')");
    await page.call('Emulation.setScriptExecutionDisabled', { value: true });
    await page.call('Page.navigate', { url: `${origin}/?dev_como=requisitante` });
    await waitFor("document.readyState==='complete' && !!document.querySelector('nav[aria-label=\"Seções\"]') && !location.search.includes('dev_como')");
    await check('Sem JS: tema oculto, menu e logout disponíveis', "!document.documentElement.classList.contains('js') && getComputedStyle(document.querySelector('[data-theme-toggle]')).display==='none' && document.querySelector('nav').getBoundingClientRect().height>0 && !!document.querySelector('form[action=\"/logout/\"] input[name=\"csrfmiddlewaretoken\"]')");
  } finally {
    await writeFile(`${output}/interacoes.json`, JSON.stringify({ capturedAt: new Date().toISOString(), browser: version.Browser, checks }, null, 2) + '\n');
    page.close(); await browser.call('Target.closeTarget', { targetId });
  }
  }
} finally {
  if (browser) { try { await browser.call('Browser.close'); } catch {} browser.close(); }
  chrome.kill();
  await delay(200);
  await rm(profile, { recursive: true, force: true });
}
