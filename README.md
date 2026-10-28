# Busca e Move Notas

Uma aplicação Nunes com três ações: **Buscar** copia DANFEs e XMLs; **Mover** organiza os arquivos na própria origem, em pastas de ano e mês; **Limpar** exclui os arquivos da pasta de cópias e esvazia Notas. Abra pelo **Hub Nunes** ou por `Abrir Busca e Move Notas.cmd`.

**Desktop Windows:** `notas.py` agora abre uma janela própria WebView2. Consulte
[DESKTOP.md](DESKTOP.md) para preparar `.venv-desktop` x64, gerar atalho/pacote,
migrar dados e integrar o executável ao Hub. A segunda abertura restaura a mesma
janela, sem perder campos ou repetir operação. `find.py` e `move.py` conservam
o modo console e o ambiente anterior.

Informe as notas na interface e escolha uma ação. A lista começa vazia no web/desktop; a interface não lê nem altera `notas.txt`. Somente as entradas console `find.py` e `move.py` carregam esse arquivo. São aceitos números de até quatro dígitos, separados por espaço, linha, vírgula ou ponto e vírgula. Números menores são completados com zeros. A identificação nos nomes dos arquivos preserva as posições dos scripts originais: quatro dígitos antes do dígito verificador do PDF e o trecho correspondente na chave do XML. Buscar e Mover consideram somente arquivos iniciados por `nfe`, sem distinção de maiúsculas, com extensão PDF ou XML.

**Limpar**, à direita de Mover, independe da lista de notas. A aplicação salva o
destino editado e prepara a limpeza da pasta configurada em **Salvar cópias em**.
Havendo arquivos, a confirmação mostra o caminho e a quantidade. A exclusão é
permanente, sem Lixeira, e abrange todos os tipos de arquivo diretamente nessa
pasta. Subpastas, links e pontos de redirecionamento são preservados. Se não
houver arquivos elegíveis, limpa somente Notas e a contagem, sem confirmação.
Ao concluir a exclusão sem erros ou interrupção, também limpa Notas. Cancelar
a confirmação ou ocorrer falha/interrupção preserva a lista.

A limpeza recusa origens, raiz de disco/compartilhamento e pastas que contenham
a instalação ou os dados da aplicação. Usa uma confirmação de uso único e
exclui somente os arquivos examinados: arquivos novos ou alterados depois da
preparação são preservados. Mantenha essa pasta estável durante a operação;
as conferências não bloqueiam alterações de outros programas entre a última
verificação e a exclusão. Falhas não recuperam arquivos já excluídos. O registro
e os cartões mostram exclusões, preservações e erros; Parar/Encerrar aguardam
o arquivo em andamento. A limpeza não acrescenta métricas de busca/movimentação
e não altera `notas.txt`.

As origens vêm de `CAMINHO_DANFE_MATRIZ`, `CAMINHO_DANFE_FILIAL`, `CAMINHO_XML_MATRIZ` e `CAMINHO_XML_FILIAL`. Podem ser ajustadas em **Configurações → Pastas de origem**. A busca percorre a raiz e as subpastas do ano atual e copia para `notas/` por padrão. A movimentação não entra em pastas com nomes numéricos; usa a **data de modificação do arquivo**, não a data de emissão, para organizar em `ANO/MÊS` na origem. Nenhuma ação é executada ao abrir a interface.

**Salvar cópias em** fica salvo para as próximas aberturas. A gravação acontece
ao sair do campo, iniciar uma ação, encerrar pelo botão ou fechar a janela, sem
precisar executar uma busca. A ajuda abaixo do campo confirma a gravação ou
informa a falha. Em desenvolvimento a preferência fica em `.local/preferencias.json` nesta instalação;
inclua esse arquivo no backup para conservar a escolha. Sem preferência salva,
continua valendo `notas/`. No pacote esses arquivos ficam nos dados persistentes
do perfil, conforme [DESKTOP.md](DESKTOP.md). Notas e ajustes das origens mantêm o comportamento acima.

Arquivos existentes no destino são preservados nas duas ações. Na busca, isso substitui a sobrescrita feita pelo script antigo. O acompanhamento informa cópias/movimentações, arquivos já existentes, erros e notas não encontradas. Erros de acesso são mostrados, sem tratar uma pasta inacessível como busca concluída sem problemas.

