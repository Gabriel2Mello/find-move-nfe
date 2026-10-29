const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function interfaceTeste(opcoes = {}) {
  const elementos = new Map();
  const eventos = new Map();
  let escritas = 0;
  const elemento = id => {
    if (!elementos.has(id)) elementos.set(id, {
      texto:'', value:'', dataset:{}, atributos:{}, tagName:id === 'tema' ? 'BUTTON' : 'INPUT', setAttribute(nome, valor){this.atributos[nome]=valor;}, disabled:false, classList:{toggle(){}},
      eventos:new Map(), addEventListener(nome, fn){
        const anterior = this.eventos.get(nome);
        this.eventos.set(nome, anterior ? (...args)=>{anterior(...args); return fn(...args);} : fn);
      },
      showModal(){this.open=true;}, close(){this.open=false;},
      selectionStart:0, selectionEnd:0, selectionDirection:'none', scrollTop:0, scrollLeft:0,
      setSelectionRange(inicio, fim, direcao){this.selectionStart=inicio;this.selectionEnd=fim;this.selectionDirection=direcao;},
      set textContent(valor) {this.texto=valor; escritas++;},
      get textContent() {return this.texto;}
    });
    return elementos.get(id);
  };
  const contexto = vm.createContext({
    document:{cookie:opcoes.cookie || '', getElementById:elemento, querySelector:seletor=>({content:opcoes.metas?.[seletor.match(/name="([^"]+)"/)?.[1]] || ''}),
      querySelectorAll:()=>[], documentElement:{dataset:{}, setAttribute(nome, valor){this.dataset.tema=valor;}, removeAttribute(){delete this.dataset.tema;}}},
    localStorage:{getItem:()=>opcoes.temaLegado || null, setItem(){}}, matchMedia:()=>({matches:false,addEventListener(){}}),
    crypto:{randomUUID:()=> 'pagina-teste'}, AbortController, AbortSignal,
    window:{addEventListener:(nome, fn)=>eventos.set(nome, fn)},
    fetch:opcoes.fetch || (()=>new Promise(()=>{})), setTimeout:opcoes.setTimeout || setTimeout,
    confirm:opcoes.confirm || (()=>true)
  });
  contexto.registrarEvento = (nome, fn)=>eventos.set(nome, fn);
  vm.runInContext('window = globalThis; window.addEventListener = registrarEvento;', contexto);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/nunes-tema.js'),'utf8'), contexto);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/notas.js'),'utf8'), contexto);
  return {elemento, eventos, contexto, avaliar:codigo=>vm.runInContext(codigo, contexto),
    escritas:()=>escritas, receber:estado=> {
    contexto.estadoTeste=estado;
    vm.runInContext('receber(estadoTeste)',contexto);
  }};
}

test('estado ocioso repetido e contagem de abas não reescrevem a interface', () => {
  const ui=interfaceTeste();
  const estado={ocupado:false,encerrando:false,acao:'',logs:[],resultado:null,paginas:1};
  ui.receber(estado);
  const antes=ui.escritas();
  ui.receber({...estado,paginas:2});
  ui.receber(estado);
  assert.equal(ui.escritas(),antes);
});

test('alterar destino salva sem iniciar operação e mostra falha de gravação', async () => {
  const pedidos = [];
  let falhar = false;
  const ui = interfaceTeste({fetch:(rota, opcoes)=> {
    if (!opcoes.body) return new Promise(()=>{});
    pedidos.push({rota, ...opcoes});
    return Promise.resolve({ok:!falhar, json:async()=>falhar ? {erro:'Sem permissão.'} : {ok:true}});
  }});
  ui.elemento('destino').value = 'C:\\cópias';
  await ui.elemento('destino').eventos.get('change')();
  assert.equal(pedidos.length, 1);
  assert.equal(pedidos[0].rota, '/api/configuracao');
  assert.equal(JSON.parse(pedidos[0].body).destino, 'C:\\cópias');
  assert.equal(pedidos[0].keepalive, true);
  assert.match(ui.elemento('ajuda-destino').textContent, /Pasta salva/);
  falhar = true;
  ui.elemento('destino').value = 'outra';
  await ui.elemento('destino').eventos.get('change')();
  assert.match(ui.elemento('ajuda-destino').textContent, /Não foi possível salvar.*Sem permissão/);
  assert.equal(ui.avaliar('destinoSalvo'), 'C:\\cópias');
});

test('fechar a aba salva o destino editado mesmo sem sair do campo', async () => {
  const pedidos = [];
  const ui = interfaceTeste({fetch:(rota, opcoes)=> {
    if (!opcoes.body) return new Promise(()=>{});
    pedidos.push({rota, ...opcoes});
    return Promise.resolve({ok:true, json:async()=>({ok:true})});
  }});
  ui.avaliar("carregado = true; destinoSalvo = 'anterior';");
  ui.elemento('destino').value = 'nova pasta';
  ui.eventos.get('pagehide')();
  assert.deepEqual(pedidos.map(p=>p.rota), ['/api/configuracao', '/api/fechar-pagina']);
  assert.equal(JSON.parse(pedidos[0].body).destino, 'nova pasta');
  assert.equal(pedidos[0].keepalive, true);
});

