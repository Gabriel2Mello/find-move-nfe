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
      texto:'', value:'', dataset:{}, tagName:id === 'tema' ? 'BUTTON' : 'INPUT', setAttribute(){}, disabled:false, classList:{toggle(){}},
      eventos:new Map(), addEventListener(nome, fn){
        const anterior = this.eventos.get(nome);
        this.eventos.set(nome, anterior ? (...args)=>{anterior(...args); return fn(...args);} : fn);
      },
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
  assert.match(ui.elemento('resumo').textContent,/1 concluído/);
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
  assert.match(ui.elemento('resumo').textContent, /1 concluído/);
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

test('tooltip do destino fecha com Escape e reabre por mouse ou foco', () => {
  const ui = interfaceTeste(), dica = ui.elemento('dica-destino');
  ui.eventos.get('keydown')({key:'Escape'});
  assert.equal(dica.dataset.fechada, 'true');
  dica.eventos.get('focusin')();
  assert.equal(dica.dataset.fechada, undefined);
  ui.eventos.get('keydown')({key:'Escape'});
  dica.eventos.get('mouseenter')();
  assert.equal(dica.dataset.fechada, undefined);
});
