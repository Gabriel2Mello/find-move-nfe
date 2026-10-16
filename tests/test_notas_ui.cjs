const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function interfaceTeste() {
  const elementos = new Map();
  let escritas = 0;
  const elemento = id => {
    if (!elementos.has(id)) elementos.set(id, {
      texto:'', disabled:false, classList:{toggle(){}}, addEventListener(){},
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
    window:{addEventListener(){}}, fetch:()=>new Promise(()=>{}), setTimeout
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/notas.js'),'utf8'), contexto);
  return {elemento, escritas:()=>escritas, receber:estado=> {
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