test('respostas fora de ordem e retorno ao destino anterior preservam a última edição', async () => {
  const pendentes = [];
  const ui = interfaceTeste({fetch:(rota, opcoes)=> {
    if (!opcoes.body) return new Promise(()=>{});
    return new Promise(resolve=>pendentes.push({dados:JSON.parse(opcoes.body), resolve}));
  }});
  ui.avaliar("destinoSalvo = 'anterior';");
  ui.elemento('destino').value = 'novo';
  const primeiro = ui.elemento('destino').eventos.get('change')();
  ui.elemento('destino').value = 'anterior';
  const segundo = ui.elemento('destino').eventos.get('change')();
  assert.equal(pendentes.length, 2);
  assert.ok(pendentes[1].dados.revisao > pendentes[0].dados.revisao);
  const resposta = {ok:true, json:async()=>({ok:true})};
  pendentes[1].resolve(resposta);
  await segundo;
  pendentes[0].resolve(resposta);
  await primeiro;
  assert.equal(ui.avaliar('destinoSalvo'), 'anterior');
});

test('conclusão de nova operação e erros ou cancelamento não retrocedem por resposta antiga', () => {
  for (const resultado of [
    {erro:'falha sintética'},
    {encontrados:0, concluidos:0, ignorados:0, erros:0, cancelado:true, nao_encontradas:[]},
    {encontrados:1, concluidos:0, ignorados:0, erros:1, nao_encontradas:[]}
  ]) {
    const ui = interfaceTeste();
    const estado = {versao:4, ocupado:false, encerrando:false, acao:'mover', logs:[], resultado};
    ui.receber(estado);
    const final = ui.elemento('status').textContent;
    ui.receber({...estado, versao:3, ocupado:true, resultado:null});
    assert.equal(ui.elemento('status').textContent, final);
    ui.receber({...estado, versao:5, ocupado:true, resultado:null});
    assert.match(ui.elemento('status').textContent, /Movendo/);
    ui.receber(estado);
    assert.match(ui.elemento('status').textContent, /Movendo/);
  }
});

test('conclusão atualiza uma vez e preserva o resultado enquanto ocioso', () => {
  const ui=interfaceTeste();
  const estado={ocupado:true,encerrando:false,acao:'buscar',logs:[],resultado:null};
  ui.receber(estado);
  assert.match(ui.elemento('status').textContent,/Buscando/);
  const fim={...estado,ocupado:false,logs:['Copiado: teste.pdf'],resultado:{
    encontrados:1,concluidos:1,ignorados:0,erros:0,nao_encontradas:[]}};
  ui.receber(fim);
  assert.equal(ui.elemento('status').textContent,'Operação concluída.');
  assert.equal(ui.elemento('resumo').hidden, false);
  assert.equal(ui.elemento('total-concluidos').textContent, 1);
  const antes=ui.escritas();
  ui.receber(JSON.parse(JSON.stringify(fim)));
  assert.equal(ui.escritas(),antes);
  assert.equal(ui.elemento('logs').textContent,'Copiado: teste.pdf');
});

test('resposta antiga de estado não recoloca Movendo após conclusão recebida pela presença', () => {
  const ui = interfaceTeste();
  const movendo = {versao:1, ocupado:true, encerrando:false, acao:'mover', logs:[], resultado:null};
  const fim = {...movendo, versao:3, ocupado:false, logs:['Movido: teste.pdf'], resultado:{
    encontrados:1, concluidos:1, ignorados:0, erros:0, nao_encontradas:[]}};
  ui.receber(movendo);
  ui.receber(fim);
  ui.receber(movendo);
  assert.equal(ui.elemento('status').textContent, 'Operação concluída.');
  assert.equal(ui.elemento('cancelar').disabled, true);
  assert.equal(ui.elemento('resumo').hidden, false);
  assert.equal(ui.elemento('total-concluidos').textContent, 1);
  assert.equal(ui.elemento('logs').textContent, 'Movido: teste.pdf');
});

const estadoOcioso = {versao:1, ocupado:false, encerrando:false, acao:'', logs:[], resultado:null};
const resposta = dados => ({ok:true, json:async()=>dados});
const pendente = () => new Promise(()=>{});

test('início com resposta perdida bloqueia repetição até consulta válida, sem reenviar ação', async () => {
  const pedidos = [], esperas = [];
  let falharEstado = true;
  const ui = interfaceTeste({setTimeout:fn=>esperas.push(fn), fetch:async (rota, opcoes)=> {
    pedidos.push(rota);
    if (rota === '/api/iniciar') throw Error('Resposta perdida.');
    if (rota === '/api/estado') {
      if (falharEstado) throw Error('Sem conexão.');
      return resposta({...estadoOcioso, versao:2, ocupado:true, acao:'buscar'});
    }
    return pendente();
  }});
  ui.avaliar("carregado = true; destinoSalvo = ''; conectado = true;");
  await ui.elemento('buscar').eventos.get('click')();
  assert.equal(ui.elemento('buscar').disabled, true);
  assert.equal(ui.avaliar('encerrado'), false);
  await ui.elemento('buscar').eventos.get('click')();
  assert.equal(pedidos.filter(p=>p==='/api/iniciar').length, 1);
  ui.receber(estadoOcioso);
  assert.equal(ui.elemento('buscar').disabled, true, 'presença não resolve um POST sem confirmação');
  falharEstado = false;
  await ui.avaliar('consultarEstado()');
  assert.equal(ui.avaliar('inicioIncerto'), false);
  assert.equal(ui.elemento('buscar').disabled, true, 'operação continua ocupada');
  ui.receber({...estadoOcioso, versao:3});
  assert.equal(ui.elemento('buscar').disabled, false);
  assert.equal(pedidos.filter(p=>p==='/api/iniciar').length, 1);
  ui.avaliar('saindo = true');
  esperas.forEach(fn=>fn());
});

