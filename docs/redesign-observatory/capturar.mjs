// Evidência local do laboratório. Node >=22 e Chrome instalado; sem dependências npm.
// Uso: node docs/redesign-observatory/capturar.mjs [http://127.0.0.1:8010] [--interacoes | --capturas] [--alvos=a,b]
// Importações (P3): o roteiro só envia arquivos, vê a prévia e, no máximo, cancela. NUNCA confirma — confirmar
// grava dados. Como salvaguarda, toda página intercepta por CDP (`Fetch.enable` + `Fetch.failRequest`) as
// requisições a `*/importacao/confirmar/*`, inclusive a navegação de um formulário — `Network.setBlockedURLs`
// NÃO barra essa navegação no Chrome headless (incidente do P3: duas importações gravadas no banco local).
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
const insumos = await mkdtemp(join(tmpdir(), 'wms-insumos-'));
const URLS_BLOQUEADAS = (process.env.CAPTURAR_BLOQUEAR || '*/importacao/confirmar/*').split(',');
const bloquear = async page => {
  await page.call('Fetch.enable', { patterns: URLS_BLOQUEADAS.map(urlPattern => ({ urlPattern, requestStage: 'Request' })) });
};
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
      // Barreira contra gravar dado: toda requisição interceptada (só as de URLS_BLOQUEADAS) falha.
      if (message.method === 'Fetch.requestPaused') {
        this.bloqueadas = (this.bloqueadas || 0) + 1;
        this.ws.send(JSON.stringify({ id: ++this.id, method: 'Fetch.failRequest', params: { requestId: message.params.requestId, errorReason: 'BlockedByClient' } }));
        return;
      }
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

