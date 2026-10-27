# Busca e Move Notas desktop

`notas.py` usa pywebview 6.2.1 + WebView2/WinForms. Janela e backend Python
vivem no mesmo processo; HTTP e processamento usam suas próprias threads.
O executor de transferências e as entradas console `find.py` e `move.py`
permanecem os mesmos. Não reserva Sisplan e pode executar junto das ferramentas
que o utilizam. Não há serviço residente nem import de repositório irmão.

## Preparar e abrir

Ambiente conferido em 25/10/2026: Windows 11, Python 3.13.13 x64, pywebview
6.2.1, pythonnet 3.2.1, pywin32 312 e PyInstaller 6.21.0. O `.venv` anterior
é Python 3.13.13 x86 e foi preservado para o console. O desktop usa um ambiente
separado `.venv-desktop`, criado com Python x64. Outro Python/Windows/arquitetura
precisa de build e homologação próprios.

```powershell
# Na raiz desta aplicação, com Python 3.13 x64 disponível:
py -3.13-64 -m venv .venv-desktop
& .\.venv-desktop\Scripts\python.exe -m pip install -r requirements-build.txt
& '.\Abrir Busca e Move Notas.cmd'
& '.\Criar Atalho Busca e Move Notas.ps1'
```

O destino Windows precisa de .NET Framework 4.8 e WebView2 Evergreen Runtime
instalados e autorizados pela TI. O pacote não instala esses runtimes.
No ZIP conhecido desta distribuição, use **Propriedades → Geral → Desbloquear →
Aplicar** (quando disponível), antes de **Extrair Tudo** em uma pasta nova.
Isso evita que a marca de download bloqueie as bibliotecas .NET do pacote.

Falhas na abertura do servidor, sincronizador, publicação ou janela mostram a
etapa e o caminho de `find-move-nfe-diagnostico.txt`. O pacote tenta gravar ao
lado do exe; sem permissão, usa `logs/` nas preferências e depois TEMP. O arquivo
contém tipos/locais das causas, códigos numéricos e presença/marca de download
dos recursos, sem mensagens brutas, documentos, credenciais ou valores livres
do ambiente. Fonte `diagnostico_nunes.py` no Hub, com cópia independente e hashes
declarados no manifesto. Veja o [padrão Nunes de diagnóstico](../estrutura-nunes/area-nunes/diagnosticos.md).