test('consulta iniciada antes do POST não libera operação de resultado incerto', async () => {
  let liberar;
  const ui = interfaceTeste({fetch:rota=>rota === '/api/estado' ? new Promise(resolve=>liberar=resolve) : pendente()});
  ui.avaliar('conectado = true; carregado = true; enviando = true; inicioIncerto = true; geracaoInicio = 1;');
  const consulta = ui.avaliar('consultarEstado()');
  ui.avaliar('enviando = false;');
  liberar(resposta(estadoOcioso));
  await consulta;
  assert.equal(ui.avaliar('inicioIncerto'), true);
  assert.equal(ui.elemento('buscar').disabled, true);
});

test('primeira falha de conexão conserva interface e recupera estado por leitura', async () => {
  let falhar = true;
  const ui = interfaceTeste({fetch:rota=>rota !== '/api/estado' ? pendente() : falhar ? Promise.reject(Error('offline')) : Promise.resolve(resposta(estadoOcioso))});
  ui.avaliar('carregado = true; conectado = true;');
  await ui.avaliar('consultarEstado()');
  assert.equal(ui.avaliar('encerrado'), false);
  assert.equal(ui.elemento('buscar').disabled, true);
  assert.match(ui.elemento('status').textContent, /Tentando reconectar/);
  falhar = false;
  await ui.avaliar('consultarEstado()');
  assert.equal(ui.elemento('buscar').disabled, false);
  assert.match(ui.elemento('status').textContent, /Pronta/);
});

test('estado inválido ou antigo não libera início incerto', async () => {
  let estado = {ocupado:false};
  const ui = interfaceTeste({fetch:rota=>rota === '/api/estado' ? Promise.resolve(resposta(estado)) : pendente()});
  ui.avaliar('carregado = true; inicioIncerto = true;');
  await ui.avaliar('consultarEstado()');
  assert.equal(ui.avaliar('inicioIncerto'), true);
  ui.receber({...estadoOcioso, versao:4});
  const statusAtual = ui.elemento('status').textContent;
  estado = {...estadoOcioso, versao:3};
  await ui.avaliar('consultarEstado()');
  assert.equal(ui.avaliar('inicioIncerto'), true);
  assert.equal(ui.elemento('status').textContent, statusAtual);
});

test('cancelar diálogo nativo mantém campos e envia somente identificação do campo', async () => {
  const pedidos = [];
  let resultado = {alterado:false};
  const ui = interfaceTeste({metas:{'notas-desktop':'1'}, fetch:(rota, opcoes)=> {
    if (rota !== '/api/escolher-pasta') return pendente();
    pedidos.push({rota, ...opcoes});
    return Promise.resolve(resposta(resultado));
  }});
  ui.avaliar("carregado = true; conectado = true; destinoSalvo = 'C:\\\\cópias';");
  ui.elemento('destino').value = 'C:\\cópias';
  ui.elemento('caminho-0').value = 'origem anterior';
  await ui.avaliar("escolherPasta('destino')");
  assert.equal(ui.elemento('destino').value, 'C:\\cópias');
  assert.deepEqual(JSON.parse(pedidos[0].body), {campo:'destino'});
  assert.equal(pedidos[0].signal, undefined, 'diálogo não expira durante escolha');
  resultado = {alterado:true, campo:'caminho-0', pasta:'nova origem'};
  await ui.avaliar("escolherPasta('caminho-0')");
  assert.equal(ui.elemento('caminho-0').value, 'nova origem');
  assert.equal(ui.elemento('destino').value, 'C:\\cópias');
  resultado = {alterado:true, campo:'destino', pasta:'novo destino'};
  await ui.avaliar("escolherPasta('destino')");
  assert.equal(ui.avaliar('destinoSalvo'), 'novo destino');
  assert.equal(pedidos.length, 3);
});

test('tema backend tem precedência ao legado e alterações são persistidas', async () => {
  const pedidos = [];
  const ui = interfaceTeste({metas:{'notas-tema':'claro','notas-desktop':'1'}, temaLegado:'escuro', fetch:(rota, opcoes)=> {
    if (rota !== '/api/tema') return pendente();
    pedidos.push(JSON.parse(opcoes.body));
    return Promise.resolve(resposta({ok:true}));
  }});
  assert.equal(ui.avaliar('document.documentElement.dataset.tema'), 'claro');
  assert.equal(ui.elemento('tema').textContent, 'Tema escuro');
  await ui.elemento('tema').eventos.get('click')();
  assert.deepEqual(pedidos, [{tema:'escuro'}]);
  assert.equal(ui.avaliar('document.documentElement.dataset.tema'), 'escuro');
  const legado = interfaceTeste({temaLegado:'claro'});
  assert.equal(legado.avaliar('document.documentElement.dataset.tema'), 'claro');
});