const esperarNovaPagina = async (page, nome) => {
  for (let attempt = 0; attempt < 150; attempt++) {
    if (await page.evaluate("!window.__antesDoEnvio && document.readyState === 'complete' && !!document.querySelector('main')").catch(() => false)) return;
    if (attempt === 149) throw Error(`Envio não concluiu: ${nome}`);
    await delay(100);
  }
};
const escolherArquivo = async (page, arquivo) => {
  await page.call('DOM.enable');
  const { root } = await page.call('DOM.getDocument', { depth: 0 });
  const { nodeId } = await page.call('DOM.querySelector', { nodeId: root.nodeId, selector: 'input[type=file]' });
  if (!nodeId) throw Error('Campo de arquivo não encontrado');
  await page.call('DOM.setFileInputFiles', { nodeId, files: [arquivo] });
  await page.evaluate("document.querySelector('input[type=file]').dispatchEvent(new Event('change', { bubbles: true })); void 0");
};
// Estado de processamento sem envio: o listener de `envio.js` (registrado antes) ocupa o formulário, e
// este, registrado depois, cancela o submit. Na confirmação a action passa a ser a própria prévia (GET
// apenas) e a URL de confirmação é interceptada e falha — três barreiras contra gravar dado.
const provocarProcessamento = async (page, seletor) => {
  const ok = await page.evaluate(`(() => {
    const f = document.querySelector(${JSON.stringify(seletor)});
    if (!f) return false;
    f.setAttribute('data-captura-processando', '');
    if (f.action.includes('/importacao/confirmar/')) f.setAttribute('action', location.pathname);
    f.addEventListener('submit', e => e.preventDefault());
    f.requestSubmit();
    return f.getAttribute('aria-busy') === 'true' && !!f.querySelector('[data-processing-submit]').disabled;
  })()`);
  if (!ok) throw Error(`Estado de processamento não provocado: ${seletor}`);
};
// Prévia rica de fornecedores contra o banco local (seed_dev + revisão do P2): a partir do export real,
// 3 liberados passam a bloqueado, 1 bloqueado volta a liberado, 1 código novo chega bloqueado e um par
// de código duplicado é recusado. Escrito só no diretório temporário.
async function gerarFornecedoresRico() {
  let texto;
  try { texto = (await readFile('docs/CSVs/fornecedores.csv', 'utf8')).replace(/^\uFEFF/, ''); }
  catch { return null; }
  const registros = texto.split('\r\n');
  const cabecalho = registros[0].split(';');
  const iCodif = cabecalho.indexOf('CODIF');
  const iBloq = cabecalho.indexOf('BLOQ_OPCAO');
  let liberadosTrocados = 0, bloqueadosTrocados = 0;
  const corpo = registros.slice(1).filter(Boolean).map(linha => {
    const campos = linha.split(';');
    if (campos.length !== cabecalho.length) return linha;
    if (campos[iBloq] === 'S' && liberadosTrocados < 3) { campos[iBloq] = 'B'; liberadosTrocados++; }
    else if (campos[iBloq] === 'B' && bloqueadosTrocados < 1) { campos[iBloq] = 'S'; bloqueadosTrocados++; }
    return campos.join(';');
  });
  const modelo = corpo.find(linha => linha.split(';').length === cabecalho.length).split(';');
  const novo = (codif, bloq) => { const c = [...modelo]; c[iCodif] = codif; c[iBloq] = bloq; return c.join(';'); };
  corpo.push(novo('999901', 'B'), novo('999902', 'S'), novo('999902', 'S'));
  const destino = join(insumos, 'fornecedores-previa-rica.csv');
  await writeFile(destino, '\uFEFF' + [registros[0], ...corpo, ''].join('\r\n'));
  return destino;
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
  const capture = (name, role, size, theme, url, touch = false, acao = null, extra = {}) => ({ name, role, size, theme, touch, url, acao, ...extra });
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
  // P3 — importações. `upload`: arquivo enviado pelo formulário de envio (DOM.setFileInputFiles) antes da
  // captura; `enviar: false` só escolhe o arquivo. `depois`: URL aberta depois do envio (prévia pendente).
  // `processando`: seletor do formulário cujo estado de processamento (`envio.js`) é provocado sem envio
  // (o submit é cancelado; na confirmação a action também é trocada e a URL está bloqueada).
  // Insumos: fixtures sintéticas de `tests/fixtures/` e, para a prévia rica de fornecedores, uma derivação
  // local de `docs/CSVs/fornecedores.csv` (fora do Git; gerada num diretório temporário, nunca versionada).
  const fx = nome => join(process.cwd(), 'tests/fixtures', nome);
  const fornecedoresRico = await gerarFornecedoresRico();
  const csv = {
    catalogoRico: fx('catalogo/carga_inicial_casos_spec.csv'),
    catalogoLimpo: fx('catalogo/linhas_vazias.csv'),
    catalogoInvalido: fx('catalogo/codificacao_invalida.csv'),
    fornecedoresLimpo: fx('fornecedores/nomes_iguais_codigos_distintos.csv'),
    fornecedoresInvalido: fx('fornecedores/byte_invalido.csv'),
  };
  const confirmar = 'form[action$="/importacao/confirmar/"]';
  const p3 = [
    ['envio-catalogo', '/catalogo/importacao/', {}, ['1440-claro', '1440-escuro', '820-toque', '390-claro', '390-escuro']],
    ['envio-catalogo-erro', '/catalogo/importacao/', { upload: csv.catalogoInvalido }, ['1440-claro', '390-escuro']],
    ['envio-catalogo-processando', '/catalogo/importacao/', { upload: csv.catalogoLimpo, enviar: false, processando: 'form[data-processing-form]' }, ['1440-claro']],
    ['envio-catalogo-pendente', '/catalogo/importacao/', { upload: csv.catalogoLimpo, depois: '/catalogo/importacao/' }, ['1440-claro', '390-claro']],
    ['previa-catalogo', '/catalogo/importacao/', { upload: csv.catalogoRico }, ['1440-claro', '1440-escuro', '1280', '820-toque', '390-claro', '390-escuro']],
    ['previa-catalogo-limpa', '/catalogo/importacao/', { upload: csv.catalogoLimpo }, ['1440-claro', '390-escuro']],
    ['previa-catalogo-processando', '/catalogo/importacao/', { upload: csv.catalogoRico, processando: confirmar }, ['1440-claro', '390-claro']],
    ['envio-fornecedores', '/fornecedores/importacao/', {}, ['1440-claro', '1440-escuro', '390-claro']],
    ['envio-fornecedores-erro', '/fornecedores/importacao/', { upload: csv.fornecedoresInvalido }, ['1440-claro']],
    ['previa-fornecedores-limpa', '/fornecedores/importacao/', { upload: csv.fornecedoresLimpo }, ['1440-claro', '390-escuro']],
    ['previa-fornecedores-processando', '/fornecedores/importacao/', { upload: csv.fornecedoresLimpo, processando: confirmar }, ['390-claro']],
  ];
  if (fornecedoresRico) {
    p3.push(['previa-fornecedores', '/fornecedores/importacao/', { upload: fornecedoresRico }, ['1440-claro', '1440-escuro', '1280', '820-toque', '390-claro', '390-escuro']]);
  } else console.warn('docs/CSVs/fornecedores.csv ausente: cenários previa-fornecedores-* (prévia rica) omitidos.');
  for (const [nome, url, extra, cenarios] of p3) {
    for (const cenario of cenarios) {
      const [largura, variante] = cenario.split('-');
      const size = { 1440: '1440x900', 1280: '1280x800', 820: '820x1180', 390: '390x844' }[largura];
      const touch = ['820', '390'].includes(largura);
      captures.push(capture(`${nome}-${cenario}`, ca, size, variante === 'escuro' ? 'dark' : 'light', url, touch, null, extra));
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
      await bloquear(page);
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
      if (capture.upload) {
        await escolherArquivo(page, capture.upload);
        if (capture.enviar !== false) {
          await page.evaluate("window.__antesDoEnvio = true; document.querySelector('input[type=file]').form.requestSubmit(); void 0");
          await esperarNovaPagina(page, capture.name);
        }
      }
      if (capture.depois) {
        await page.evaluate(`window.__antesDoEnvio = true; location.href = ${JSON.stringify(capture.depois)}; void 0`);
        await esperarNovaPagina(page, capture.name);
      }
      if (capture.processando) await provocarProcessamento(page, capture.processando);
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
    await bloquear(page);
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
    // P3 — importações: envio, prévia, processamento, prévia pendente e cancelamento. Nada é confirmado.
    const ir = async (url, condicao) => {
      await page.call('Page.navigate', { url: `${origin}${url}` });
      await waitFor(`document.readyState==='complete' && !location.search.includes('dev_como') && ${condicao}`);
    };
    const enviarArquivo = async arquivo => {
      await escolherArquivo(page, arquivo);
      await page.evaluate("window.__antesDoEnvio = true; document.querySelector('input[type=file]').form.requestSubmit(); void 0");
      await esperarNovaPagina(page, 'interações P3');
    };
    const previaOk = `/\\/importacao\\/previa\\/$/.test(location.pathname) && document.querySelector('h1')?.textContent.includes('Não gravada')
      && document.querySelectorAll('${confirmar}').length===1 && document.querySelectorAll('form[action$="/importacao/cancelar/"]').length===1
      && !!document.querySelector('${confirmar} input[name=token]') && !!document.querySelector('${confirmar} input[name=impressao_digital]')
      && document.querySelectorAll('main').length===1 && document.querySelectorAll('.side').length===1`;
    await ir('/catalogo/importacao/?dev_como=chefe-almoxarifado', "!!document.querySelector('input[type=file]')");
    await escolherArquivo(page, csv.catalogoRico);
    await check('Importação: arquivo escolhido aparece no envio', "document.querySelector('[data-file-upload-meta]').textContent.startsWith('carga_inicial_casos_spec.csv — ')");
    await page.evaluate("window.__antesDoEnvio = true; document.querySelector('input[type=file]').form.requestSubmit(); void 0");
    await esperarNovaPagina(page, 'interações P3');
    await check('Importação: envio abre a prévia não gravada com um único par confirmar/cancelar', previaOk);
    await provocarProcessamento(page, confirmar);
    await check('Importação: confirmação em processamento com rótulo legível e Cancelar desabilitado, sem envio', "(() => { const f = document.querySelector('[data-captura-processando]'); return f.querySelector('[data-processing-submit-label]').textContent==='Confirmando…' && f.querySelector('[data-processing-submit]').disabled && f.getAttribute('aria-busy')==='true' && document.querySelector('.confirmation-bar form[action$=\"/importacao/cancelar/\"] button').disabled && /\\/previa\\/$/.test(location.pathname); })()");
    await ir('/catalogo/importacao/', "!!document.querySelector('input[type=file]')");
    await check('Importação: prévia pendente anunciada no envio', "!!document.querySelector('[role=status] a[href$=\"/catalogo/importacao/previa/\"]')");
    await ir('/catalogo/importacao/previa/', "!!document.querySelector('form[action$=\"/importacao/cancelar/\"]')");
    await page.evaluate("window.__antesDoEnvio = true; document.querySelector('form[action$=\"/importacao/cancelar/\"]').requestSubmit(); void 0");
    await esperarNovaPagina(page, 'interações P3');
    await check('Importação: cancelar volta ao envio e descarta a prévia', "location.pathname==='/catalogo/importacao/' && !document.querySelector('[role=status] a[href$=\"/importacao/previa/\"]')");
    await enviarArquivo(csv.catalogoInvalido);
    await check('Importação: arquivo recusado com erro associado ao campo', "(() => { const i = document.querySelector('input[type=file]'); const ids = (i.getAttribute('aria-describedby') || '').split(' ').filter(Boolean); return location.pathname==='/catalogo/importacao/' && ids.length>0 && ids.every(id => document.getElementById(id)?.textContent.trim()); })()");
    await ir('/fornecedores/importacao/', "!!document.querySelector('input[type=file]')");
    await enviarArquivo(csv.fornecedoresLimpo);
    await check('Importação de fornecedores: prévia com a nota de bloqueio', `${previaOk} && document.querySelector('main').textContent.includes('não pode ser emitente de uma entrada')`);
    await page.evaluate("window.__antesDoEnvio = true; document.querySelector('form[action$=\"/importacao/cancelar/\"]').requestSubmit(); void 0");
    await esperarNovaPagina(page, 'interações P3');
    await check('Importação de fornecedores: cancelar volta ao envio', "location.pathname==='/fornecedores/importacao/' && !document.querySelector('[role=status] a[href$=\"/importacao/previa/\"]')");
    await ir('/catalogo/importacoes/', "!!document.querySelector('[data-linha-clicavel]')");
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
  await rm(insumos, { recursive: true, force: true });
}
