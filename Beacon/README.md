# Beacon — MVP de planejamento financeiro

**Versão acadêmica:** aplicativo de terminal em Python, com armazenamento local SQLite, cálculo determinístico de metas e cortes e educação financeira contextualizada. O Beacon não utiliza IA generativa nesta edição. Esta entrega corresponde ao **MVP em terminal**, não à plataforma web completa descrita no conceito original.

## Problema e proposta de valor

Um extrato ou gráfico ajuda a enxergar gastos, mas não informa necessariamente quais mudanças seriam suficientes para alcançar uma meta. O Beacon relaciona receitas, despesas obrigatórias, gastos opcionais e objetivos para propor cortes mensais matematicamente explícitos. A edição universitária protege categorias essenciais e trabalha com uma referência conservadora de renda quando ela varia.

## Funcionalidades disponíveis

| Recurso | Como funciona |
|---|---|
| Cadastro e login | Conta local, senha mascarada com `*`, derivação PBKDF2-SHA256 com salt individual |
| Transações | Cadastro, listagem e exclusão de receitas e despesas por usuário, categoria, data e obrigatoriedade |
| Painel financeiro | Saldo, totais e comprometimento de renda por mês |
| Gráficos no terminal | Barras por categoria e evolução de despesas em seis meses |
| Metas | Valor alvo, valor reservado, prazo, aporte mensal indicado |
| Plano de cortes | Redução de gastos opcionais elegíveis, limitada pelos lançamentos existentes e categorias protegidas |
| Perfil jovem | Universitário, estagiário ou ambos; renda fixa/variável/mista; proteção de categorias essenciais |
| Educação financeira | Capítulos, quiz, exemplo e recomendações por regras, sem acessar serviços externos |
| FAQ | 13 perguntas e respostas pré-definidas; pesquisa simples por termo |
| Simulador de compras | À vista, parcelas sem juros ou juros hipotéticos; comparação da folga financeira e das metas |
| Exportação CSV e PDF | Relatórios locais; PDF criado com a biblioteca padrão Python, sem instalação adicional |

## Requisitos para executar

- Windows 10/11 com Python 3.10 ou superior instalado e disponível como `py` ou `python`; também executável em macOS/Linux via terminal.
- Não há dependências de terceiros e não é necessário executar `pip install`.
- O programa é offline. O banco é criado localmente; **não** coloque dados financeiros pessoais reais de terceiros durante a apresentação.

## Iniciar o aplicativo

1. Extraia a pasta `Beacon` preservando `materiais/` e `testes/` ao lado de `beacon.py`.
2. No Windows, dê dois cliques em `iniciar_windows.bat`. Se houver problema, abra o PowerShell nessa pasta e rode `py -3 beacon.py` (ou `python beacon.py`).
3. No menu de acesso, escolha `2 - Criar conta`, forneça e-mail, nome, senha de 8 a 128 caracteres e confirmação.
4. Volte ao menu, escolha `1 - Entrar` e utilize seu cadastro.
5. Para ver um cenário completo, escolha a opção `7` e confirme o carregamento de **dados fictícios**. A opção é idempotente para os mesmos meses.
6. Ao finalizar, use `0 - Sair` e feche a janela.

A entrada de senha exibe `*` apenas para visualização da quantidade de caracteres. O programa não grava a senha em texto puro. O banco `beacon.db` é criado ao lado do arquivo Python e é excluído do Git pelo `.gitignore`.

## Mapa do menu

| Opção | Comando | Opção | Comando |
|---:|---|---:|---|
| 1 | Meu perfil | 10 | Atualizar valor reservado |
| 2 | Adicionar receita ou despesa | 11 | Planejamento e cortes |
| 3 | Listar transações | 12 | Trilha de educação financeira |
| 4 | Excluir transação | 13 | Perguntas frequentes |
| 5 | Painel financeiro mensal | 14 | Exportar CSV |
| 6 | Gráficos de despesas | 15 | Perfil universitário e estagiário |
| 7 | Carregar dados fictícios | 16 | Educação adaptativa por regras |
| 8 | Cadastrar meta | 17 | Simulador de compras |
| 9 | Consultar metas | 18 | Exportar relatório PDF |
| 0 | Sair | | |

## Demonstração em cinco minutos

1. Cadastre uma conta de demonstração. Use a opção `7`: os dados do mês atual terão receitas de **R$ 2.250,00**, despesas de **R$ 1.855,00** e saldo de **R$ 395,00**.
2. Abra `5` e `6` para mostrar os totais e gráficos. Os gastos opcionais fictícios somam R$ 605,00.
3. Em `8`, cadastre uma meta realista para as datas atuais e em `11` abra o planejamento de cortes. A soma de aportes e a insuficiência são calculadas a partir dos dados cadastrados; o resultado depende do prazo da meta.
4. Em `15`, escolha o perfil de estagiário, renda variável e as categorias protegidas. Abra `16` para explicar as recomendações de estudo; abra `13` para demonstrar o FAQ sem IA.
5. Em `17`, simule uma compra de **R$ 600,00** em **6 parcelas sem juros**. Sem metas, o saldo-base de R$ 395,00 cai para R$ 295,00 durante os meses com parcelas. O sistema não registra a compra no banco.
6. Use `14` ou `18` para exportar uma amostra e abra a pasta `exportacoes/` para exibir os arquivos.