test('encerrar confirma uma vez se ocupado e cancelamento não envia pedido', async () => {
  let confirmacoes = 0, aceitar = false;
  const pedidos = [];
  const ui = interfaceTeste({confirm:()=>{confirmacoes++; return aceitar;}, fetch:(rota, opcoes)=> {
    if (!opcoes.body) return pendente();
    pedidos.push(rota);
    return Promise.resolve(resposta({ok:true}));
  }});
  ui.avaliar("carregado = true; conectado = true; ocupado = true; destinoSalvo = '';");
  await ui.elemento('encerrar').eventos.get('click')();
  assert.equal(confirmacoes, 1);
  assert.deepEqual(pedidos, []);
  aceitar = true;
  await ui.elemento('encerrar').eventos.get('click')();
  assert.equal(confirmacoes, 2);
  assert.deepEqual(pedidos, ['/api/encerrar']);
  assert.equal(ui.avaliar('encerrado'), true);
  await ui.elemento('encerrar').eventos.get('click')();
  assert.equal(confirmacoes, 2);
});

test('diálogo espera gravação anterior do destino antes de abrir e persistir escolha', async () => {
  let liberarGravacao;
  const pedidos = [];
  const ui = interfaceTeste({metas:{'notas-desktop':'1'}, fetch:(rota, opcoes)=> {
    if (!opcoes.body) return pendente();
    pedidos.push(rota);
    if (rota === '/api/configuracao') return new Promise(resolve=>liberarGravacao=resolve);
    return Promise.resolve(resposta({alterado:true,campo:'destino',pasta:'pasta nativa'}));
  }});
  ui.avaliar("carregado = true; conectado = true; destinoSalvo = 'anterior';");
  ui.elemento('destino').value = 'edição manual';
  const salvando = ui.elemento('destino').eventos.get('change')();
  const escolhendo = ui.avaliar("escolherPasta('destino')");
  assert.deepEqual(pedidos, ['/api/configuracao']);
  liberarGravacao(resposta({ok:true}));
  await salvando;
  await escolhendo;
  assert.deepEqual(pedidos, ['/api/configuracao','/api/escolher-pasta']);
  assert.equal(ui.elemento('destino').value, 'pasta nativa');
  assert.equal(ui.avaliar('destinoSalvo'), 'pasta nativa');
});

test('desktop sem preferência inicia claro e conserva legado válido', async () => {
  const padrao = interfaceTeste({metas:{'notas-desktop':'1'}});
  assert.equal(padrao.avaliar('document.documentElement.dataset.tema'), 'claro');
  const legado = interfaceTeste({metas:{'notas-desktop':'1'}, temaLegado:'escuro'});
  assert.equal(legado.avaliar('document.documentElement.dataset.tema'), 'escuro');
  const cookie = interfaceTeste({metas:{'notas-desktop':'1'}, cookie:'notas-tema=escuro', temaLegado:'claro'});
  assert.equal(cookie.avaliar('document.documentElement.dataset.tema'), 'escuro');
  const pedidos = [];
  const web = interfaceTeste({fetch:rota=>{pedidos.push(rota); return pendente();}});
  await web.elemento('tema').eventos.get('click')();
  assert.equal(pedidos.includes('/api/tema'), false, 'modo web usa somente preferência legada');
});

test('configuração inválida mantém diagnóstico e permite recuperação explícita pelo destino', async () => {
  const pedidos = [], esperas = [];
  let recuperado = false;
  const ui = interfaceTeste({metas:{'notas-desktop':'1'}, setTimeout:fn=>esperas.push(fn), fetch:async (rota, opcoes)=> {
    pedidos.push(rota);
    if (rota === '/api/configuracao' && !opcoes.body) {
      if (!recuperado) return {ok:false,json:async()=>({erro:'Preferências inválidas. Confira .local/preferencias.json.'})};
      return resposta({notas:'1234', destino:'pasta recuperada', caminhos:['a','b','c','d']});
    }
    if (rota === '/api/estado') return resposta(estadoOcioso);
    if (rota === '/api/escolher-pasta') {
      recuperado = true;
      return resposta({alterado:true,campo:'destino',pasta:'pasta recuperada'});
    }
    return pendente();
  }});
  await new Promise(setImmediate);
  assert.match(ui.elemento('status').textContent, /Preferências inválidas.*preferencias.json.*escolha novamente/);
  assert.equal(ui.elemento('buscar').disabled, true);
  assert.equal(ui.avaliar('carregado'), false);
  await ui.avaliar("escolherPasta('destino')");
  assert.equal(pedidos.filter(p=>p==='/api/configuracao').length, 1, 'não grava campo vazio antes da escolha explícita');
  assert.equal(ui.elemento('destino').value, 'pasta recuperada');
  esperas.shift()();
  await new Promise(setImmediate);
  assert.equal(ui.avaliar('carregado'), true);
  assert.equal(ui.elemento('notas').value, '');
  assert.equal(ui.elemento('buscar').disabled, false);
});

test('abertura inicia notas vazias mesmo se um backend anterior devolver conteúdo legado', async () => {
  const ui = interfaceTeste({fetch:async rota => {
    if (rota === '/api/configuracao') return resposta({notas:'1234',destino:'cópias',caminhos:['a','b','c','d']});
    if (rota === '/api/estado') return resposta(estadoOcioso);
    return pendente();
  }});
  await new Promise(setImmediate);
  assert.equal(ui.avaliar('carregado'), true);
  assert.equal(ui.elemento('notas').value, '');
  ui.elemento('notas').value = '7; 25';
  ui.receber({...estadoOcioso,versao:2});
  assert.equal(ui.elemento('notas').value, '7; 25', 'atualizações preservam a edição manual');
});