Quando **Buscar** encontra o mesmo nome de arquivo em mais de um local, reúne
as versões antes de copiar e escolhe a **emissão mais recente**. Emissões iguais
usam a **modificação mais recente do arquivo**; se ambas empatarem, o caminho
serve apenas para manter a escolha estável, independentemente da ordem da busca.
A lista de andamento e resultados informa que o arquivo foi encontrado em dois
ou mais locais. Na interface, cada caminho aparece como empresa e trecho relativo,
por exemplo `FILIAL · DANFE\2026\AGOSTO\Nfe0079974.pdf`, e a versão selecionada
é indicada sem o detalhamento das datas. O console conserva os caminhos completos e datas.
As outras versões permanecem nas origens e não geram o aviso de destino existente
quando a pasta de cópias começou vazia. Encontrados inclui as versões localizadas;
Concluídos e as métricas contam somente o arquivo efetivamente copiado.

A emissão é lida no campo **DATA [DE] EMISSÃO** da primeira página do DANFE,
incluindo o horário quando presente junto à data, ou em `ide/dhEmi` (`dEmi` nos
XMLs antigos). Nome da pasta, criação do PDF, autorização e vencimento não
substituem a emissão. Se uma versão duplicada não permitir essa leitura (inclusive
PDF digitalizado sem texto), nenhuma versão daquele nome é copiada e o motivo
aparece como erro. Arquivos sem duplicidade mantêm a cópia direta. **Mover**
continua organizando por modificação, preservando colisões. Destinos já ocupados
continuam preservados; para refazer a seleção, use uma pasta vazia ou a limpeza
com confirmação. É necessário reabrir a aplicação para carregar a regra; pacotes
executáveis antigos precisam ser reconstruídos.

**Parar operação**, **Encerrar**, X da janela ou encerramento pelo monitor do Hub concluem o arquivo em andamento antes de parar. X durante operação confirma uma vez. A janela controla a vida do backend: perder presença/conexão não encerra o desktop e fechar o Hub mantém a ferramenta aberta. Apenas uma operação executa por vez. A aplicação não utiliza o Sisplan e pode funcionar junto das ferramentas que o reservam. O comportamento antigo de encerramento pela última aba permanece apenas nos testes do servidor web.

Enquanto estiver ociosa, a interface preserva status, resultado e campos. A conexão de presença continua aberta para detectar a saída das abas, mas só transmite estado quando houver mudança; sinais de presença não redesenham a interface.

As atualizações de acompanhamento têm uma versão crescente. Uma consulta antiga
que chegue depois da conclusão não recoloca a tela em “Movendo e organizando
notas…” nem apaga o resumo final. Novas execuções continuam atualizando o andamento.

O contrato `integracao_hub.py` é copiado do nunes-hub, que mantém a fonte. Ele fornece identidade, saúde, parada e instância única, inclusive nos iniciadores console `find.py` e `move.py`. As entradas console continuam lendo `notas.txt` da pasta de trabalho e as mesmas variáveis de ambiente. Executáveis antigos em `dist` precisam ser reconstruídos para incorporar as mudanças.

As entradas console retornam código 1 quando falta o arquivo de entrada, há
erro de configuração/validação ou a transferência termina com erros. Código
0 indica execução sem erros técnicos; notas não encontradas e destinos já
existentes continuam pendências informadas, sem sobrescrita. Confira o resumo
antes de repetir uma operação parcialmente concluída.

## Diagnóstico de abertura

A abertura registra servidor/estado, entrada do sincronizador e publicação
em `logs/find-move-nfe-abertura.log`, na pasta de presença da sessão Nunes.
Reabra a aplicação para carregar a mudança. Valores medidos, localização,
retenção e limites estão em [Tempos por etapa](../nunes-hub/TEMPOS_ABERTURA.md).

## Preservação de arquivos — E6, 20/10/2026

A movimentação usa uma publicação que recusa um destino já ocupado. Uma
colisão criada depois da verificação inicial também preserva os arquivos e
aparece no registro como **Conflito**, somando em **já existentes**, sem
somar conclusão. Não há repetição por outro método em caso de permissão,
indisponibilidade ou conflito. Console e interface usam o mesmo executor.

