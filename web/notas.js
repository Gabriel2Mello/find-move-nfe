'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="notas-token"]').content;
const pagina = crypto.randomUUID(), presenca = new AbortController();
let ocupado = false, encerrado = false, carregado = false, enviando = false, saindo = false;
let assinaturaEstado = '';
function temaAtual() {return document.documentElement.dataset.tema || (matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro');}
function atualizarTema() {$('tema').textContent = temaAtual() === 'escuro' ? 'Tema claro' : 'Tema escuro';}
try {const salvo = localStorage.getItem('notas-tema'); if (['claro','escuro'].includes(salvo)) document.documentElement.dataset.tema = salvo;} catch {}
atualizarTema();
$('tema').addEventListener('click', () => {const tema = temaAtual() === 'escuro' ? 'claro' : 'escuro'; document.documentElement.dataset.tema = tema; try {localStorage.setItem('notas-tema', tema);} catch {} atualizarTema();});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', atualizarTema);
function avisar(texto, erro = false) {$('status').textContent = texto; $('status').classList.toggle('erro', erro);}
function botoes() {
  $('buscar').disabled = $('mover').disabled = !carregado || ocupado || enviando || encerrado;
  $('cancelar').disabled = !ocupado || encerrado;
  for (const campo of document.querySelectorAll('input,textarea')) campo.disabled = ocupado || enviando || encerrado;
}
async function pedir(rota, dados) {
  const resposta = await fetch(rota, {method:dados ? 'POST' : 'GET', cache:'no-store', signal:AbortSignal.timeout(10000), headers:{'X-Notas-Token':token, ...(dados ? {'Content-Type':'application/json'} : {})}, body:dados ? JSON.stringify(dados) : undefined});
  const resultado = await resposta.json(); if (!resposta.ok) throw Error(resultado.erro || 'Não foi possível concluir.'); return resultado;
}
function receber(estado) {
  const assinatura = JSON.stringify([estado.ocupado, estado.encerrando, estado.acao, estado.logs, estado.resultado]);
  if (assinatura === assinaturaEstado) return;
  assinaturaEstado = assinatura;
  ocupado = estado.ocupado;
  if (estado.encerrando) {encerrado = true; avisar('Encerrando com segurança. O arquivo em andamento será concluído.');}
  else if (ocupado) avisar(estado.acao === 'buscar' ? 'Buscando e copiando notas…' : 'Movendo e organizando notas…');
  else if (estado.resultado) avisar(estado.resultado.erro ? 'A operação encontrou um erro.' : estado.resultado.cancelado ? 'Operação interrompida. Os arquivos concluídos foram preservados.' : estado.resultado.erros ? 'Operação concluída com erros. Confira o registro.' : 'Operação concluída.', !!(estado.resultado.erro || estado.resultado.erros));
  $('logs').textContent = estado.logs.join('\n');
  const r = estado.resultado;
  $('resumo').textContent = r && !r.erro ? `${r.encontrados} arquivo(s) encontrado(s) · ${r.concluidos} concluído(s) · ${r.ignorados} já existente(s) · ${r.erros} erro(s)${r.nao_encontradas.length ? ' · Notas não encontradas: ' + r.nao_encontradas.join(', ') : ''}` : '';
  botoes();
}
async function iniciar(acao) {
  if (ocupado || enviando || encerrado) return;
  if (acao === 'mover' && !confirm('Mover as notas informadas nas pastas de origem para ano e mês? A data de modificação de cada arquivo será usada.')) return;
  enviando = true; botoes();
  try {
    await pedir('/api/iniciar', {acao, notas:$('notas').value, destino:$('destino').value, caminhos:[0,1,2,3].map(i => $('caminho-' + i).value)});
    receber(await pedir('/api/estado'));
  } catch (erro) {avisar(erro.message, true);} finally {enviando = false; botoes();}
}
$('buscar').addEventListener('click', () => iniciar('buscar'));
$('mover').addEventListener('click', () => iniciar('mover'));
$('cancelar').addEventListener('click', async () => {try {await pedir('/api/cancelar', {}); avisar('Parada solicitada. Concluindo o arquivo atual…');} catch (erro) {avisar(erro.message, true);}});
$('encerrar').addEventListener('click', async () => {
  try {await pedir('/api/encerrar', {}); encerrado = true; presenca.abort(); botoes(); $('encerrar').disabled = true; avisar('Encerramento solicitado. A operação para após concluir o arquivo atual. Você pode fechar esta aba.');}
  catch (erro) {avisar(erro.message, true);}
});
async function acompanhar() {
  while (!encerrado && !saindo) {
    try {
      const resposta = await fetch('/api/presenca', {headers:{'X-Notas-Token':token, 'X-Notas-Pagina':pagina}, signal:presenca.signal});
      if (!resposta.ok || !resposta.body) throw Error('Sem conexão.');
      const leitor = resposta.body.getReader(), decoder = new TextDecoder(); let buffer = '';
      while (!encerrado && !saindo) {
        const {value,done} = await leitor.read(); if (done) break;
        buffer += decoder.decode(value, {stream:true}); let fim;
        while ((fim = buffer.indexOf('\n\n')) !== -1) {const evento = buffer.slice(0,fim); buffer = buffer.slice(fim+2); if (evento.startsWith('data: ')) receber(JSON.parse(evento.slice(6)));}
      }
    } catch {}
    if (!encerrado && !saindo) {
      try {receber(await pedir('/api/estado'));} catch {encerrado = true; avisar('A ferramenta deixou de responder. Reabra pelo Hub Nunes.', true); botoes();}
      if (!encerrado) await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
}
window.addEventListener('pagehide', () => {saindo = true; presenca.abort(); if (!encerrado) fetch('/api/fechar-pagina', {method:'POST', keepalive:true, headers:{'Content-Type':'application/json','X-Notas-Token':token}, body:JSON.stringify({pagina})});});
window.addEventListener('pageshow', evento => {if (evento.persisted) location.reload();});
(async () => {
  try {const config = await pedir('/api/configuracao'); $('notas').value = config.notas; $('destino').value = config.destino; config.caminhos.forEach((c,i) => $('caminho-' + i).value = c); carregado = true; avisar('Pronta para buscar ou mover notas.'); botoes(); acompanhar();}
  catch (erro) {avisar(erro.message, true);}
})();