test('configurações fecham por Escape, clique ou foco externo e preservam interação interna', () => {
  const ui = interfaceTeste(), menu = ui.elemento('configuracoes');
  const interno = ui.elemento('caminho-0'), externo = ui.elemento('notas');
  menu.contains = alvo => alvo === interno || alvo === menu;
  for (const evento of ['pointerdown', 'focusin']) {
    menu.open = true;
    ui.eventos.get(evento)({target:interno});
    assert.equal(menu.open, true);
    ui.eventos.get(evento)({target:menu});
    assert.equal(menu.open, true);
    ui.eventos.get(evento)({target:externo});
    assert.equal(menu.open, false);
  }
  menu.open = true;
  ui.eventos.get('keydown')({key:'Escape'});
  assert.equal(menu.open, false);
  assert.equal(ui.elemento('notas'), externo, 'fechar não substitui campos nem seu conteúdo');
});

test('efeito de tema começa apenas na troca manual e mantém nome acessível da próxima ação', async () => {
  const ui = interfaceTeste({metas:{'notas-tema':'claro'}});
  assert.equal(ui.avaliar('document.documentElement.dataset.temaAnimado'), undefined);
  await ui.elemento('tema').eventos.get('click')();
  assert.equal(ui.avaliar('document.documentElement.dataset.temaAnimado'), '1');
  assert.equal(ui.avaliar('document.documentElement.dataset.tema'), 'escuro');
  assert.equal(ui.elemento('tema').textContent, 'Tema claro');
  assert.equal(ui.elemento('tema').atributos['aria-label'], 'Ativar tema claro');
  await ui.elemento('tema').eventos.get('click')();
  assert.equal(ui.avaliar('document.documentElement.dataset.tema'), 'claro');
  assert.equal(ui.elemento('tema').textContent, 'Tema escuro');
  assert.equal(ui.elemento('tema').atributos['aria-label'], 'Ativar tema escuro');
});

test('cartões refletem todos os totais e preservam notas não encontradas e registro', () => {
  const ui = interfaceTeste();
  const estado = {versao:1, ocupado:false, encerrando:false, acao:'buscar', logs:['Registro sintético'], resultado:{
    encontrados:20, concluidos:17, ignorados:2, erros:1, nao_encontradas:['0007','0012']}};
  ui.receber(estado);
  assert.equal(ui.elemento('resumo').hidden, false);
  for (const [campo, total] of Object.entries({encontrados:20, concluidos:17, ignorados:2, erros:1})) {
    assert.equal(ui.elemento('total-' + campo).textContent, total);
  }
  assert.equal(ui.elemento('notas-nao-encontradas').textContent, 'Notas não encontradas: 0007, 0012');
  assert.equal(ui.elemento('logs').textContent, 'Registro sintético');
  ui.receber({...estado, versao:2, resultado:{...estado.resultado, encontrados:0, concluidos:0, ignorados:0, erros:0, nao_encontradas:[]}});
  for (const campo of ['encontrados','concluidos','ignorados','erros']) assert.equal(ui.elemento('total-' + campo).textContent, 0);
  assert.equal(ui.elemento('notas-nao-encontradas').textContent, '');
  for (const resultado of [null, {erro:'Falha sintética'}]) {
    ui.receber({...estado, versao:3, resultado});
    assert.equal(ui.elemento('resumo').hidden, true);
    assert.equal(ui.elemento('total-encontrados').textContent, '');
    assert.equal(ui.elemento('notas-nao-encontradas').textContent, '');
  }
});

test('busca e movimento mostram cartões em andamento; limpeza conserva apenas o resumo final', () => {
  for (const acao of ['buscar','mover','limpar']) {
    const ui = interfaceTeste();
    const estado = {versao:1, ocupado:true, encerrando:false, acao, logs:[], resultado:null};
    ui.elemento('notas').value = '1234';
    ui.receber(estado);
    if (acao === 'limpar') {
      assert.equal(ui.elemento('resumo').hidden, true);
      ui.receber({...estado, versao:2, andamento:{encontrados:6, concluidos:2, ignorados:0, erros:0}});
      assert.equal(ui.elemento('resumo').hidden, true);
      ui.receber({...estado, versao:3, ocupado:false, resultado:{encontrados:6, concluidos:6, ignorados:0, erros:0, nao_encontradas:[]}});
      assert.equal(ui.elemento('resumo').hidden, false);
      assert.equal(ui.elemento('total-concluidos').textContent, 6);
      assert.equal(ui.elemento('resumo').dataset.finalizado, 'true');
      continue;
    }
    assert.equal(ui.elemento('resumo').hidden, false);
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'false');
    for (const campo of ['encontrados','concluidos','ignorados','erros']) assert.equal(ui.elemento('total-' + campo).textContent, 0);
    const andamento = {encontrados:6, concluidos:2, ignorados:1, erros:1};
    ui.receber({...estado, versao:2, andamento});
    for (const [campo, valor] of Object.entries(andamento)) assert.equal(ui.elemento('total-' + campo).textContent, valor);
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'false');
    assert.equal(ui.elemento('notas').value, '1234');
    ui.receber(estado);
    assert.equal(ui.elemento('total-concluidos').textContent, 2);
    ui.receber({...estado, versao:3, ocupado:false, andamento, resultado:{...andamento, concluidos:4, nao_encontradas:[], cancelado:true}});
    assert.equal(ui.elemento('total-concluidos').textContent, 4);
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'true');
    ui.receber({...estado, versao:4});
    assert.equal(ui.elemento('total-concluidos').textContent, 0);
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'false');
  }
});

