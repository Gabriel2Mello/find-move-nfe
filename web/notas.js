'use strict';
const $ = id => document.getElementById(id);
const meta = nome => document.querySelector(`meta[name="${nome}"]`)?.content || '';
const token = meta('notas-token'), desktop = meta('notas-desktop') === '1';
const pagina = crypto.randomUUID(), presenca = new AbortController();
let ocupado = false, encerrado = false, carregado = false, enviando = false, saindo = false;
let conectado = false, inicioIncerto = false, selecionando = false, encerrando = false;
let geracaoInicio = 0;
let assinaturaEstado = '', versaoEstado = -1, destinoSalvo = null, revisaoDestino = 0, salvamentosDestino = 0;
const destinosPendentes = new Set();
const dicaDestino = $('dica-destino');
for (const evento of ['mouseenter', 'focusin']) dicaDestino.addEventListener(evento, () => {delete dicaDestino.dataset.fechada;});
window.addEventListener('keydown', evento => {
  if (evento.key === 'Escape') dicaDestino.dataset.fechada = 'true';
});
function lerTemaLegado() {
  const valido = valor => ['claro','escuro'].includes(valor);
  try {
    const item = document.cookie.split(';').map(parte => parte.trim()).find(parte => parte.startsWith('notas-tema='));
    const valor = item ? decodeURIComponent(item.slice('notas-tema='.length)) : '';
    if (valido(valor)) return valor;
  } catch {}
  try {const valor = localStorage.getItem('notas-tema'); if (valido(valor)) return valor;} catch {}
  return '';
}
const temaLegado = lerTemaLegado();
const tema = window.NunesTema.iniciar({controle:$('tema'), chave:'notas-tema', cookie:true});
const temaSalvo = meta('notas-tema');
if (['claro','escuro'].includes(temaSalvo)) tema.aplicar(temaSalvo, true);
else if (desktop && !temaLegado) tema.aplicar('claro');
let salvamentoTema = Promise.resolve();
$('tema').addEventListener('click', () => {
  if (!desktop) return;
  const preferencia = document.documentElement.dataset.tema;
  // Mantém a ordem das gravações mesmo em cliques rápidos.
  salvamentoTema = salvamentoTema.catch(() => {}).then(async () => {
    try {await pedir('/api/tema', {tema:preferencia}); $('tema-status').textContent = '';}
    catch (erro) {$('tema-status').textContent = 'Tema aplicado, mas não foi salvo: ' + erro.message;}
  });
  return salvamentoTema;
});
function avisar(texto, erro = false) {$('status').textContent = texto; $('status').classList.toggle('erro', erro);}
function botoes() {
  const bloqueado = !carregado || !conectado || ocupado || enviando || inicioIncerto || selecionando || encerrando || encerrado;
  $('buscar').disabled = $('mover').disabled = bloqueado;
  $('cancelar').disabled = !conectado || !ocupado || encerrando || encerrado;
  $('encerrar').disabled = selecionando || encerrando || encerrado;
  for (const campo of document.querySelectorAll('input,textarea')) campo.disabled = !carregado || ocupado || enviando || inicioIncerto || selecionando || encerrando || encerrado;
  for (const botao of document.querySelectorAll('[data-campo]')) {
    const recuperarDestino = desktop && botao.dataset.campo === 'destino' && !carregado && conectado && !ocupado && !selecionando && !encerrando && !encerrado;
    botao.disabled = bloqueado && !recuperarDestino;
  }
}
async function pedir(rota, dados, keepalive = false, semPrazo = false) {
  const resposta = await fetch(rota, {method:dados ? 'POST' : 'GET', cache:'no-store', keepalive, signal:semPrazo ? undefined : AbortSignal.timeout(10000), headers:{'X-Notas-Token':token, ...(dados ? {'Content-Type':'application/json'} : {})}, body:dados ? JSON.stringify(dados) : undefined});
  const resultado = await resposta.json(); if (!resposta.ok) throw Error(resultado.erro || 'Não foi possível concluir.'); return resultado;
}
function salvarDestino() {
  const tarefa = gravarDestino();
  destinosPendentes.add(tarefa);
  tarefa.finally(() => destinosPendentes.delete(tarefa));
  return tarefa;
}
async function gravarDestino() {
  const destino = $('destino').value.trim();
  if (destino === destinoSalvo && !salvamentosDestino) return true;
  const revisao = ++revisaoDestino;
  salvamentosDestino++;
  try {
    await pedir('/api/configuracao', {destino, pagina, revisao}, true);
    if (revisao === revisaoDestino) {
      destinoSalvo = destino;
      $('ajuda-destino').textContent = 'Pasta salva para as próximas aberturas.';
    }
    return true;
  } catch (erro) {
    if (revisao === revisaoDestino) $('ajuda-destino').textContent = 'Não foi possível salvar a pasta: ' + erro.message;
    return false;
  } finally {salvamentosDestino--;}
}
$('destino').addEventListener('change', salvarDestino);
async function escolherPasta(campo) {
  if (!desktop || selecionando || ocupado || enviando || inicioIncerto || encerrando || encerrado || (!carregado && campo !== 'destino') || !conectado) return;
  selecionando = true; botoes();
  try {
    await Promise.all([...destinosPendentes]);
    if (carregado && campo === 'destino' && !await salvarDestino()) return;
    // O diálogo pode ficar aberto indefinidamente. O servidor escolhe a pasta inicial.
    const resultado = await pedir('/api/escolher-pasta', {campo}, false, true);
    if (resultado.alterado === true && resultado.campo === campo && typeof resultado.pasta === 'string') {
      $(campo).value = resultado.pasta;
      if (campo === 'destino') {
        destinoSalvo = resultado.pasta;
        $('ajuda-destino').textContent = 'Pasta salva para as próximas aberturas.';
        if (!carregado) avisar('Pasta salva. Recarregando configurações…');
      }
    }
  } catch (erro) {avisar('Não foi possível escolher a pasta: ' + erro.message, true);}
  finally {selecionando = false; botoes();}
}
for (const botao of document.querySelectorAll('[data-campo]')) {
  botao.hidden = !desktop;
  botao.addEventListener('click', () => escolherPasta(botao.dataset.campo));
}
function receber(estado) {
  if (!estado || typeof estado.ocupado !== 'boolean' || typeof estado.encerrando !== 'boolean' || !Array.isArray(estado.logs)) return false;
  // GET e presença podem terminar em outra ordem. Nunca reaplicar um estado antigo.
  if (Number.isInteger(estado.versao)) {
    if (estado.versao < versaoEstado) return false;
    versaoEstado = estado.versao;
  }
  const recuperando = !conectado;
  conectado = true;
  const assinatura = JSON.stringify([estado.ocupado, estado.encerrando, estado.acao, estado.logs, estado.resultado]);
  if (assinatura === assinaturaEstado && !recuperando) {botoes(); return true;}
  assinaturaEstado = assinatura;
  ocupado = estado.ocupado;
  if (estado.encerrando) {encerrado = true; avisar('Encerrando com segurança. O arquivo em andamento será concluído.');}
  else if (ocupado) avisar(estado.acao === 'buscar' ? 'Buscando e copiando notas…' : 'Movendo e organizando notas…');
  else if (estado.resultado) avisar(estado.resultado.erro ? 'A operação encontrou um erro.' : estado.resultado.cancelado ? 'Operação interrompida. Os arquivos concluídos foram preservados.' : estado.resultado.erros ? 'Operação concluída com erros. Confira o registro.' : 'Operação concluída.', !!(estado.resultado.erro || estado.resultado.erros));
  else avisar('Pronta para buscar ou mover notas.');
  $('logs').textContent = estado.logs.join('\n');
  const r = estado.resultado;
  $('resumo').textContent = r && !r.erro ? `${r.encontrados} arquivo(s) encontrado(s) · ${r.concluidos} concluído(s) · ${r.ignorados} já existente(s) · ${r.erros} erro(s)${r.nao_encontradas.length ? ' · Notas não encontradas: ' + r.nao_encontradas.join(', ') : ''}` : '';
  botoes();
  return true;
}
async function consultarEstado() {
  const geracao = geracaoInicio, podeConfirmarInicio = !enviando;
  try {
    const estado = await pedir('/api/estado');
    // Uma leitura atrasada não representa queda de conexão nem confirma o início.
    if (Number.isInteger(estado?.versao) && estado.versao < versaoEstado) return false;
    if (!receber(estado)) throw Error('Estado indisponível.');
    // Só uma leitura posterior à resposta (ou falha) do POST libera outro início.
    if (podeConfirmarInicio && geracao === geracaoInicio && !enviando) inicioIncerto = false;
    botoes(); return true;
  } catch {
    conectado = false;
    avisar(inicioIncerto ? 'Confirmação pendente. Reconectando para verificar a operação…' : 'Conexão interrompida. Tentando reconectar…', true);
    botoes(); return false;
  }
}
async function iniciar(acao) {
  if (!carregado || !conectado || ocupado || enviando || inicioIncerto || selecionando || encerrando || encerrado) return;
  if (acao === 'mover' && !confirm('Mover as notas informadas nas pastas de origem para ano e mês? A data de modificação de cada arquivo será usada.')) return;
  enviando = true; botoes();
  try {
    if (!await salvarDestino()) return;
    geracaoInicio++;
    inicioIncerto = true;
    await pedir('/api/iniciar', {acao, notas:$('notas').value, destino:$('destino').value, caminhos:[0,1,2,3].map(i => $('caminho-' + i).value)});
  } catch (erro) {avisar('Não foi possível confirmar o início: ' + erro.message, true);}
  finally {
    enviando = false;
    if (inicioIncerto) {
      await consultarEstado();
      if (inicioIncerto) recuperarInicio();
    }
    botoes();
  }
}
async function recuperarInicio() {
  // Uma resposta perdida nunca reenvia a ação. Apenas consultas podem reconciliá-la.
  while (inicioIncerto && !encerrado && !saindo) {
    await new Promise(resolve => setTimeout(resolve, 1000));
    if (!encerrado && !saindo) await consultarEstado();
  }
}
$('buscar').addEventListener('click', () => iniciar('buscar'));
$('mover').addEventListener('click', () => iniciar('mover'));
$('cancelar').addEventListener('click', async () => {try {await pedir('/api/cancelar', {}); avisar('Parada solicitada. Concluindo o arquivo atual…');} catch (erro) {avisar(erro.message, true);}});
$('encerrar').addEventListener('click', async () => {
  if (encerrado || encerrando || selecionando) return;
  if ((ocupado || inicioIncerto || enviando) && !confirm('Encerrar a ferramenta? A operação será interrompida após concluir o arquivo atual.')) return;
  encerrando = true; botoes();
  try {
    if (carregado && !await salvarDestino()) return;
    await pedir('/api/encerrar', {});
    encerrado = true; presenca.abort();
    avisar('Encerramento solicitado. A operação para após concluir o arquivo atual. Você pode fechar esta janela.');
  } catch (erro) {avisar(erro.message, true);}
  finally {encerrando = false; botoes();}
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
      await consultarEstado();
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
}
window.addEventListener('pagehide', () => {saindo = true; if (carregado && !encerrado) salvarDestino(); presenca.abort(); if (!encerrado) fetch('/api/fechar-pagina', {method:'POST', keepalive:true, headers:{'Content-Type':'application/json','X-Notas-Token':token}, body:JSON.stringify({pagina})});});
window.addEventListener('pageshow', evento => {if (evento.persisted) location.reload();});
(async () => {
  while (!carregado && !encerrado && !saindo) {
    try {
      const config = await pedir('/api/configuracao');
      $('notas').value = ''; $('destino').value = destinoSalvo = config.destino;
      config.caminhos.forEach((c,i) => $('caminho-' + i).value = c);
      carregado = true;
    } catch (erro) {
      await consultarEstado();
      avisar(erro.message + ' Confira .local/preferencias.json na pasta de dados' + (desktop ? ' ou escolha novamente a pasta de cópias para salvar o destino.' : '.') + ' Tentando carregar novamente…', true);
      botoes();
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  if (!encerrado && !saindo) {await consultarEstado(); acompanhar();}
})();
botoes();
