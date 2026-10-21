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
      texto:'', value:'', disabled:false, classList:{toggle(){}},
      eventos:new Map(), addEventListener(nome, fn){this.eventos.set(nome, fn);},
      set textContent(valor) {this.texto=valor; escritas++;},
      get textContent() {return this.texto;}
    });
    return elementos.get(id);
  };
  const contexto = vm.createContext({
    document:{getElementById:elemento, querySelector:()=>({content:'teste'}),
      querySelectorAll:()=>[], documentElement:{dataset:{}}},
    localStorage:{getItem:()=>null}, matchMedia:()=>({matches:false,addEventListener(){}}),
    crypto:{randomUUID:()=> 'pagina-teste'}, AbortController, AbortSignal,
    window:{addEventListener:(nome, fn)=>eventos.set(nome, fn)},
    fetch:opcoes.fetch || (()=>new Promise(()=>{})), setTimeout,
    confirm:()=>true
  });
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