test('cartões destacam apenas resultado final e ignoram estados antigos', () => {
  const ui = interfaceTeste();
  const resultado = {encontrados:2, concluidos:1, ignorados:0, erros:1, nao_encontradas:[]};
  const estado = {versao:1, ocupado:true, encerrando:false, acao:'buscar', logs:[], resultado};
  ui.receber(estado);
  assert.equal(ui.elemento('resumo').dataset.finalizado, 'false');
  for (const fim of [resultado, {...resultado, erros:0}, {...resultado, cancelado:true}]) {
    ui.receber({...estado, versao:2, ocupado:false, resultado:fim});
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'true');
    ui.receber(estado);
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'true');
  }
  ui.receber({...estado, versao:3, resultado:null});
  assert.equal(ui.elemento('resumo').dataset.finalizado, 'false');
  for (const resultado of [null, {erro:'Falha sintética'}]) {
    ui.receber({...estado, versao:4, ocupado:false, resultado});
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'false');
  }
});

test('Buscar, Mover e Limpar retiram destaque dos cartões antes de enviar a execução', async () => {
  for (const acao of ['buscar','mover','limpar']) {
    let enviado = false;
    const ui = interfaceTeste({fetch:rota => {
      if (rota === '/api/preparar-limpeza') return Promise.resolve(resposta({quantidade:1, destino:'C:\\Teste', confirmacao:'sintetica'}));
      if (rota === '/api/iniciar' || rota === '/api/limpar') {
        assert.equal(ui.elemento('resumo').dataset.finalizado, 'false');
        enviado = true;
        return Promise.resolve(resposta({ok:true}));
      }
      if (rota === '/api/estado') return Promise.resolve(resposta({...estadoOcioso, versao:2, ocupado:true, acao}));
      return pendente();
    }});
    ui.avaliar("carregado = true; destinoSalvo = '';");
    ui.receber({...estadoOcioso, resultado:{encontrados:1, concluidos:1, ignorados:0, erros:0, nao_encontradas:[]}});
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'true');
    await ui.elemento(acao).eventos.get('click')();
    assert.equal(enviado, true);
    assert.equal(ui.elemento('resumo').dataset.finalizado, 'false');
  }
});

test('ajuda abre e fecha sem alterar notas ou iniciar uma operação', () => {
  const pedidos=[];
  const ui=interfaceTeste({fetch:rota=>{pedidos.push(rota);return pendente();}});
  ui.elemento('notas').value='1234\n5678';
  ui.elemento('configuracoes').open=true;
  ui.elemento('ajuda-acoes').eventos.get('click')();
  assert.equal(ui.elemento('dialogo-acoes').open,true);
  assert.equal(ui.elemento('configuracoes').open,false);
  ui.elemento('fechar-ajuda').eventos.get('click')();
  assert.equal(ui.elemento('dialogo-acoes').open,false);
  assert.equal(ui.elemento('notas').value,'1234\n5678');
  assert.equal(pedidos.includes('/api/iniciar'),false);
});

test('contador acompanha digitação, colagem e limpeza com notas válidas sem repetição', () => {
  const pedidos=[];
  const ui=interfaceTeste({fetch:rota=>{pedidos.push(rota);return pendente();}});
  const campo=ui.elemento('notas'), contador=ui.elemento('contagem-notas');
  assert.equal(contador.textContent,'Contagem: 0');
  for (const [valor,total] of [
    ['1',1], ['12',1], ['12, 7; 0007\n0012\t9999',3],
    ['8098\r\n8402\n8403\n8404\n9593\n9594\n9595\n8440\n8441\n8405',10],
    ['12345, 0, 0000, 25',2], [' \n\t,; ',0], ['',0]
  ]) {
    campo.value=valor;
    campo.eventos.get('input')();
    assert.equal(contador.textContent,'Contagem: '+total);
  }
  assert.equal(pedidos.includes('/api/iniciar'),false);
});

test('Notas bloqueia letras e outros caracteres inválidos antes da inserção', () => {
  const ui=interfaceTeste(), campo=ui.elemento('notas');
  campo.value='1234\n5678';campo.eventos.get('input')();
  campo.setSelectionRange(1,3,'backward');
  for (const texto of ['a','Z','á','字','🙂','12A34','1234\ntexto\n5678','-','.']) {
    let bloqueado=false;
    campo.eventos.get('beforeinput')({data:texto,cancelable:true,preventDefault(){bloqueado=true;}});
    assert.equal(bloqueado,true,texto);
    assert.equal(campo.value,'1234\n5678');
    assert.equal(campo.selectionStart,1);
    assert.equal(campo.selectionEnd,3);
  }
  for (const texto of ['0','1234\n5678',' ,;\t\n',null]) {
    let bloqueado=false;
    campo.eventos.get('beforeinput')({data:texto,cancelable:true,preventDefault(){bloqueado=true;}});
    assert.equal(bloqueado,false,String(texto));
  }
  let bloqueado=false;
  campo.eventos.get('beforeinput')({data:null,dataTransfer:{getData:()=> '12A34'},cancelable:true,preventDefault(){bloqueado=true;}});
  assert.equal(bloqueado,true);
});

