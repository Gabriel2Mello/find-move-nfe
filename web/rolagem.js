'use strict';
// Adaptado da Cofre: mantém a rolagem nativa e sobrepõe apenas o indicador de arraste.
(() => {
  if (!window.ResizeObserver || !window.PointerEvent) return;
  const alvos = [document.documentElement, ...document.querySelectorAll('#notas,.rolagem-resultados,.menu-configuracoes,dialog')];
  let quadro = 0;
  const barras = alvos.map(alvo => {
    const trilho = document.createElement('div'), polegar = document.createElement('div');
    trilho.className = 'barra-rolagem';
    trilho.setAttribute('aria-hidden', 'true');
    polegar.className = 'barra-rolagem-polegar';
    trilho.append(polegar);
    // O indicador de um diálogo precisa acompanhar sua camada modal.
    (alvo.matches('dialog') ? alvo : document.body).append(trilho);
    alvo.classList.add('rolagem-sobreposta');
    const pagina = alvo === document.documentElement;
    const margemResultados = alvo.classList.contains('rolagem-resultados');
    let percurso = 0, maximo = 0, arraste = null;
    function atualizar() {
      const rect = alvo.getBoundingClientRect();
      const altura = pagina ? innerHeight : alvo.clientHeight;
      const topo = pagina ? 0 : Math.max(0, rect.top + alvo.clientTop);
      const fim = pagina ? innerHeight : Math.min(innerHeight, rect.top + alvo.clientTop + altura);
      const visivel = Math.max(0, fim - topo);
      maximo = Math.max(0, alvo.scrollHeight - altura);
      trilho.hidden = !maximo || !visivel || (!pagina && getComputedStyle(alvo).overflowY === 'visible');
      if (!pagina && alvo.closest('dialog') && !alvo.closest('dialog').open) trilho.hidden = true;
      if (trilho.hidden) return;
      const tamanho = Math.min(visivel, Math.max(32, visivel * altura / alvo.scrollHeight));
      percurso = visivel - tamanho;
      const larguraBarra = trilho.getBoundingClientRect().width;
      const limiteDireito = document.documentElement.clientWidth - larguraBarra;
      trilho.style.top = topo + 'px';
      // Nos resultados, ocupa a margem que já existe fora da região rolável.
      trilho.style.left = (pagina ? limiteDireito : margemResultados
        ? Math.min(rect.right, limiteDireito)
        : rect.right - alvo.clientLeft - larguraBarra) + 'px';
      trilho.style.height = visivel + 'px';
      polegar.style.height = tamanho + 'px';
      polegar.style.top = (percurso * alvo.scrollTop / maximo) + 'px';
    }
    polegar.addEventListener('pointerdown', evento => {
      if (evento.button !== 0 || !evento.isPrimary) return;
      evento.preventDefault();
      arraste = {y:evento.clientY, topo:alvo.scrollTop};
      polegar.setPointerCapture(evento.pointerId);
    });
    polegar.addEventListener('pointermove', evento => {
      if (!arraste || !percurso) return;
      alvo.scrollTop = arraste.topo + (evento.clientY - arraste.y) * maximo / percurso;
      agendar();
    });
    for (const nome of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      polegar.addEventListener(nome, () => { arraste = null; });
    }
    polegar.addEventListener('wheel', evento => {
      if (evento.ctrlKey) return;
      evento.preventDefault();
      const fator = evento.deltaMode === 1 ? 20 : evento.deltaMode === 2 ? (pagina ? innerHeight : alvo.clientHeight) : 1;
      alvo.scrollBy({top:evento.deltaY * fator, left:evento.deltaX * fator});
    }, {passive:false});
    return {alvo, atualizar};
  });
  function agendar() {
    if (quadro) return;
    quadro = requestAnimationFrame(() => {
      quadro = 0;
      barras.forEach(barra => barra.atualizar());
    });
  }
  const tamanhos = new ResizeObserver(agendar);
  barras.forEach(barra => tamanhos.observe(barra.alvo));
  const conteudo = new MutationObserver(mudancas => {
    if (mudancas.some(mudanca => !mudanca.target.closest?.('.barra-rolagem'))) agendar();
  });
  // Os trilhos ficam fora das regiões observadas, exceto no diálogo;
  // ali ignoramos as alterações de posição do próprio indicador.
  for (const regiao of document.querySelectorAll('main,header,dialog')) {
    conteudo.observe(regiao, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['hidden','class','open']});
  }
  document.addEventListener('toggle', agendar, true);
  document.addEventListener('close', agendar, true);
  document.addEventListener('scroll', agendar, true);
  document.addEventListener('input', agendar);
  window.addEventListener('resize', agendar);
  document.fonts.ready.then(agendar);
  agendar();
})();