No Windows, o movimento no mesmo volume usa `os.rename`, sem `shutil.move`.
Somente `EXDEV` (volumes diferentes) permite a alternativa de cópia: temporário
exclusivo na pasta de destino, sincronização, comparação SHA-256 com a origem,
publicação sem substituição e conferência do arquivo final e da origem antes
de removê-la. A busca também usa essa cópia verificada, mantendo a origem.
Referências: [rename](https://docs.python.org/3.13/library/os.html#os.rename)
e [move](https://docs.python.org/3.13/library/shutil.html#shutil.move).

Se a publicação terminar e a conferência/remoção falhar, a operação informa
erro com o caminho publicado e mantém a origem disponível, sem apagar o
destino como tentativa de desfazer. Uma nova execução encontra esse destino
e o ignora: **confira conteúdo e caminhos manualmente antes de decidir sobre
duplicatas**. Queda do processo pode deixar um `.nunes-*.tmp` ou as duas
cópias; esses temporários não entram na seleção de notas e não são retomados
nem apagados automaticamente em outra execução. Não há diário de recuperação.

As origens devem estar estáveis. As verificações detectam mudanças de
identidade, tamanho, datas e conteúdo, mas não bloqueiam edições/remoções por
outros programas depois da conferência. A proteção impede que esta ferramenta
substitua um nome ocupado; não controla alterações posteriores de terceiros.
A cópia conserva os metadados suportados por `copy2`, sem garantir ACLs,
proprietário ou fluxos alternativos. Filtros de nomes e organização por data
de modificação permanecem conforme descritos acima.

Validação local: **28 testes Python e dois JavaScript aprovados**, com 14
testes Python novos. Abrangem a corrida com conteúdo distinto, dois escritores,
permissão, cópia parcial/divergente, sincronização, origem/destino alterados,
publicação e remoção com falha, além dos fluxos console e worker web. Os testes
usaram arquivos sintéticos temporários; a diferença entre volumes foi simulada
por `EXDEV`. Nenhuma nota ou pasta de rede real foi alterada. A análise de tipos
mantém dois erros anteriores de `operacoes.py`, confirmados no código de HEAD
(mês opcional e inferência do resumo), além de avisos; sem erro novo na E6.

Windows local foi validado. Compartilhamento real, volumes físicos distintos,
queda de energia e POSIX continuam sem homologação. Antes do uso operacional
em rede, conferir em área isolada de testes: destino existente, criação
concorrente com conteúdo distinto e indisponibilidade durante cópia/publicação;
comparar origem/destino e confirmar que falhas não removem a origem. Reabrir
a aplicação Python para carregar o código. Executáveis antigos em `dist`
precisam ser reconstruídos antes da distribuição.


## Contador de arquivos — E11, 21/10/2026

No Hub, **Resultados → Arquivos buscados e movidos** reúne as duas ações no
mesmo total. A unidade aprovada pelo responsável é **um arquivo concluído por
ação**: buscar PDF e XML soma 2; depois mover os dois soma mais 2, totalizando 4.
Só encontrar um nome não conta: na busca, a cópia precisa terminar com a
conferência E6; no movimento, a transferência precisa terminar, incluindo a
remoção da origem quando usar cópia entre volumes. Já existentes, conflitos,
falhas e itens não processados por cancelamento ficam fora do contador.

Interface web e console compartilham o registro. Cada entrega usa a ação e os
caminhos absolutos normalizados de origem/destino como identidade estável.
Reiniciar ou repetir a mesma entrega não acrescenta outra contagem, mesmo
depois de remover a cópia de destino. Outro destino ou outra origem representa
outra entrega. O conteúdo não integra essa identidade: substituir um arquivo
por outro no mesmo caminho e repetir a mesma ação também não cria novo evento.
Não foi acrescentada leitura da chave fiscal nem alterada a seleção legada.

O histórico/CSV conserva referência de quatro dígitos e tipo da ação/arquivo
(`busca_pdf`, `busca_xml`, `move_pdf`, `move_xml`), sem guardar caminhos ou nomes
fiscais completos. Esses caminhos entram apenas na identidade em hash. Não se
infere empresa a partir da posição/nome das pastas; esses eventos ficam na visão
de todas as empresas. Não há classificação por setor.

O módulo `metricas_nunes.py` tem fonte no Hub, assim como a integração. O
escritor mantém SQLite/fila permanente local, instante original e deduplicação
do [contrato de métricas](../nunes-hub/METRICAS.md). Se banco e fila falharem,
a ferramenta avisa que o relatório pode ficar incompleto e preserva o resultado
da transferência, sem repeti-la. Queda entre transferência e registro pode
deixar uma lacuna; uma execução que encontra o destino existente não reconstrói
uma conclusão antiga sem evidência. Não há diário de recuperação novo.

**Atualização:** encerrar normalmente e reabrir Hub e as seis ferramentas
que compartilham métricas (Havan, Financeiro, Cofre, Impressão, Busca e Move e Fluxo)
para carregar o contrato com o novo evento. Leitores antigos rejeitam esse
evento como desconhecido. Não apagar banco/fila para contornar isso.
Executáveis antigos precisam ser reconstruídos. O histórico começa com as
próximas operações desta versão, sem importar documentos anteriores.

Validação: 40 testes Python da ferramenta (12 novos), com transferência real
de arquivos sintéticos, console/worker, falhas, colisão, cancelamento,
persistência/deduplicação e fila. No conjunto afetado passaram **776 Python e
52 JavaScript**, tipagem estrita do Financeiro sem erros/avisos, contratos
iguais por SHA-256 e verificação do pacote E10 histórico. Prévia Edge conferida
em claro/escuro a 360/1200 px. Nenhuma nota real, pasta de rede ou aplicação
externa foi operada. Evidências locais: `nunes-hub/.local/e11-find-move-2026-10-21/`.

## Instalação e validação

### Piloto de estatísticas com central local — 21/10/2026

O cliente opcional `sincronizar_estatisticas.py` replica os eventos persistidos
de arquivos transferidos para a [central de estatísticas](../nunes-estatisticas/README.md).
O mesmo cliente acompanha as entradas web e console, sem depender do Hub
instalado. O vínculo é preparado pela central e fica em `.local/central.json`;
sem esse arquivo e sem `NUNES_CENTRAL_CONFIG`, não há sincronização.

O sincronizador consulta na abertura e ao encerrar. A espera base entre ciclos
é de cinco segundos; após ciclos sem atividade nem pendências, cresce para 10,
20 e no máximo 30 segundos. Atividade ou falha retomam cinco segundos. A espera
pode ser interrompida pelo encerramento; cada ciclo ainda faz a reconciliação
completa do banco e da fila, sem cache persistente nem alteração de esquema.
Um ciclo sem pendências evita a segunda leitura integral redundante. Esses
intervalos são esperas entre ciclos, além do tempo de leitura/envio.

O histórico local permanece disponível. A central confirma depois de gravar;
falhas conservam a pendência e reenvios não acrescentam contagem. Não execute
uma transferência novamente para recuperar estatística. O envio inclui eventos
locais anteriores à habilitação e tenta novamente enquanto a aplicação estiver
aberta, na próxima abertura ou por comando manual. Detalhes de instalação,
consulta, recuperação e distribuição estão no guia da central. Não há serviço
permanente nem implantação no TS01 nesta etapa. O Hub oferece uma seção
**Central local** com os totais recebidos e pendências, separada do relatório
local com filtros. A consulta do Hub não envia eventos nem cria confirmações.
O cliente tem fonte neste projeto e seis cópias declaradas no
[manifesto de manutenção do Hub](../nunes-hub/manutencao.json). Mantenha as sete
cópias de `sincronizar_estatisticas.py` iguais, juntamente com o contrato do piloto.

Validação deste piloto: 27 testes de central/integração, 47 regressões Python
desta ferramenta e sete JavaScript aprovados, com arquivos sintéticos e uma
conta Windows. Inclui perda de resposta após commit, central indisponível,
reinício em processos separados e pacote individual sem repositórios irmãos.

### Ambiente e testes da ferramenta

O executor/console usa Python 3.10 ou superior e `pypdf`, fixado em
`requirements.txt`, para ler a emissão de DANFEs duplicados. Instale com
`python -m pip install -r requirements.txt` no ambiente do console.
O desktop usa o ambiente Windows x64 com dependências fixadas descrito em
[DESKTOP.md](DESKTOP.md). CMD e Hub preferem `.venv-desktop/Scripts/pythonw.exe`;
para abrir diretamente: `.venv-desktop/Scripts/python.exe notas.py`.

Execute `python -m unittest discover -s tests -v` e `node --test tests/test_notas_ui.cjs`. Em 16/10/2026 passaram 14 testes Python com arquivos temporários e dois JavaScript: formatos PDF/XML, filtros, cópia, movimentação, arquivos existentes, validação, cancelamento, HTTP local, várias abas, integração com o monitor e preservação do estado ocioso. Nenhuma operação em documentos reais foi necessária para esses testes.

Servidor em `127.0.0.1`, porta automática, token por execução, Host exato e validação de Origin nas ações. O servidor serve somente recursos explicitamente cadastrados. O processamento roda fora da requisição HTTP; a interface continua disponível durante a operação.

A preparação de Buscar/Mover também executa no worker: a operação fica reservada
antes de consultar as pastas, sem bloquear o estado ou a janela durante uma
consulta lenta. Erros de preparação aparecem no registro e no resultado.
Parar/Encerrar durante essa etapa impedem a transferência e a criação do destino
quando a consulta em andamento retornar; não interrompem uma chamada de sistema
já bloqueada. Nenhuma segunda operação começa enquanto a preparação estiver ativa.

### Controle de tema compartilhado

O layout segue a referência do Cofre NFe: cabeçalho compacto, fonte Segoe UI,
preparação à esquerda e andamento/resultados à direita. O campo **Notas** tem
dez linhas visíveis, altura fixa e contador discreto no canto inferior direito,
sem fundo próprio. A contagem considera números válidos de até quatro dígitos,
sem repetir notas equivalentes como `7` e `0007`. A coluna esquerda não tem
rolagem própria. As descrições
ficam em **Como funcionam as ações**, que abre uma ajuda fechável com **Fechar**
ou Escape. Em janelas baixas, a tela inteira pode rolar; os resultados mantêm
sua rolagem própria em duas colunas. Em telas estreitas as áreas se empilham.
**Configurações**, no cabeçalho,
reúne as quatro pastas de origem; o menu fecha com Escape, clique ou foco fora.
O destino das cópias permanece junto das notas, e **Encerrar** fica no rodapé.

O botão de tema usa os ícones locais de lua e lua/sol da Cofre, com transição
de cores de 150 ms e rotação de 120 ms após troca manual. Movimento reduzido
desativa os efeitos. A identidade e o ícone da aplicação continuam no azul
petróleo aprovado; o neon das notas só aparece no campo vazio e sem foco.
Os dois SVGs de tema são recursos locais explícitos no servidor e no spec
do desktop. Reabra a aplicação Python para carregar o layout; executáveis
existentes precisam ser reconstruídos.

A interface usa a cópia local `web/nunes-tema.js`, versão **1.1.0**, cuja
[fonte e contrato](../estrutura-nunes/identidade-visual/interfaces/README.md)
ficam no estrutura-nunes. A aplicação inicializa o controle com sua chave
`notas-tema` e `cookie: true`. O desktop prioriza a preferência persistida no
backend, depois o legado válido disponível (cookie antes do armazenamento local)
e aplica claro sem preferência. O componente distribuído conserva seu contrato.

Para atualizar as cópias das seis interfaces locais, execute na raiz do estrutura-nunes:

```powershell
./identidade-visual/interfaces/distribuir-tema.ps1
./identidade-visual/interfaces/distribuir-tema.ps1 -Verificar
```

O CSS da assinatura Essencial fica em `web/nunes-assinatura.css`, com fonte
compartilhada no mesmo guia e cores herdadas desta aplicação. Tema e assinatura
têm destinos declarados em `componentes.json`; use `distribuir-componentes.ps1`
para atualizar ambos ou acrescente `-Verificar` para somente conferir hashes.

Distribua o arquivo junto da pasta `web` e reabra a aplicação para carregar a
cópia atualizada. A execução usa apenas arquivos locais. Valide com os comandos
Python e JavaScript acima; o teste HTTP confere recurso, ordem dos scripts
e política de segurança existente.

## Identidade e autoria

Ícone gerado pelo modelo aprovado em `estrutura-nunes/identidade-visual`, cadastrado como `find-move-nfe` na paleta central: azul petróleo **#0E7490**, símbolo branco preservado. Recursos em `icons/`, favicon e cabeçalho da interface, `icone.ico` para compatibilidade e `notas.svg` distribuído ao hub. O gerador sinalizou proximidade com o cinza ardósia da Impressão de OPs; a identificação também usa os nomes visíveis.

A assinatura segue `estrutura-nunes/identidade-visual/marca-pessoal/README.md`: **Desenvolvido por g2mello**, no estilo **Essencial**, com dois traços separados sob os `l`, link do GitHub e contraste nos temas claro e escuro. Essencial é o nome do estilo, não texto do rodapé. Não há sincronização automática com a fonte visual.

Criado por Gabriel Mello · [g2mello](https://github.com/Gabriel2Mello)
