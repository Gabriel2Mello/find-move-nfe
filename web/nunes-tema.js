/* Preferência visual compartilhada; não controla execução das automações. */
(() => {
  'use strict';
  const versao='1.1.0';
  function iniciar({controle, raiz=document.documentElement, chave='nunes-tema', cookie=false}={}) {
    const permitidos=['sistema','claro','escuro'];
    const botao=controle?.tagName?.toLowerCase()==='button';
    const valido=valor=>permitidos.includes(valor) && (!botao || valor!=='sistema');
    const nomeCookie=encodeURIComponent(chave);
    function lerCookie() {
      if(!cookie) return null;
      try {
        const item=document.cookie.split(';').map(parte=>parte.trim()).find(parte=>parte.startsWith(nomeCookie+'='));
        return item ? decodeURIComponent(item.slice(nomeCookie.length+1)) : null;
      } catch { return null; }
    }
    function salvar(valor) {
      try { localStorage.setItem(chave,valor); } catch {}
      if(cookie) {
        try { document.cookie=nomeCookie+'='+encodeURIComponent(valor)+'; Path=/; Max-Age=31536000; SameSite=Strict'; } catch {}
      }
    }
    let preferencia=lerCookie();
    if(!valido(preferencia)) {
      try { preferencia=localStorage.getItem(chave); } catch { preferencia=null; }
    }
    const persistida=valido(preferencia);
    if(!persistida) preferencia='escuro';
    function aplicar(valor, persistir=false) {
      preferencia=valido(valor)?valor:'escuro';
      if(preferencia==='sistema') raiz.removeAttribute('data-tema');
      else raiz.setAttribute('data-tema',preferencia);
      if(botao) {
        controle.textContent='Tema '+(preferencia==='escuro'?'claro':'escuro');
        controle.setAttribute('aria-label','Ativar tema '+(preferencia==='escuro'?'claro':'escuro'));
      } else if(controle) controle.value=preferencia;
      if(persistir) salvar(preferencia);
    }
    aplicar(preferencia);
    if(persistida) salvar(preferencia);
    const mudar=()=>aplicar(botao ? (preferencia==='escuro'?'claro':'escuro') : controle.value,true);
    const evento=botao?'click':'change';
    controle?.addEventListener(evento,mudar);
    return {aplicar, destruir(){controle?.removeEventListener(evento,mudar);}};
  }
  window.NunesTema=Object.freeze({versao,iniciar});
})();