test('colagem inválida sem beforeinput cancelável restaura conteúdo, seleção, rolagem e contagem', () => {
  const pedidos=[], ui=interfaceTeste({fetch:rota=>{pedidos.push(rota);return pendente();}});
  const campo=ui.elemento('notas');
  campo.value='1234\n5678';campo.eventos.get('input')();
  campo.setSelectionRange(1,3,'backward');campo.scrollTop=42;campo.scrollLeft=7;
  campo.eventos.get('beforeinput')({data:null,cancelable:false});
  campo.value='12A34\n5678';campo.setSelectionRange(5,5,'none');campo.scrollTop=0;campo.scrollLeft=0;
  campo.eventos.get('input')();
  assert.equal(campo.value,'1234\n5678');
  assert.deepEqual([campo.selectionStart,campo.selectionEnd,campo.selectionDirection],[1,3,'backward']);
  assert.deepEqual([campo.scrollTop,campo.scrollLeft],[42,7]);
  assert.equal(ui.elemento('contagem-notas').textContent,'Contagem: 2');
  assert.equal(pedidos.includes('/api/iniciar'),false);
});

test('edições válidas, exclusão e desfazer preservam o cursor e o texto informado', () => {
  const ui=interfaceTeste(),campo=ui.elemento('notas');
  for (const [texto,cursor] of [['1234',2],['1564',3],['14',1],['1564',3],['0012, 7;\n5678',12],['',0]]) {
    campo.eventos.get('beforeinput')({data:null,cancelable:true});
    campo.value=texto;campo.setSelectionRange(cursor,cursor,'none');
    campo.eventos.get('input')();
    assert.equal(campo.value,texto);
    assert.equal(campo.selectionStart,cursor);
    assert.equal(campo.selectionEnd,cursor);
  }
  campo.eventos.get('beforeinput')({data:'a',cancelable:false});
  campo.value='a';campo.eventos.get('input')();
  assert.equal(campo.value,'','conteúdo anterior não reaparece depois de limpar');
  assert.equal(ui.elemento('contagem-notas').textContent,'Contagem: 0');
});

test('Abrir envia a pasta atual de cada campo sem alterar seleção ou executar operação', async () => {
  const pedidos=[];
  const ui=interfaceTeste({metas:{'notas-desktop':'1'},fetch:(rota,opcoes)=>{
    if (rota!=='/api/abrir-pasta') return pendente();
    pedidos.push(JSON.parse(opcoes.body));
    return Promise.resolve(resposta({ok:true}));
  }});
  ui.avaliar("carregado=true; conectado=true; destinoSalvo='anterior';");
  for (const campo of ['destino','caminho-0','caminho-1','caminho-2','caminho-3']) {
    ui.elemento(campo).value='  C:\\Pasta editada '+campo+'  ';
    await ui.avaliar("abrirPasta('"+campo+"')");
    assert.deepEqual(pedidos.at(-1),{campo,pasta:'C:\\Pasta editada '+campo});
    assert.equal(ui.elemento(campo).value,'  C:\\Pasta editada '+campo+'  ');
  }
  assert.equal(pedidos.length,5);
  assert.equal(ui.avaliar('destinoSalvo'),'anterior');
  assert.equal(ui.avaliar('selecionando'),false);
});

test('Abrir bloqueia cliques repetidos e informa falha liberando os controles', async () => {
  let liberar;
  let pedidos=0;
  const ui=interfaceTeste({metas:{'notas-desktop':'1'},fetch:rota=>{
    if (rota!=='/api/abrir-pasta') return pendente();
    pedidos++;
    return new Promise(resolve=>liberar=resolve);
  }});
  ui.avaliar('carregado=true; conectado=true;');
  ui.elemento('destino').value='C:\\Pasta';
  const abertura=ui.avaliar("abrirPasta('destino')");
  assert.equal(ui.avaliar('selecionando'),true);
  assert.equal(ui.elemento('buscar').disabled,true);
  await ui.avaliar("abrirPasta('destino')");
  assert.equal(pedidos,1);
  liberar({ok:false,json:async()=>({erro:'Pasta indisponível.'})});
  await abertura;
  assert.match(ui.elemento('status').textContent,/Não foi possível abrir a pasta: Pasta indisponível/);
  assert.equal(ui.avaliar('selecionando'),false);
  assert.equal(ui.elemento('buscar').disabled,false);
  const web=interfaceTeste();
  web.avaliar('carregado=true; conectado=true;');
  await web.avaliar("abrirPasta('destino')");
  assert.equal(web.avaliar('selecionando'),false);
});