## Regras e limites das projeções

- Valores financeiros são guardados como inteiros em centavos para evitar erros típicos de ponto flutuante.
- Aporte mensal indicativo = valor ainda necessário dividido pela quantidade de meses considerada pelo sistema, com arredondamento para cima em centavos.
- Corte adicional necessário = `max(0, total de aportes − (renda de referência − despesas))`. Cortes nunca são sugeridos sobre categorias protegidas e não excedem o total de gastos opcionais elegíveis.
- A referência conservadora, quando informada em perfil de renda variável/mista, limita a receita usada no planejamento ao menor valor entre a receita lançada e a referência.
- O simulador repete **como hipótese** o orçamento de um mês-base nos meses seguintes, aplica eventuais parcelas e mostra a folga financeira. Não prevê renda, inflação, inflação de preços, CET, rentabilidade, sazonalidade nem riscos futuros.
- A educação adaptativa é uma seleção por regras explícitas, **não um assistente de inteligência artificial**.

## Estrutura do projeto

```text
Beacon/
├── beacon.py
├── iniciar_windows.bat
├── testar_windows.bat
├── README.md
├── RELATO_CONDUCAO.md
├── GUIA_EQUIPE_GITHUB.md
├── CHECKLIST_AVALIACAO.md
├── ROTEIRO_APRESENTACAO.md
├── .gitignore
├── materiais/
│   ├── 01_orcamento.md ... 08_vida_academica.md
│   ├── GABARITO.md
│   ├── FONTES.md
│   └── DADOS_FICTICIOS.csv
└── testes/
    ├── test_beacon.py
    ├── test_novidades.py
    └── test_qualidade.py
```

**Código-fonte:** as regras, consultas SQL, autenticação, interface textual e PDF estão integralmente disponíveis em `beacon.py`; não são usados componentes compilados ou serviços ocultos. `iniciar_windows.bat` apenas define UTF-8, localiza o Python, inicia `beacon.py` e mantém o console aberto ao fim. O arquivo `.bat` serve para reduzir a barreira de execução em Windows.

**Banco:** `users`, `transactions`, `goals` e `student_profiles`, criadas automaticamente. Consultas usam parâmetros SQL e filtragem por `user_id`, impedindo que operações usuais cruzem contas pelo ID fornecido no menu. O banco SQLite **não possui criptografia integral**.

## Testes e manutenção

Execute no PowerShell:

```powershell
py -3 -m unittest discover -s testes -v
```

Ou dê dois cliques em `testar_windows.bat`. A suíte contém **22 testes automatizados** de cálculos, integridade monetária, dados fictícios, exportação, perfis, validações, PDF, autenticidade do PDF e isolamento por usuário. O resultado nesta entrega foi `22 tests ... OK`. Isso não equivale a uma auditoria formal de segurança ou usabilidade em todos os sistemas operacionais.

Para preservar dados antigos: feche o programa, faça backup do arquivo `beacon.db`, atualize os arquivos do projeto e execute novamente. Não mova o `.db` para o GitHub. Caso o sistema apresente erro de banco, restaure a cópia de segurança e consulte o erro impresso no terminal.

## Limitações e escopo não realizado

A proposta original previa aplicativo **React/Tailwind com layout desktop/mobile**, assistência de IA generativa, integrações institucionais B2B, nuvem AWS/GCP com meta de disponibilidade, APIs, criptografia ponta a ponta e conformidade abrangente à LGPD. Essas frentes **não foram implementadas** no MVP de terminal e não devem ser apresentadas como finalizadas sem aceite explícito do orientador. Não há conexão com bancos, gateways de pagamentos ou serviços externos. A autenticação local não é suficiente para lançamento comercial com dados financeiros reais.

## Documentação da avaliação

- [Relato da condução e tabela previsto × realizado](RELATO_CONDUCAO.md)
- [Checklist dos critérios de avaliação](CHECKLIST_AVALIACAO.md)
- [Guia de trabalho em equipe e publicação manual](GUIA_EQUIPE_GITHUB.md)
- [Roteiro de apresentação (10–15 minutos)](ROTEIRO_APRESENTACAO.md)
- [Fontes dos conteúdos educativos](materiais/FONTES.md)

## Referências didáticas

A trilha inclui materiais originais e cita as fontes oficiais em `materiais/FONTES.md`: Banco Central do Brasil, CVM, Tesouro Direto e CAIXA. As informações não são cotações atualizadas em tempo real nem recomendações de investimento. Dados fictícios não correspondem a usuários reais.

## Participação da equipe e histórico

O histórico e a colaboração devem ser comprovados pelo **repositório real**, em commits e/ou pull requests com autoria legítima. Consulte `GUIA_EQUIPE_GITHUB.md`. O ZIP distribuído não contém um histórico Git artificial e não executa commits automáticos.
