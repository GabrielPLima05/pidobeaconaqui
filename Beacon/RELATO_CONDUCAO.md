# Beacon — Relato da condução do trabalho

**Base da verificação:** código-fonte do Beacon MVP em terminal e testes locais, revisados em 23/11/2026. A proposta original informada ao desenvolvimento também previa uma interface web React/Tailwind, IA, integração institucional e serviços de nuvem. **O documento formal de requisitos e a ata da última reunião não estavam disponíveis para confronto linha a linha.** A tabela deve ser reconciliada com esses documentos antes da avaliação.

## Tabela de escopo: previsto × realizado

| Item previsto | Realizado? | Evidência e considerações |
|---|---|---|
| Cadastro e login | **Sim (MVP)** | `beacon.py`: cadastro, login local, senha mascarada, salt e PBKDF2. Não equivale a autenticação de produção. |
| Receitas e despesas | **Sim** | Inclusão, listagem e exclusão; transações isoladas por usuário e valores em centavos. |
| Metas de economia | **Sim** | Criação, prazo, acompanhamento e atualização do reservado. |
| Cálculo de projeção e sugestão de cortes | **Parcial** | Motor matemático local calcula aportes e cortes exatos sobre gastos opcionais elegíveis; não realiza previsão estatística nem IA generativa. |
| Gráficos e relatórios | **Parcial em relação à proposta web** | Gráficos ASCII e dashboard no terminal; não há Recharts/Chart.js nem painel React. |
| Educação financeira e gamificação | **Parcial** | Capítulos, quiz, exercício e recomendações educativas por regras. Não há pontos, medalhas ou progressão avançada. |
| Assistente de chat com IA | **Não** | Substituído por FAQ predefinido por decisão de escopo do MVP. Sem integração com modelo de IA. |
| Perfil universitário/estagiário | **Sim (extra)** | Tipo de renda, referência conservadora e categorias protegidas. |
| Simulador de compras | **Sim (extra)** | Compras à vista, parcelas com/sem juros hipotéticos; efeito no orçamento e nas metas, sem transação automática. |
| Exportação CSV | **Sim** | CSV em `exportacoes/`, com tratamento para fórmulas em células. |
| Exportação PDF | **Sim (adicionado nesta revisão)** | Relatório financeiro mensal em PDF usando somente bibliotecas padrão. |
| Interface web em React/Tailwind/shadcn | **Não** | Entrega atual usa terminal Python e `iniciar_windows.bat`. Requer aceite explícito do orientador como escopo da entrega. |
| Layout dark mode, sidebar e login split screen | **Não** | Pertencem à interface web originalmente concebida. |
| Integração institucional B2B | **Não** | Não há contas institucionais, permissões ou API B2B. |
| Backend/API interoperável | **Não** | Uso local direto de SQLite, sem endpoints HTTP. |
| Hospedagem em AWS/GCP, 99,9% de uptime e resposta < 3 s | **Não aferido / não implementado** | Programa offline; não existe infraestrutura cloud nem testes de SLA. |
| LGPD, criptografia ponta a ponta, acessibilidade WCAG | **Não demonstrado integralmente** | Há proteção parcial de senha e segregação de dados, mas SQLite não é criptografado; WCAG é voltado à interface e não foi auditado. |
| Código-fonte integral no repositório | **Preparado, envio pendente de verificação** | Arquivos de fonte estão completos neste pacote. Necessário confirmar publicação na branch padrão do GitHub. |
| Histórico de commits | **Depende do GitHub real** | Não foi possível verificar o histórico do repositório e não foram gerados commits artificiais. |
| Trabalho em equipe | **Depende de evidências reais** | Registrar no GitHub issues, contribuições, autoria e/ou revisões; preencher a seção abaixo. |
| README, documentação e testes | **Sim no pacote** | `README.md`, este relato, guia de equipe, checklist e 28 testes locais aprovados. |

## Como o trabalho foi conduzido

1. Definição do problema: planejamento financeiro orientado a metas para estudantes e estagiários.
2. Escolha do recorte executável: aplicação offline de terminal com Python e SQLite, sem dependências de terceiros.
3. Construção de autenticação local, transações, dashboard e gráficos por categoria.
4. Implementação de metas e cálculo determinístico de aportes e cortes.
5. Inclusão de materiais didáticos, quiz e uso de dados de demonstração.
6. Inclusão de perfil universitário/estagiário, recomendações educativas por regras, FAQ e simulação de compras.
7. Revisão de segurança básica, validação de entrada, exportação de PDF e ampliação de testes.
8. Preparação do código-fonte e documentação para publicação **manual**.

## Evidência de trabalho colaborativo a preencher pela equipe

| Integrante | Responsabilidade real | Evidência verificável no GitHub (commit/PR/issue) |
|---|---|---|
| A preencher | A preencher | URL de commit, PR ou issue |
| A preencher | A preencher | URL de commit, PR ou issue |
| A preencher | A preencher | URL de commit, PR ou issue |

Não atribuir tarefas ou autoria sem comprovação. Não alterar artificialmente autores ou datas de commits.

## Considerações gerais para publicar no GitHub

- A pasta do repositório deve conter `beacon.py`, `iniciar_windows.bat`, `testar_windows.bat`, `README.md`, `testes/` e `materiais/` diretamente na raiz.
- O arquivo `.gitignore` impede o versionamento do banco local e das exportações. Verifique com cuidado as alterações antes do commit.
- O README descreve a execução, limitações e os principais diferenciais. Cada contribuição nova deve ter commit com mensagem descritiva e, quando houver trabalho conjunto, evidência de revisão por outro integrante.
- Conferir na branch principal o histórico real de commits, a documentação, as evidências de equipe e o funcionamento em um segundo computador.

## Conclusão

A edição de terminal está funcional e demonstrável, mas **não pode ser declarada como 100% da proposta web original**. O maior risco de avaliação é o requisito de cumprimento integral do escopo: é necessário que o orientador confirme formalmente o recorte do MVP (terminal, sem IA e sem B2B) ou que a equipe implemente as funcionalidades originais faltantes. O código-fonte e os testes fornecidos cobrem a versão terminal entregue, não uma plataforma comercial em nuvem.
