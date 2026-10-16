# Busca e Move Notas

Uma aplicação Nunes com duas ações: **Busca-notas** copia DANFEs e XMLs; **Move-notas** organiza os arquivos na própria origem, em pastas de ano e mês. Abra pelo **Hub Nunes** ou por `Abrir Busca e Move Notas.cmd`.

Informe as notas na interface e escolha uma ação. `notas.txt`, quando existir, é carregado ao abrir; a interface não altera esse arquivo. São aceitos números de até quatro dígitos, separados por espaço, linha, vírgula ou ponto e vírgula. Números menores são completados com zeros. A identificação nos nomes dos arquivos preserva as posições dos scripts originais: quatro dígitos antes do dígito verificador do PDF e o trecho correspondente na chave do XML. Somente arquivos iniciados por `nfe`, sem distinção de maiúsculas, com extensão PDF ou XML são considerados.

As origens vêm de `CAMINHO_DANFE_MATRIZ`, `CAMINHO_DANFE_FILIAL`, `CAMINHO_XML_MATRIZ` e `CAMINHO_XML_FILIAL`. Podem ser ajustadas nesta aba em **Pastas de origem**. A busca percorre a raiz e as subpastas do ano atual e copia para `notas/` por padrão. A movimentação não entra em pastas com nomes numéricos; usa a **data de modificação do arquivo**, não a data de emissão, para organizar em `ANO/MÊS` na origem. Nenhuma ação é executada ao abrir a interface.

Arquivos existentes no destino são preservados nas duas ações. Na busca, isso substitui a sobrescrita feita pelo script antigo. O acompanhamento informa cópias/movimentações, arquivos já existentes, erros e notas não encontradas. Arquivos com o mesmo nome em origens diferentes permanecem na origem quando já houver um destino com esse nome; confira o registro. Erros de acesso são mostrados, sem tratar uma pasta inacessível como busca concluída sem problemas.

**Parar operação**, **Encerrar**, fechar a última aba ou solicitar encerramento pelo monitor do hub concluem o arquivo em andamento antes de parar. Outra aba conectada mantém o servidor aberto. Há tolerância de cinco segundos para reconexão e limite inicial de dois minutos sem abas. Apenas uma operação executa por vez. A aplicação não utiliza o Sisplan e pode funcionar junto das ferramentas que o reservam.

Enquanto estiver ociosa, a interface preserva status, resultado e campos. A conexão de presença continua aberta para detectar a saída das abas, mas só transmite estado quando houver mudança; sinais de presença não redesenham a interface.

O contrato `integracao_hub.py` é copiado do nunes-hub, que mantém a fonte. Ele fornece identidade, saúde, parada e instância única, inclusive nos iniciadores console `find.py` e `move.py`. As entradas console continuam lendo `notas.txt` da pasta de trabalho e as mesmas variáveis de ambiente. Executáveis antigos em `dist` precisam ser reconstruídos para incorporar as mudanças.

## Instalação e validação

Python 3.10 ou superior, somente biblioteca padrão. Crie `.venv` com `python -m venv --without-pip .venv`. O CMD e o hub usam `.venv/Scripts/pythonw.exe`, com processo próprio e sem console. Para abrir diretamente pelo Python: `.venv/Scripts/python.exe notas.py`.

Execute `python -m unittest discover -s tests -v` e `node --test tests/test_notas_ui.cjs`. Em 16/10/2026 passaram 14 testes Python com arquivos temporários e dois JavaScript: formatos PDF/XML, filtros, cópia, movimentação, arquivos existentes, validação, cancelamento, HTTP local, várias abas, integração com o monitor e preservação do estado ocioso. Nenhuma operação em documentos reais foi necessária para esses testes.

Servidor em `127.0.0.1`, porta automática, token por execução, Host exato e validação de Origin nas ações. O servidor serve somente recursos explicitamente cadastrados. O processamento roda fora da requisição HTTP; a interface continua disponível durante a operação.

## Identidade e autoria

Ícone gerado pelo modelo aprovado em `estrutura-nunes/identidade-visual`, cadastrado como `find-move-nfe` na paleta central: azul petróleo **#0E7490**, símbolo branco preservado. Recursos em `icons/`, favicon e cabeçalho da interface, `icone.ico` para compatibilidade e `notas.svg` distribuído ao hub. O gerador sinalizou proximidade com o cinza ardósia da Impressão de OPs; a identificação também usa os nomes visíveis.

A assinatura segue `estrutura-nunes/identidade-visual/marca-pessoal/README.md`: **g2mello · Essencial**, com dois traços separados sob os `l`, link do GitHub e contraste nos temas claro e escuro. Não há sincronização automática com a fonte visual.

Criado por Gabriel Mello · [g2mello](https://github.com/Gabriel2Mello)