O renderer é explicitamente `edgechromium`, sem fallback para IE.
Referências: [instalação](https://pywebview.flowrl.com/guide/installation.html),
[API de janelas e diálogos](https://pywebview.flowrl.com/api/) e
[distribuição WebView2](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution).

CMD, Python, exe, atalho e Hub iniciam ou restauram a mesma janela da sessão
Windows, inclusive minimizada, sem recarregar campos, resultado ou operação.
Identidade: `Nunes.BuscaMoveNotas.Desktop.1`, nome Busca e Move Notas e ícone
aprovado azul petróleo #0E7490. Relançamento e atalho usam o mesmo iniciador.
Gere novamente o atalho ao mover a instalação; fixar na barra é ação manual.
O Windows pode negar foco e sinalizar o botão na barra.

## Uso, preferências e encerramento

**Buscar** copia DANFEs/XMLs. **Mover** organiza na própria origem
por ano/mês da modificação, excluindo pastas numéricas da varredura. Os filtros,
busca na raiz/ano atual, preenchimento de zeros, conflitos concorrentes, cópia
verificada e preservação de destinos seguem o README e o executor existente.

**Limpar** remove permanentemente os arquivos da raiz da pasta de cópias após
confirmar destino e quantidade, preservando subpastas e links. Ao concluir sem
erros ou interrupção, esvazia Notas; sem arquivos elegíveis, limpa apenas Notas
sem confirmação. Consulte as proteções e limites da limpeza no README.

O destino é persistido em `.local/preferencias.json`, como antes. Campo editável
e botão **Alterar** apontam à mesma preferência. Cancelar o diálogo mantém a
seleção anterior. As quatro origens vêm das mesmas variáveis de ambiente;
escolher ou editar uma origem só ajusta esta janela, sem gravar variáveis ou
preferências de origem. A janela mantém notas e resumo durante atualizações.
À direita de cada **Alterar**, **Abrir** abre no Explorador a pasta atualmente
informada naquele campo, inclusive uma edição manual. Pastas inexistentes ou
inacessíveis geram um aviso, sem criar diretórios. A abertura não inicia busca
ou movimentação nem altera a seleção das pastas.
Preferência inválida é informada e pode ser substituída explicitamente pelo
seletor do destino. A dica de persistência aparece na tooltip de **Salvar cópias em**,
por mouse ou foco, e fecha com Escape. A lista de notas começa vazia no web/desktop;
somente `find.py` e `move.py` leem `notas.txt`. A interface não lê nem altera esse arquivo.

Tema e geometria persistem em `desktop-tema.json` e `desktop-janela.json` no
perfil. O tema backend válido tem precedência; cookie/armazenamento legado
válido é respeitado quando disponível; sem preferência, desktop inicia claro.
O renderer privado não importa o perfil de um navegador externo: uma escolha
antiga existente somente naquele navegador deve ser escolhida uma vez aqui.
Geometria inválida usa o padrão; monitor removido ajusta o retângulo à área
útil. Fechar minimizada não inicia oculto na próxima execução.

X ocioso salva a edição de destino e encerra. X durante processamento confirma
uma vez; cancelar mantém a execução; confirmar pede parada após concluir o
arquivo em andamento. **Encerrar** confirma na própria tela e Hub confirma no
monitor, sem repetição de confirmação na janela. O título indica encerramento.
A saída aguarda worker e sincronizador antes de liberar recursos/exclusividade.
Nenhum processo é morto por timeout. Perda de SSE/conexão, isoladamente, não
encerra o desktop. Fechar o Hub mantém esta aplicação aberta.

## Dados, pacote e atualização

```powershell
& '.\Build Desktop.ps1'
& '.\dist\Busca e Move Notas\Busca e Move Notas.exe'
& '.\dist\Busca e Move Notas\Criar Atalho Busca e Move Notas.ps1'
```

Distribua a pasta inteira `dist\Busca e Move Notas`, incluindo `_internal`,
guia e gerador de atalho. Não basta o exe. O spec lista recursos explicitamente:
HTML/CSS/JS e ícones aprovados; não inclui notas, preferências, caminhos de
negócio, credenciais, métricas ou vínculo central. Não distribua build/ambientes.

| Dado | Desenvolvimento | Pacote |
| --- | --- | --- |
| `.local/preferencias.json`, cópias padrão `notas/` | Raiz do projeto | `%LOCALAPPDATA%\Nunes\BuscaMoveNotas` |
| Tema e geometria | `%LOCALAPPDATA%\Nunes\BuscaMoveNotas` | Mesmo perfil |
| Vínculo central opcional | `.local/central.json` na raiz | `.local/central.json` nos dados do perfil |

`NUNES_NOTAS_DADOS` substitui explicitamente os dados e preferências da interface
para ensaio/instalação isolada. Não altera o contrato de `find.py`/`move.py`:
console continua lendo `notas.txt` do diretório de trabalho e as variáveis de
ambiente originais. Métricas/presença conservam seus overrides independentes
`NUNES_METRICAS_DADOS` e `NUNES_HUB_DADOS`. `NUNES_CENTRAL_CONFIG` prevalece
quando informado; sem vínculo, sincronização não é habilitada. A fila local e
deduplicação de métricas permanecem no contrato compartilhado.

Migração para pacote: com aplicação fechada e backup, copie apenas os dados que
deseja conservar (`.local/preferencias.json` e vínculo opcional)
para a pasta persistente escolhida. Não há importação/mesclagem automática de
dados reais. Em desenvolvimento a preferência existente continua no mesmo
arquivo. Atualize a pasta distribuída com a aplicação fechada, mantendo a pasta
persistente. Não apague métricas/fila para corrigir sincronização.

No Hub, desenvolvimento usa `notas.py`, ambientes `.venv-desktop`/`.venv`,
`modo: desktop` e `sisplan: false`. Para pacote, ajuste o catálogo para a pasta
distribuída, `entrada: "Busca e Move Notas.exe"`, `ambientes: []`. Reinicie o Hub
para carregar o cadastro novo. Um Hub empacotado antigo precisa ser reconstruído
com a fonte atual, além de ter seu catálogo ajustado. O pacote antigo encontrado
nesta máquina recusou entrada `.exe` como indisponível; a fonte atual foi
ensaiada com janela real e iniciou/ativou o pacote desta ferramenta.

## Segurança e manutenção

Trava e saúde autenticada conferem aplicação, protocolo, instância e PID;
ativação confere também a sessão Windows. A segunda abertura espera até 15 s
por inicialização/saída e volta a disputar a trava quando ela libera. Um dono
sem resposta conserva a trava; feche uma versão web anterior normalmente.
`POST /desktop/ativar` aceita somente `{}`, com Host exato, token de integração,
sem Origin e JSON. Não aceita comandos, caminhos ou scripts. Rotas da página
exigem token próprio, Host exato e Origin válido; bind é loopback, CSP e lista
de recursos permanecem restritos. Não há objeto Python exposto ao JavaScript.

`desktop_windows.py` é cópia independente da fonte do Hub, SHA-256
`ee726338206a40731335c4047df2a3536d1f4ec140da250ec4bf5fde9bab3c24`, registrado
no manifesto do Hub. Integração, métricas e sincronizador compartilhados não
foram modificados. Diagnósticos sanitizados de abertura/erro continuam na
pasta de presença da sessão, em `logs/find-move-nfe-abertura.log` e
`logs/find-move-nfe.log`.

## Validação reproduzível

```powershell
& .\.venv-desktop\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_notas_ui.cjs
# Abrem janelas reais, mas usam somente dados/arquivos sintéticos em TEMP:
& .\.venv-desktop\Scripts\python.exe -m tests.verificar_pacote_desktop --fonte
& .\.venv-desktop\Scripts\python.exe -m tests.verificar_pacote_desktop
```

Os ensaios geram evidências locais em `.local/qa-desktop` e preservam suas
pastas TEMP para diagnóstico. Testes de rede física, volumes físicos distintos,
queda de energia e implantação no TS01 continuam exigindo homologação isolada
do responsável. Não executar esses testes sobre notas ou compartilhamentos reais.

### Evidências da implementação — 25/10/2026

Testes automatizados: 66 Python desta aplicação, 19 JavaScript e 60 Python
direcionados do Hub (desktop, integração e manutenção), com dados sintéticos.
`pip check` sem incompatibilidades. Console x86 original executou `find.py` e
`move.py` com diretório de trabalho isolado e o Enter de confirmação preservado.

Janela WebView2 real: temas claro/escuro, disposição ampla/compacta, diálogo
nativo/cancelamento, edição de campos, segunda abertura e restauração minimizada
mantendo edição e resultado foram observados. No ensaio lento, X confirmou;
cancelar preservou a janela. Uma nova cópia encerrada pelo X concluiu nove de
vinte arquivos sintéticos, todos conferidos por SHA-256, sem temporários e sem
remover os vinte originais. O fechamento nativo ocioso do pacote salvou a edição
do destino sem precisar sair do campo. Os ensaios automáticos conferiram cópia,
movimentação, abertura/ativação pelo Hub e independência após fechar o Hub.

O primeiro ensaio do Hub fonte com argumentos de isolamento redundantes falhou
ao inicializar a janela; o ensaio ajustado usa `NUNES_HUB_DADOS` sem repetir
`--dados` no relançamento e passou com a janela real. Não alterou o runtime do
Hub nem seus mecanismos de segurança. Homologação humana de aparência,
agrupamento/fixação na barra e implantação em outra máquina continua pendente.

### Arquivos da migração

No `find-move-nfe`:

- Backend e dados: `notas.py`, `desktop_notas.py`, `desktop_windows.py`, `caminhos_desktop.py`.
- Interface: `web/index.html`, `web/notas.css`, `web/notas.js`.
- Distribuição: `Abrir Busca e Move Notas.cmd`, `Criar Atalho Busca e Move Notas.ps1`,
  `Build Desktop.ps1`, `Busca e Move Notas.spec`, `requirements-desktop.txt`,
  `requirements-build.txt`, `.gitignore`.
- Testes: `tests/__init__.py`, `tests/test_desktop.py`, `tests/test_notas.py`,
  `tests/test_notas_ui.cjs`, `tests/ensaio_desktop.py`, `tests/verificar_pacote_desktop.py`.
- Documentação: `README.md`, `DESKTOP.md`.

No `nunes-hub`: `aplicacoes.json`, `manutencao.json`, `DESKTOP.md` e
`tests/test_cofre_desktop.py`. Alterações concorrentes nos demais arquivos do
Hub foram preservadas. A Cofre também recebeu ajustes de rótulo, neon e layout,
documentados no guia desktop daquele projeto.
`operacoes.py`, `find.py`, `move.py`, os ícones aprovados e os contratos
compartilhados anteriores permaneceram intactos. Ambientes, pacotes, atalhos
gerados e evidências locais ficam fora dos commits. Não houve push ou publicação.
