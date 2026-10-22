# Busca e Move Notas

Uma aplicação Nunes com duas ações: **Busca-notas** copia DANFEs e XMLs; **Move-notas** organiza os arquivos na própria origem, em pastas de ano e mês. Abra pelo **Hub Nunes** ou por `Abrir Busca e Move Notas.cmd`.

Informe as notas na interface e escolha uma ação. `notas.txt`, quando existir, é carregado ao abrir; a interface não altera esse arquivo. São aceitos números de até quatro dígitos, separados por espaço, linha, vírgula ou ponto e vírgula. Números menores são completados com zeros. A identificação nos nomes dos arquivos preserva as posições dos scripts originais: quatro dígitos antes do dígito verificador do PDF e o trecho correspondente na chave do XML. Somente arquivos iniciados por `nfe`, sem distinção de maiúsculas, com extensão PDF ou XML são considerados.

As origens vêm de `CAMINHO_DANFE_MATRIZ`, `CAMINHO_DANFE_FILIAL`, `CAMINHO_XML_MATRIZ` e `CAMINHO_XML_FILIAL`. Podem ser ajustadas nesta aba em **Pastas de origem**. A busca percorre a raiz e as subpastas do ano atual e copia para `notas/` por padrão. A movimentação não entra em pastas com nomes numéricos; usa a **data de modificação do arquivo**, não a data de emissão, para organizar em `ANO/MÊS` na origem. Nenhuma ação é executada ao abrir a interface.

**Salvar cópias em** fica salvo para as próximas aberturas. A gravação acontece
ao sair do campo, iniciar uma ação, encerrar pelo botão ou fechar a aba, sem
precisar executar uma busca. A ajuda abaixo do campo confirma a gravação ou
informa a falha. A preferência fica em `.local/preferencias.json` nesta instalação;
inclua esse arquivo no backup para conservar a escolha. Sem preferência salva,
continua valendo `notas/`. Notas e ajustes das origens mantêm o comportamento acima.

Arquivos existentes no destino são preservados nas duas ações. Na busca, isso substitui a sobrescrita feita pelo script antigo. O acompanhamento informa cópias/movimentações, arquivos já existentes, erros e notas não encontradas. Arquivos com o mesmo nome em origens diferentes permanecem na origem quando já houver um destino com esse nome; confira o registro. Erros de acesso são mostrados, sem tratar uma pasta inacessível como busca concluída sem problemas.

**Parar operação**, **Encerrar**, fechar a última aba ou solicitar encerramento pelo monitor do hub concluem o arquivo em andamento antes de parar. Outra aba conectada mantém o servidor aberto. Há tolerância de cinco segundos para reconexão e limite inicial de dois minutos sem abas. Apenas uma operação executa por vez. A aplicação não utiliza o Sisplan e pode funcionar junto das ferramentas que o reservam.

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

O histórico local permanece disponível. A central confirma depois de gravar;
falhas conservam a pendência e reenvios não acrescentam contagem. Não execute
uma transferência novamente para recuperar estatística. O envio inclui eventos
locais anteriores à habilitação e tenta novamente enquanto a aplicação estiver
aberta, na próxima abertura ou por comando manual. Detalhes de instalação,
consulta, recuperação e distribuição estão no guia da central. Não há serviço
permanente nem implantação no TS01 nesta etapa. O Hub oferece uma seção
**Central local** com os totais recebidos e pendências, separada do relatório
local com filtros. A consulta do Hub não envia eventos nem cria confirmações.
O cliente deste projeto é distribuído também ao Hub e ao Cofre; mantenha as três cópias
de `sincronizar_estatisticas.py` iguais, juntamente com o contrato do piloto.

Validação deste piloto: 27 testes de central/integração, 47 regressões Python
desta ferramenta e sete JavaScript aprovados, com arquivos sintéticos e uma
conta Windows. Inclui perda de resposta após commit, central indisponível,
reinício em processos separados e pacote individual sem repositórios irmãos.

### Ambiente e testes da ferramenta

Python 3.10 ou superior, somente biblioteca padrão. Crie `.venv` com `python -m venv --without-pip .venv`. O CMD e o hub usam `.venv/Scripts/pythonw.exe`, com processo próprio e sem console. Para abrir diretamente pelo Python: `.venv/Scripts/python.exe notas.py`.

Execute `python -m unittest discover -s tests -v` e `node --test tests/test_notas_ui.cjs`. Em 16/10/2026 passaram 14 testes Python com arquivos temporários e dois JavaScript: formatos PDF/XML, filtros, cópia, movimentação, arquivos existentes, validação, cancelamento, HTTP local, várias abas, integração com o monitor e preservação do estado ocioso. Nenhuma operação em documentos reais foi necessária para esses testes.

Servidor em `127.0.0.1`, porta automática, token por execução, Host exato e validação de Origin nas ações. O servidor serve somente recursos explicitamente cadastrados. O processamento roda fora da requisição HTTP; a interface continua disponível durante a operação.

### Controle de tema compartilhado

A interface usa a cópia local `web/nunes-tema.js`, versão **1.1.0**, cuja
[fonte e contrato](../estrutura-nunes/identidade-visual/interfaces/README.md)
ficam no estrutura-nunes. A aplicação inicializa o controle com sua chave
`notas-tema` e `cookie: true`, preservando a preferência existente: cookie
válido antes do armazenamento local, e escuro sem preferência válida.

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

A assinatura segue `estrutura-nunes/identidade-visual/marca-pessoal/README.md`: **g2mello · Essencial**, com dois traços separados sob os `l`, link do GitHub e contraste nos temas claro e escuro. Não há sincronização automática com a fonte visual.

Criado por Gabriel Mello · [g2mello](https://github.com/Gabriel2Mello)
