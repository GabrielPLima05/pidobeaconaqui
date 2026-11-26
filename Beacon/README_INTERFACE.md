# Beacon — Interface Visual Funcional (MVP local)

O Beacon agora tem interface visual no navegador, com menu lateral, formulários e gráficos alimentados por dados reais do SQLite. **Não é apenas uma imagem:** todas as telas consultam e atualizam o banco pelo backend Python.

## 1. Como executar no Windows

1. Instale **Python 3.10 ou superior** e marque **Add Python to PATH**, se disponível.
2. Extraia todo o ZIP para uma pasta no computador.
3. Se você já utiliza o Beacon, **feche o aplicativo antigo** e faça backup do arquivo `beacon.db`.
4. Copie o arquivo `beacon.db` antigo para a pasta do novo Beacon, ao lado de `beacon.py`. Não renomeie nem apague as outras pastas.
5. Abra **`iniciar_windows.bat`**. O navegador abrirá automaticamente em `http://127.0.0.1:8765`.
6. Se o navegador não abrir, digite esse endereço manualmente, mantendo a janela de execução aberta.
7. Faça login com a conta existente ou crie uma nova. Para encerrar o servidor, pressione **Ctrl+C** na janela de comando.

Você também pode executar com `py -3 web_app.py` no PowerShell. Se a porta 8765 estiver ocupada, execute `set BEACON_PORT=8766` no CMD antes de iniciar, ou `$env:BEACON_PORT='8766'` no PowerShell.

**Requisitos:** Python 3.10+ e navegador moderno. Sem Flask, Node, npm, pacotes externos ou instalação adicional de Python.

## 2. Como utilizar

- **Visão geral:** receitas, despesas, saldo, gastos opcionais, gráfico por categoria e evolução mensal.
- **Transações:** registrar e excluir receitas/despesas, consultar por mês, identificar gastos opcionais.
- **Metas:** criar, acompanhar, atualizar valor já reservado e excluir objetivos.
- **Plano de economia:** total de aportes e cortes matemáticos em despesas opcionais não protegidas.
- **Simular compra:** avaliar pagamento à vista ou parcelado, com juros hipotéticos e impacto nas metas. A simulação não cria movimentação real.
  - Na mesma aba, clique em **Carregar dados fictícios para teste** para incluir lançamentos de exemplo dos últimos três meses e preencher uma simulação de R$ 600 em seis parcelas sem juros. Confirme a operação antes de gravar os exemplos.
  - Os lançamentos de demonstração são identificados por `DEMO |`, são adicionados à conta que estiver conectada e não são duplicados quando se usa o botão novamente nos mesmos meses. A compra simulada não é registrada como despesa.
  - Para evitar misturar registros fictícios com dados pessoais, recomenda-se usar uma conta exclusiva para testes.
- **Educação financeira:** materiais, fontes, explicações e recomendações determinadas por regras.
- **Perguntas frequentes:** respostas predefinidas, sem IA.
- **Meu perfil:** perfil universitário/estagiário, renda conservadora e proteção de categorias essenciais.
- **Relatórios:** exportar CSV e PDF, diretamente pelo navegador.

Quando não houver lançamentos, o dashboard oferece a opção de **carregar dados fictícios** para experimentação. Essa ação exige confirmação e não duplica os exemplos do mesmo mês.

## 3. Estrutura técnica

```text
Beacon_Visual/
├── beacon.py                Motor original do aplicativo e terminal
├── web_app.py               Backend HTTP local com endpoints JSON
├── static/
│   ├── index.html           Estrutura da interface
│   ├── app.css              Identidade visual preta, roxa e carmesim
│   └── app.js               Navegação, formulários e gráficos
├── materiais/               Textos educativos e fontes
├── testes/                  Testes do motor e da interface
├── iniciar_windows.bat      Abre a interface visual
├── iniciar_terminal.bat     Abre a versão anterior do terminal
└── testar_windows.bat       Executa a suíte automatizada
```

O arquivo `beacon.db` é criado automaticamente quando não existe. O mesmo banco pode ser utilizado pelo terminal e pela interface visual, **mas evite abrir os dois ao mesmo tempo**.

## 4. Segurança e limitações

O serviço HTTP **escuta apenas `127.0.0.1`**, e não fica publicado na internet. O login usa hashes PBKDF2 e sessões temporárias em memória, com cookie `HttpOnly` e proteção CSRF nas alterações. Não há compartilhamento de dados com serviços externos.

O banco SQLite **não é criptografado integralmente**. Este projeto é um MVP acadêmico/local, não um serviço comercial pronto para produção. Não abra portas no roteador nem exponha o servidor à rede externa. Use dados fictícios em demonstrações públicas e mantenha backups locais.

Projeções financeiras são **ilustrativas e determinísticas**. O assistente com IA generativa, sincronização bancária, cobranças, anúncios e módulos B2B ainda não foram implementados.

## 5. Testes e publicação

No Windows, execute `testar_windows.bat`. Também pode usar:

```powershell
py -3 -m unittest discover -s testes -v
```

Para atualizar o repositório GitHub, copie os arquivos atuais do projeto para a raiz do repositório (sem copiar `beacon.db`). Mantenha a pasta `.git` existente. O programa é executado localmente sem hospedagem.
