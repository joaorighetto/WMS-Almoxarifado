// Evidência local do laboratório. Node >=22 e Chrome instalado; sem dependências npm.
// Uso: node docs/redesign-observatory/capturar.mjs [http://127.0.0.1:8010] [--interacoes | --capturas] [--alvos=a,b,prefixo-*]
// Importações (P3): o roteiro só envia arquivos, vê a prévia e, no máximo, cancela. NUNCA confirma — confirmar
// grava dados. Como salvaguarda, toda página intercepta por CDP (`Fetch.enable` + `Fetch.failRequest`) as
// requisições a `*/importacao/confirmar/*`, inclusive a navegação de um formulário — `Network.setBlockedURLs`
// NÃO barra essa navegação no Chrome headless (incidente do P3: duas importações gravadas no banco local).
// Estoque (P4): o roteiro nunca confirma entrada nem estorna. O estorno é POST na MESMA URL do GET que mostra
// a tela, então a barreira filtra por método: toda requisição que casa com URLS_BLOQUEADAS e não é GET/HEAD
// falha (`Fetch.failRequest`); GET/HEAD seguem (`Fetch.continueRequest`).
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
const URLS_BLOQUEADAS = (process.env.CAPTURAR_BLOQUEAR || '*/importacao/confirmar/*,*/entradas/nova/confirmar/*,*/estorno/*').split(',');
const METODOS_LIVRES = ['GET', 'HEAD'];
// Toda requisição barrada (qualquer aba do roteiro) entra aqui; o resumo final a lista.
const BLOQUEADAS = [];
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
      // Barreira contra gravar dado: requisição interceptada (só as de URLS_BLOQUEADAS) que não seja GET/HEAD
      // falha; GET/HEAD seguem (a tela de estorno é GET na mesma URL do POST que estorna).
      if (message.method === 'Fetch.requestPaused') {
        const { requestId, request } = message.params;
        if (METODOS_LIVRES.includes(request.method)) {
          this.ws.send(JSON.stringify({ id: ++this.id, method: 'Fetch.continueRequest', params: { requestId } }));
          return;
        }
        BLOQUEADAS.push(`${request.method} ${request.url}`);
        this.ws.send(JSON.stringify({ id: ++this.id, method: 'Fetch.failRequest', params: { requestId, errorReason: 'BlockedByClient' } }));
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
// Estado de processamento sem envio: o listener da tela (`envio.js` no form; `estoque.js` delegado em `body`) ocupa o
// formulário, e este, registrado no próprio form, cancela o submit (o JS da tela não olha `defaultPrevented`, então roda
// mesmo assim — o retorno confere `aria-busy` e o botão desabilitado). Quatro barreiras contra gravar dado: (1) a action
// do formulário de efeito (confirmar importação/entrada, estornar) passa a ser a própria página e o método vira GET;
// (2) `preventDefault`; (3) a interceptação por CDP falha qualquer requisição não-GET às URLs de efeito; (4) o roteiro
// nunca clica no botão — só `requestSubmit` aqui.
const provocarProcessamento = async (page, seletor) => {
  const ok = await page.evaluate(`(() => {
    const f = document.querySelector(${JSON.stringify(seletor)});
    if (!f) return false;
    f.setAttribute('data-captura-processando', '');
    if (['/importacao/confirmar/', '/entradas/nova/confirmar/', '/estorno/'].some(fim => new URL(f.action).pathname.endsWith(fim))) {
      f.setAttribute('action', location.pathname);
      f.setAttribute('method', 'get');
    }
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

// Roteiros da composição da entrada (P4): cliques HTMX na própria tela, sem gravar. Só "Revisar", as buscas, escolher
// emitente, adicionar/remover item e "Voltar e corrigir" são acionados — todos POST em `/estoque/entradas/nova/`, que
// compõe e valida sem gravar. O roteiro NUNCA aciona o formulário de `/entradas/nova/confirmar/` nem `/estorno/`.
const swapsAteAgora = page => page.evaluate('window.__swaps');
const aguardarSwap = async (page, antes, nome) => {
  for (let attempt = 0; attempt < 100; attempt++) {
    if ((await page.evaluate('window.__swaps')) > antes && await page.evaluate("!document.querySelector('.htmx-request')")) { await delay(120); return; }
    await delay(100);
  }
  throw Error(`Troca HTMX não concluiu: ${nome}`);
};
const passoHtmx = async (page, js, nome) => {
  const antes = await swapsAteAgora(page);
  await page.evaluate(`(() => { ${js} })(); void 0`);
  await aguardarSwap(page, antes, nome);
};
const clicar = (seletor) => `document.querySelector(${JSON.stringify(seletor)}).click();`;
const preencher = (seletor, valor) => `document.querySelector(${JSON.stringify(seletor)}).value = ${JSON.stringify(valor)};`;
const acionarBotao = (nome, valor) => clicar(`button[name="${nome}"][value="${valor}"]`);
const adicionarMaterial = async (page, cadpro, quantidade) => {
  await passoHtmx(page, preencher('#id_busca_material', cadpro) + acionarBotao('acao', 'buscar_material'), `buscar ${cadpro}`);
  await passoHtmx(page, clicar('button[name="adicionar_material"]'), `adicionar ${cadpro}`);
  await page.evaluate(`(() => { const campos = document.querySelectorAll('input[inputmode="decimal"]'); campos[campos.length - 1].value = ${JSON.stringify(quantidade)}; })(); void 0`);
};
const roteiros = {
  // Composição montada: motivo Compra (o tipo vira Nota fiscal pelo JS), emitente liberado e dois materiais com quantidade.
  async montar(page, quantidades = ['12,5', '3']) {
    await page.evaluate("window.__swaps = 0; document.body.addEventListener('htmx:after:settle', () => { window.__swaps++; }); void 0");
    await page.evaluate(`(() => { const m = document.querySelector('#id_motivo'); m.value = 'COMPRA'; m.dispatchEvent(new Event('change', { bubbles: true })); ${preencher('#id_numero_documento', 'NF-000321/2026')} })(); void 0`);
    await passoHtmx(page, preencher('#id_busca_emitente', 'ltda') + acionarBotao('acao', 'buscar_emitente'), 'buscar emitente');
    await passoHtmx(page, clicar('button[name="escolher_emitente"]'), 'escolher emitente');
    await adicionarMaterial(page, '000.000.002', quantidades[0]);
    await adicionarMaterial(page, '000.000.006', quantidades[1]);
  },
  async revisao(page) {
    await roteiros.montar(page);
    await passoHtmx(page, acionarBotao('acao', 'revisar'), 'revisar');
    // O Confirmar ignora ativações por ~500 ms depois que a revisão entra (`estoque.js`): o processamento provocado
    // depois disto (`provocarProcessamento`) e a captura esperam essa janela.
    await delay(650);
  },
  async 'erro-quantidade'(page) {
    await roteiros.montar(page, ['abc', '3']);
    await passoHtmx(page, acionarBotao('acao', 'revisar'), 'revisar com quantidade inválida');
  },
  async 'erro-validacao'(page) {
    await page.evaluate("window.__swaps = 0; document.body.addEventListener('htmx:after:settle', () => { window.__swaps++; }); void 0");
    await passoHtmx(page, acionarBotao('acao', 'revisar'), 'revisar vazio');
  },
  // Emitente já escolhido com a busca de troca aberta: "Trocar emitente" e "Remover emitente" juntos sob o nome.
  async 'trocar-emitente'(page) {
    await roteiros.montar(page);
    await page.evaluate("document.querySelector('.estoque-busca-recolhida > summary').click(); void 0");
    await passoHtmx(page, preencher('#id_busca_emitente', 'IMPLANTAÇÃO') + acionarBotao('acao', 'buscar_emitente'), 'buscar emitente para trocar');
  },
  // Emitente bloqueado: a busca mostra "Indisponível"/"Bloqueado" e nenhum botão Escolher para ele.
  async 'emitente-bloqueado'(page) {
    await page.evaluate("window.__swaps = 0; document.body.addEventListener('htmx:after:settle', () => { window.__swaps++; }); void 0");
    await passoHtmx(page, preencher('#id_busca_emitente', 'IMPLANTAÇÃO') + acionarBotao('acao', 'buscar_emitente'), 'buscar emitente bloqueado');
  },
};

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
    capture('home-admin-1440', 'administrador-sistema', '1440x900', 'light', '/'),
    capture('usuarios-admin-1440-herdada', 'administrador-sistema', '1440x900', 'light', '/organizacao/usuarios/'),
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
  // P4 — estoque (entradas de materiais). Dados do banco local preparado pelo serviço de domínio: #1 estornada
  // (doação com emitente), #2 compra NF-000123/2026 com emitente liberado e 3 itens (estorno possível), #3 doação
  // sem emitente, #4 compra NF-000124/2026 com estorno BLOQUEADO por saldo, #5 empréstimo devolvido estornado.
  // `roteiro`: cliques HTMX na composição (ver `roteiros`); `processando`: estado do envio de efeito, sem enviar.
  // Limitações registradas: (a) a lista vazia (S17) só existe com o banco sem entradas — `get_page` clampa uma
  // página fora do intervalo para a última — e não se apaga dado para capturá-la; (b) o erro de justificativa do
  // estorno (S20) vem de um POST em `/estorno/`, que a barreira recusa por método: está coberto por teste de view
  // e não é capturado aqui.
  const grupoClaroEscuro = ['1440-claro', '1440-escuro', '820-toque', '390-claro', '390-escuro'];
  const p4 = [
    ['entradas-fa', fa, '/estoque/entradas/', {}, ['1440-claro', '1440-escuro', '1280', '820-toque', '390-claro', '390-escuro']],
    ['entradas-auditor', 'auditor', '/estoque/entradas/', {}, ['1440-claro', '1440-escuro', '390-claro']],
    ['entrada-nova-vazia', fa, '/estoque/entradas/nova/', {}, grupoClaroEscuro],
    ['entrada-nova-montada', fa, '/estoque/entradas/nova/', { roteiro: 'montar' }, ['1440-claro', '1440-escuro', '1280', '820-toque', '390-claro', '390-escuro']],
    ['entrada-nova-revisao', fa, '/estoque/entradas/nova/', { roteiro: 'revisao' }, ['1440-claro', '1440-escuro', '1280', '820-toque', '390-claro', '390-escuro']],
    ['entrada-nova-emitente-bloqueado', fa, '/estoque/entradas/nova/', { roteiro: 'emitente-bloqueado' }, ['1440-claro', '390-claro']],
    ['entrada-nova-trocar-emitente', fa, '/estoque/entradas/nova/', { roteiro: 'trocar-emitente' }, ['1440-claro', '390-claro']],
    ['entrada-nova-erro-validacao', fa, '/estoque/entradas/nova/', { roteiro: 'erro-validacao' }, ['1440-claro', '1440-escuro', '390-claro']],
    ['entrada-nova-erro-quantidade', fa, '/estoque/entradas/nova/', { roteiro: 'erro-quantidade' }, ['1440-claro', '390-escuro']],
    ['entrada-nova-processando', fa, '/estoque/entradas/nova/', { roteiro: 'revisao', processando: 'form[action$="/entradas/nova/confirmar/"]' }, ['1440-claro', '390-claro']],
    ['entrada-detalhe-fa', fa, '/estoque/entradas/2/', {}, grupoClaroEscuro],
    ['entrada-detalhe-auditor', 'auditor', '/estoque/entradas/2/', {}, ['1440-claro', '390-claro']],
    ['entrada-detalhe-chefe', ca, '/estoque/entradas/2/', {}, grupoClaroEscuro],
    ['entrada-detalhe-estornada', ca, '/estoque/entradas/5/', {}, ['1440-claro', '1440-escuro', '390-claro']],
    ['entrada-detalhe-sem-emitente', fa, '/estoque/entradas/3/', {}, ['1440-claro']],
    ['entrada-estorno', ca, '/estoque/entradas/2/estorno/', {}, grupoClaroEscuro],
    ['entrada-estorno-bloqueado', ca, '/estoque/entradas/4/estorno/', {}, ['1440-claro', '1440-escuro', '390-claro']],
    ['entrada-estorno-processando', ca, '/estoque/entradas/2/estorno/', { processando: 'form[action$="/estorno/"]' }, ['1440-claro', '390-claro']],
  ];
  for (const [nome, papel, url, extra, cenarios] of p4) {
    for (const cenario of cenarios) {
      const [largura, variante] = cenario.split('-');
      const size = { 1440: '1440x900', 1280: '1280x800', 820: '820x1180', 390: '390x844' }[largura];
      const touch = ['820', '390'].includes(largura);
      captures.push(capture(`${nome}-${cenario}`, papel, size, variante === 'escuro' ? 'dark' : 'light', url, touch, null, extra));
    }
  }
  for (const [prefix, role, url] of [
    ['usuarios-admin', 'administrador-sistema', '/organizacao/usuarios/'],
  ]) {
    for (const theme of ['light', 'dark']) captures.push(capture(`${prefix}-1440-${theme}-herdada`, role, '1440x900', theme, url));
  }
  await mkdir(output, { recursive: true });
  let previous = [];
  try { previous = JSON.parse(await readFile(`${output}/captures.json`, 'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }

  const results = [];
  for (const capture of onlyInteractions ? [] : captures.filter(item => !selectedNames || selectedNames.some(nome => nome.endsWith('*') ? item.name.startsWith(nome.slice(0, -1)) : nome === item.name))) {
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
      if (capture.roteiro) await roteiros[capture.roteiro](page);
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
      if (evidence.scrollW > width) {
        // Diagnóstico do overflow horizontal da página: quem passa da largura do alvo e não está contido num rolável, mais os
        // posicionados (absolute/fixed: um `visually-hidden` numa coluna fora da vista dentro de `.table-wrapper` alarga a página).
        const culpados = await page.evaluate(`(() => {
          const contido = n => { for (let a = n.parentElement; a && a !== document.body; a = a.parentElement) if (getComputedStyle(a).overflowX !== 'visible') return true; return false; };
          return [...document.querySelectorAll('body *')].filter(n => n.getBoundingClientRect().right > ${width} + 1 && (!contido(n) || ['absolute', 'fixed'].includes(getComputedStyle(n).position))).slice(0, 8).map(n => n.tagName + '.' + n.className + ' ' + Math.round(n.getBoundingClientRect().right));
        })()`);
        console.error(`Overflow horizontal em ${capture.name}: ${JSON.stringify(culpados)}`);
      }
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
    // P4 — estoque. Nada é gravado: só buscas, escolha de emitente, adicionar item e "Revisar" (POST em
    // `/estoque/entradas/nova/`, que compõe e valida sem gravar). O formulário de confirmar a entrada e o de estornar
    // só têm o estado de processamento provocado por `provocarProcessamento` (action trocada, método GET, submit
    // cancelado, interceptação por CDP): nenhum botão de efeito é clicado.
    const instalarContador = () => page.evaluate("window.__smokeOriginalBody = document.body; window.__swaps = 0; document.body.addEventListener('htmx:after:settle', () => { window.__swaps++; }); void 0");
    const teclarEnter = async () => {
      await page.call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' });
      await page.call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    };
    const composicao = async () => {
      await ir('/estoque/entradas/nova/?dev_como=funcionario-almoxarifado', "!!document.querySelector('#id_busca_emitente') && !!document.querySelector('#entrada-composicao form')");
      await instalarContador();
    };
    await composicao();
    await passoHtmx(page, preencher('#id_busca_emitente', 'ltda') + acionarBotao('acao', 'buscar_emitente'), 'buscar emitente');
    await check('Entrada: busca de emitente por HTMX troca só a composição, sem shell duplicado', "document.body===window.__smokeOriginalBody && document.querySelectorAll('.side').length===1 && document.querySelectorAll('main').length===1 && !!document.querySelector('#entrada-composicao form') && !!document.querySelector('button[name=escolher_emitente]') && !document.querySelector('#entrada-composicao #entrada-indicador') && !!document.querySelector('#entrada-indicador')");
    await composicao();
    await page.evaluate("document.querySelector('#id_busca_emitente').value = 'ltda'; document.querySelector('#id_busca_emitente').focus(); void 0");
    const antesEnterEmitente = await swapsAteAgora(page);
    await teclarEnter();
    await aguardarSwap(page, antesEnterEmitente, 'Enter na busca de emitente');
    await check('Entrada: Enter na busca de emitente aciona a busca e não Revisar', "!!document.querySelector('button[name=escolher_emitente]') && !document.querySelector('.error-box') && !document.querySelector('#resumo-heading')");
    await composicao();
    await page.evaluate("document.querySelector('#id_busca_material').value = '000.000.002'; document.querySelector('#id_busca_material').focus(); void 0");
    const antesEnterMaterial = await swapsAteAgora(page);
    await teclarEnter();
    await aguardarSwap(page, antesEnterMaterial, 'Enter na busca de material');
    await check('Entrada: Enter na busca de material aciona a busca e não Revisar', "!!document.querySelector('button[name=adicionar_material]') && !document.querySelector('.error-box') && !document.querySelector('#resumo-heading')");
    await passoHtmx(page, clicar('button[name="adicionar_material"]'), 'adicionar material');
    await check('Entrada: material adicionado leva o foco à quantidade da linha', "document.activeElement?.matches('input[inputmode=decimal]') && document.querySelectorAll('input[inputmode=decimal]').length===1");
    await composicao();
    await passoHtmx(page, acionarBotao('acao', 'revisar'), 'revisar vazio');
    await check('Entrada: Revisar vazio mostra erros de campo e geral e foca o primeiro campo inválido', "document.activeElement?.id==='id_motivo' && document.querySelector('#id_motivo').getAttribute('aria-invalid')==='true' && !!document.querySelector('.error-box[role=alert]') && document.querySelectorAll('.field-error').length>=3");
    await composicao();
    await page.evaluate(`(() => { const m = document.querySelector('#id_motivo'); m.value = 'COMPRA'; m.dispatchEvent(new Event('change', { bubbles: true })); ${preencher('#id_numero_documento', 'NF-000321/2026')} })(); void 0`);
    await passoHtmx(page, preencher('#id_busca_emitente', 'ltda') + acionarBotao('acao', 'buscar_emitente'), 'buscar emitente');
    await passoHtmx(page, clicar('button[name="escolher_emitente"]'), 'escolher emitente');
    await passoHtmx(page, acionarBotao('acao', 'revisar'), 'revisar sem itens');
    await check('Entrada: só erro geral (sem itens) leva o foco à caixa de erro', "document.activeElement?.matches('.error-box[role=alert]') && !document.querySelector('[aria-invalid=true]:not([type=hidden])')");
    await composicao();
    await roteiros.revisao(page);
    await check('Entrada: Revisar troca a composição pela revisão não gravada, com foco no título e rótulo da consequência', "(() => { const b = document.querySelector('form[action$=\"/entradas/nova/confirmar/\"] [data-processing-submit]'); return document.activeElement?.id==='resumo-heading' && document.querySelector('#resumo-heading').textContent.includes('Não gravada') && !!document.querySelector('.alert-info[role=status]') && b.textContent.trim().replace(/\\s+/g, ' ')==='Confirmar entrada: 2 itens' && document.querySelectorAll('.confirmation-bar-card form').length===2 && document.querySelectorAll('.side').length===1 && document.querySelectorAll('main').length===1 && document.body===window.__smokeOriginalBody; })()");
    await page.evaluate("window.__antesDoEnvio = true; document.querySelector('input[name=acao][value=voltar]').form.requestSubmit(); void 0");
    await esperarNovaPagina(page, 'Voltar e corrigir');
    await check('Entrada: Voltar e corrigir preserva cabeçalho, emitente e itens', "(() => { const q = [...document.querySelectorAll('input[inputmode=decimal]')].map(i => i.value); return location.pathname==='/estoque/entradas/nova/' && q.length===2 && q[0]==='12,5' && q[1]==='3' && document.querySelector('#id_numero_documento').value==='NF-000321/2026' && !!document.querySelector('.estoque-emitente-escolhido') && !document.querySelector('#resumo-heading'); })()");
    await instalarContador();
    await passoHtmx(page, acionarBotao('acao', 'revisar'), 'revisar de novo');
    await delay(650);
    await provocarProcessamento(page, 'form[action$="/entradas/nova/confirmar/"]');
    await check('Entrada: confirmação em processamento (Confirmando…, desabilitada, Voltar desabilitado), sem envio', "(() => { const f = document.querySelector('[data-captura-processando]'); const voltar = document.querySelector('input[name=acao][value=voltar]').form.querySelector('button'); return f.querySelector('[data-processing-submit-label]').textContent==='Confirmando…' && f.querySelector('[data-processing-submit]').disabled && f.getAttribute('aria-busy')==='true' && voltar.disabled && location.pathname==='/estoque/entradas/nova/'; })()");
    // P4, rodada 3 — o Confirmar da revisão ignora a ativação logo depois da troca (o primário cai no ponto do último
    // clique em viewports baixas). Nada é gravado: o form de confirmação ganha, assim que entra no DOM, a action da
    // própria página, método GET e um `preventDefault`; a interceptação por CDP falha qualquer POST de efeito.
    const armarConfirmacao = `(() => {
      window.__env = { submits: 0, imediato: null };
      new MutationObserver(() => {
        const f = document.querySelector('form[action$="/entradas/nova/confirmar/"]');
        if (!f || f.__armado) return;
        f.__armado = true;
        f.setAttribute('action', location.pathname); f.setAttribute('method', 'get');
        f.addEventListener('submit', e => { window.__env.submits++; e.preventDefault(); });
        f.requestSubmit(); // segunda ativação no mesmo instante da troca
        window.__env.imediato = { submits: window.__env.submits, ariaBusy: f.getAttribute('aria-busy'), disabled: f.querySelector('[data-processing-submit]').disabled };
      }).observe(document.getElementById('entrada-composicao'), { childList: true });
    })(); void 0`;
    const clicarEm = async (x, y) => {
      await page.call('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
      await page.call('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
      await page.call('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
    };
    for (const [largura, altura, movel, ancora] of [[1440, 520, false, 'r.bottom - 5'], [390, 600, true, 'r.y + r.height / 2']]) {
      await page.call('Emulation.setDeviceMetricsOverride', { width: largura, height: altura, deviceScaleFactor: 1, mobile: movel });
      await page.call('Emulation.setTouchEmulationEnabled', { enabled: movel, maxTouchPoints: movel ? 5 : 1 });
      await composicao();
      await roteiros.montar(page);
      await page.evaluate(armarConfirmacao);
      await page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight); void 0');
      await delay(150);
      const revisar = await page.evaluate(`(() => { const r = document.querySelector('button[name=acao][value=revisar]').getBoundingClientRect(); return { x: r.x + r.width / 2, y: ${ancora} }; })()`);
      const antes = await swapsAteAgora(page);
      await clicarEm(revisar.x, revisar.y); // gesto real de Revisar
      await aguardarSwap(page, antes, `revisar ${largura}x${altura}`);
      const sob = await page.evaluate(`(() => { const e = document.elementFromPoint(${revisar.x}, ${revisar.y}); return !!e?.closest('[data-processing-submit]'); })()`);
      await check(`Entrada ${largura}x${altura}: o primário da revisão cai no ponto do clique de Revisar`, String(sob));
      await check(`Entrada ${largura}x${altura}: Confirmar ignora a ativação logo após a troca (sem Confirmando…, sem desabilitar)`, "(() => { const f = document.querySelector('[data-processing-form]'); return window.__env.imediato.submits===1 && window.__env.imediato.ariaBusy===null && window.__env.imediato.disabled===false && f.getAttribute('aria-busy')===null && !f.querySelector('[data-processing-submit]').disabled; })()");
      await clicarEm(revisar.x, revisar.y); // segundo clique, ainda dentro da janela
      await check(`Entrada ${largura}x${altura}: o segundo clique no mesmo ponto também é ignorado`, "(() => { const f = document.querySelector('[data-processing-form]'); return window.__env.submits===2 && f.getAttribute('aria-busy')===null && !f.querySelector('[data-processing-submit]').disabled; })()");
      await delay(650);
      await clicarEm(revisar.x, revisar.y); // depois da janela, o envio é aceito (Confirmando…) — sem gravar: GET + preventDefault + barreira
      await check(`Entrada ${largura}x${altura}: depois da janela o Confirmar volta a aceitar o envio (Confirmando…)`, "(() => { const f = document.querySelector('[data-processing-form]'); return window.__env.submits===3 && f.getAttribute('aria-busy')==='true' && f.querySelector('[data-processing-submit]').disabled && f.querySelector('[data-processing-submit-label]').textContent==='Confirmando…'; })()");
    }
    // P4, rodada 3 — erro de quantidade na 2ª linha: o campo e o texto do erro ficam dentro da área visível do wrapper.
    for (const [largura, altura, movel] of [[390, 844, true], [1440, 900, false]]) {
      await page.call('Emulation.setDeviceMetricsOverride', { width: largura, height: altura, deviceScaleFactor: 1, mobile: movel });
      await page.call('Emulation.setTouchEmulationEnabled', { enabled: movel, maxTouchPoints: movel ? 5 : 1 });
      await composicao();
      await roteiros.montar(page, ['12,5', 'abc']);
      await passoHtmx(page, acionarBotao('acao', 'revisar'), 'revisar com quantidade inválida na 2ª linha');
      await delay(200);
      await check(`Entrada ${largura}: erro de quantidade focado e visível no wrapper, com o texto do erro`, "(() => { const c = document.activeElement; const w = c.closest('.table-wrapper'); const e = c.closest('td').querySelector('.field-error'); const W = w.getBoundingClientRect(), C = c.getBoundingClientRect(), E = e.getBoundingClientRect(); return c.getAttribute('aria-invalid')==='true' && C.left>=W.left-1 && C.right<=W.right+1 && E.left>=W.left-1 && E.right<=W.right+1 && C.top>=0 && E.bottom<=innerHeight && document.documentElement.scrollWidth<=innerWidth; })()");
    }
    await page.call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    await page.call('Emulation.setTouchEmulationEnabled', { enabled: false, maxTouchPoints: 1 });
    // P4, rodada 3 — emitente já escolhido com a busca de troca aberta: um só "Remover emitente" visível, junto de
    // "Buscar emitente", a busca na largura do card e o estado aberto no próprio botão.
    await composicao();
    await roteiros.montar(page);
    await check('Emitente escolhido (fechado): nome · código · documento num só fragmento e Remover ao lado do Trocar', "(() => { const p = document.querySelector('.estoque-emitente-escolhido'); const remover = [...document.querySelectorAll('button[value=limpar_emitente]')].filter(b => b.checkVisibility()); const sum = document.querySelector('.estoque-busca-recolhida > summary'); return !!p.querySelector('.estoque-emitente-nome') && p.querySelectorAll('.table-cell-code').length===2 && remover.length===1 && remover[0].getBoundingClientRect().left>sum.getBoundingClientRect().right && sum.textContent.trim()==='Trocar emitente'; })()");
    await passoHtmx(page, "document.querySelector('.estoque-busca-recolhida > summary').click();" + preencher('#id_busca_emitente', 'IMPLANTAÇÃO') + acionarBotao('acao', 'buscar_emitente'), 'buscar emitente para trocar');
    await check('Emitente em troca (aberto): busca na largura do card, um só Remover junto de Buscar e estado no summary', "(() => { const d = document.querySelector('.estoque-busca-recolhida'); const card = d.closest('.card'); const cs = getComputedStyle(card); const util = card.getBoundingClientRect().width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 2; const remover = [...document.querySelectorAll('button[value=limpar_emitente]')].filter(b => b.checkVisibility()); const buscar = d.querySelector('button[value=buscar_emitente]'); const sum = d.querySelector('summary'); const sb = getComputedStyle(sum); return d.open && sum.textContent.trim()==='Trocar emitente' && sb.fontWeight==='600' && getComputedStyle(sum,'::before').content.includes('▾') && d.getBoundingClientRect().width>=util-2 && remover.length===1 && d.contains(remover[0]) && Math.abs(remover[0].getBoundingClientRect().top-buscar.getBoundingClientRect().top)<4; })()");

    await ir('/estoque/entradas/2/estorno/?dev_como=chefe-almoxarifado', "!!document.querySelector('form[action$=\"/estorno/\"]')");
    await check('Estorno: aviso de consequência, justificativa rotulada e primário destrutivo com a consequência', "(() => { const b = document.querySelector('form[action$=\"/estorno/\"] [data-processing-submit]'); return !!document.querySelector('.alert-warning:not([role])') && b.classList.contains('btn-danger') && !document.querySelector('.btn-primary') && b.textContent.trim().replace(/\\s+/g, ' ')==='Estornar entrada #2: 3 itens' && document.querySelector('label[for=id_justificativa]')?.textContent.trim()!=='' && document.querySelectorAll('.table-row-error').length===0; })()");
    await provocarProcessamento(page, 'form[action$="/estorno/"]');
    await check('Estorno: em processamento (Estornando…, desabilitado, Cancelar desabilitado), sem envio', "(() => { const f = document.querySelector('[data-captura-processando]'); const cancelar = [...document.querySelectorAll('.confirmation-bar a.btn')].find(a => a.textContent.trim()==='Cancelar'); return f.querySelector('[data-processing-submit-label]').textContent==='Estornando…' && f.querySelector('[data-processing-submit]').disabled && f.getAttribute('aria-busy')==='true' && cancelar.getAttribute('aria-disabled')==='true' && /\\/estorno\\/$/.test(location.pathname); })()");
    await ir('/estoque/entradas/4/estorno/?dev_como=chefe-almoxarifado', "!!document.querySelector('.error-box[role=alert]')");
    await check('Estorno bloqueado por saldo: selo no h1, erro antes do Registro, linha marcada com texto, sem barra de confirmação e só o link de volta', "(() => { const erro = document.querySelector('.error-box[role=alert]'); const registro = document.querySelector('#registro-titulo').closest('section'); const voltar = [...document.querySelectorAll('main a.btn')].filter(a => a.textContent.trim()==='Voltar à entrada #4'); return document.querySelector('h1 .badge.badge-warning')?.textContent.trim()==='Bloqueado' && document.querySelectorAll('.error-box[role=alert]').length===1 && !!(erro.compareDocumentPosition(registro) & Node.DOCUMENT_POSITION_FOLLOWING) && document.querySelectorAll('.table-row-error').length===1 && document.querySelector('.table-row-error').textContent.includes('Ficaria negativo.') && !document.querySelector('form[action$=\"/estorno/\"]') && !document.querySelector('.confirmation-bar') && voltar.length===1 && getComputedStyle(voltar[0].parentElement).position!=='sticky' && document.querySelectorAll('main .btn').length===1; })()");
    await ir('/estoque/entradas/5/?dev_como=chefe-almoxarifado', "!!document.querySelector('h1 .badge')");
    await check('Entrada estornada: selo "Estornada" neutro (badge-neutral), não de perigo', "document.querySelector('h1 .badge')?.textContent.trim()==='Estornada' && document.querySelector('h1 .badge').classList.contains('badge-neutral') && !document.querySelector('.badge-danger')");
    await ir('/estoque/entradas/2/?dev_como=chefe-almoxarifado', "!!document.querySelector('#registro-titulo')");
    await check('Registro: emitente com nome · código · documento em mono (um fragmento)', "(() => { const dd = [...document.querySelectorAll('.estoque-kv dt')].find(t => t.textContent==='Emitente').nextElementSibling; const codigos = [...dd.querySelectorAll('.table-cell-code')]; return !!dd.querySelector('.estoque-emitente-nome') && codigos.length===2 && codigos.every(c => getComputedStyle(c).fontFamily!==getComputedStyle(dd).fontFamily); })()");
    await ir('/estoque/entradas/?dev_como=auditor', "!!document.querySelector('[data-linha-clicavel]')");
    await check('Entradas (auditor): consulta sem nenhuma ação de registro', "!document.querySelector('main a[href$=\"/entradas/nova/\"]') && !document.querySelector('.tools a') && document.querySelectorAll('[data-linha-clicavel]').length>=1");
    await ir('/estoque/entradas/?dev_como=funcionario-almoxarifado', "!!document.querySelector('[data-linha-clicavel]')");
    await check('Entradas (funcionário): ação Registrar entrada em tools', "!!document.querySelector('.tools a.btn-secondary[href$=\"/entradas/nova/\"]')");
    await page.evaluate("document.querySelector('[data-linha-clicavel] td:nth-child(3)').click()");
    await waitFor("document.readyState==='complete' && /\\/estoque\\/entradas\\/\\d+\\/$/.test(location.pathname)");
    await check('Entradas: clique na linha abre o detalhe, sem ação de estorno para o funcionário', "/\\/estoque\\/entradas\\/\\d+\\/$/.test(location.pathname) && document.querySelectorAll('.side').length===1 && !document.querySelector('a[href$=\"/estorno/\"]')");
    await ir('/estoque/entradas/2/?dev_como=chefe-almoxarifado', "!!document.querySelector('h1')");
    await check('Entrada (chefe): detalhe com convite destrutivo secundário', "!!document.querySelector('.tools a.btn-secondary.btn-secondary-danger[href$=\"/estorno/\"]') && !document.querySelector('.tools .btn-primary')");
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
  // Barreira de dados: toda requisição não-GET às URLs de efeito que o roteiro tentou (e a interceptação falhou).
  console.log(`Requisições barradas pela interceptação CDP: ${BLOQUEADAS.length}${BLOQUEADAS.length ? '\n  ' + [...new Set(BLOQUEADAS)].join('\n  ') : ''}`);
  if (browser) { try { await browser.call('Browser.close'); } catch {} browser.close(); }
  chrome.kill();
  await delay(200);
  await rm(profile, { recursive: true, force: true });
  await rm(insumos, { recursive: true, force: true });
}