function prepararCampoLimpeza(ui) {
  ui.avaliar("carregado=true; conectado=true; destinoSalvo='C:\\\\copias';");
  ui.elemento('destino').value='C:\\copias';
  ui.elemento('notas').value='1234\n5678';
  ui.elemento('notas').eventos.get('input')();
}
const planoLimpeza={destino:'C:\\copias',quantidade:2,confirmacao:'confirmacao-sintetica'};
const fimLimpeza={...estadoOcioso,versao:5,acao:'limpar',logs:['Excluído: teste.pdf'],resultado:{
  encontrados:2,concluidos:2,ignorados:0,erros:0,cancelado:false,nao_encontradas:[],limpeza_id:'limpeza-1'}};

test('Limpar com pasta vazia limpa somente Notas, sem confirmação nem exclusão', async () => {
  const pedidos=[];
  let confirmacoes=0;
  const ui=interfaceTeste({confirm:()=>{confirmacoes++;return true;},fetch:async rota=>{
    pedidos.push(rota);
    return rota==='/api/preparar-limpeza' ? resposta({...planoLimpeza,quantidade:0}) : pendente();
  }});
  prepararCampoLimpeza(ui);
  await ui.elemento('limpar').eventos.get('click')();
  assert.equal(confirmacoes,0);
  assert.equal(pedidos.includes('/api/limpar'),false);
  assert.equal(ui.elemento('notas').value,'');
  assert.equal(ui.elemento('contagem-notas').textContent,'Contagem: 0');
});

test('cancelar Limpar conserva notas, contagem e arquivos sem enviar execução', async () => {
  const pedidos=[];
  let mensagem='';
  const ui=interfaceTeste({confirm:texto=>{mensagem=texto;return false;},fetch:async rota=>{
    pedidos.push(rota);
    return rota==='/api/preparar-limpeza' ? resposta(planoLimpeza) : pendente();
  }});
  prepararCampoLimpeza(ui);
  await ui.elemento('limpar').eventos.get('click')();
  assert.match(mensagem,/Excluir permanentemente 2 arquivo/);
  assert.ok(mensagem.includes('C:\\copias'));
  assert.equal(pedidos.includes('/api/limpar'),false);
  assert.equal(ui.elemento('notas').value,'1234\n5678');
  assert.equal(ui.elemento('contagem-notas').textContent,'Contagem: 2');
});

test('limpeza confirmada envia só autorização e limpa Notas uma vez após sucesso', async () => {
  const pedidos=[];
  const ui=interfaceTeste({fetch:async (rota,opcoes)=>{
    if(rota==='/api/preparar-limpeza') return resposta(planoLimpeza);
    if(rota==='/api/limpar') {pedidos.push(JSON.parse(opcoes.body));return resposta({ok:true});}
    if(rota==='/api/estado') return resposta(fimLimpeza);
    return pendente();
  }});
  prepararCampoLimpeza(ui);
  await ui.elemento('limpar').eventos.get('click')();
  assert.deepEqual(pedidos,[{confirmacao:'confirmacao-sintetica'}]);
  assert.equal(ui.elemento('notas').value,'');
  assert.equal(ui.elemento('contagem-notas').textContent,'Contagem: 0');
  assert.equal(ui.elemento('rotulo-concluidos').textContent,'Excluídos');
  ui.elemento('notas').value='9999';
  ui.elemento('notas').eventos.get('input')();
  ui.avaliar('conectado=false;');
  ui.receber({...fimLimpeza,versao:6,logs:[...fimLimpeza.logs,'Estatística confirmada.']});
  assert.equal(ui.elemento('notas').value,'9999','reconexão e novos logs não apagam uma nova edição');
});

test('limpeza com erro ou cancelamento preserva Notas e preparação inválida não as apaga', async () => {
  for (const resultado of [{...fimLimpeza.resultado,erros:1},{...fimLimpeza.resultado,cancelado:true},{erro:'falha'}]) {
    const ui=interfaceTeste();
    prepararCampoLimpeza(ui);
    ui.receber({...fimLimpeza,resultado});
    assert.equal(ui.elemento('notas').value,'1234\n5678');
  }
  const ui=interfaceTeste({fetch:async rota=>rota==='/api/preparar-limpeza' ? resposta({ok:true}) : pendente()});
  prepararCampoLimpeza(ui);
  await ui.elemento('limpar').eventos.get('click')();
  assert.equal(ui.elemento('notas').value,'1234\n5678');
  assert.match(ui.elemento('status').textContent,/Preparação da limpeza inválida/);
});

test('resposta perdida da limpeza bloqueia repetição e reconcilia sem excluir novamente', async () => {
  const esperas=[];
  let inicios=0, falharEstado=true;
  const ui=interfaceTeste({setTimeout:fn=>esperas.push(fn),fetch:async rota=>{
    if(rota==='/api/preparar-limpeza') return resposta(planoLimpeza);
    if(rota==='/api/limpar') {inicios++;throw Error('Resposta perdida.');}
    if(rota==='/api/estado') {if(falharEstado) throw Error('Sem conexão.');return resposta(fimLimpeza);}
    return pendente();
  }});
  prepararCampoLimpeza(ui);
  await ui.elemento('limpar').eventos.get('click')();
  assert.equal(ui.elemento('limpar').disabled,true);
  await ui.elemento('limpar').eventos.get('click')();
  assert.equal(inicios,1);
  falharEstado=false;
  await ui.avaliar('consultarEstado()');
  assert.equal(ui.elemento('notas').value,'');
  assert.equal(inicios,1);
  ui.avaliar('saindo=true;');
  esperas.forEach(fn=>fn());
});
