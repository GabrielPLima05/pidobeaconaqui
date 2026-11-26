const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const state = { user: null, csrf: null, page: 'dashboard', authMode: 'login', dashboardMonth: '', transactionsMonth: '', faq: [], toastTimer: null };
const currency = new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'});
const amount = value => currency.format(Number(value || 0));
const encode = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const monthNow = () => {const d = new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`};
const dateNow = () => {const d = new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const formObject = form => Object.fromEntries(new FormData(form).entries());
const monthShort = month => {const [y,m] = month.split('-');return `${['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'][Number(m)-1]}/${y.slice(2)}`};
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));

function toast(text, isError=false){
  const node=$('#toast'); node.textContent=text;node.classList.toggle('error',isError);node.hidden=false;
  clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>node.hidden=true,4800);
}
async function api(path, opts={}){
  const headers = {'Accept':'application/json'};
  if(opts.body!==undefined){headers['Content-Type']='application/json';}
  if(opts.method && opts.method!=='GET' && state.csrf){headers['X-Beacon-CSRF']=state.csrf;}
  const response=await fetch(path,{method:opts.method||'GET',credentials:'same-origin',headers,body:opts.body!==undefined?JSON.stringify(opts.body):undefined});
  let data={};try{data=await response.json()}catch{}
  if(!response.ok){if(response.status===401&&state.user){showAuth();toast('Sua sessão expirou. Entre novamente.',true)}throw new Error(data.error||`Não foi possível concluir a solicitação (${response.status}).`)}
  return data;
}
async function action(work,success){
  try {const result=await work();if(success)toast(success);return result}
  catch(err){toast(err.message||'Erro inesperado.',true);return null}
}
function showAuth(){state.user=null;state.csrf=null;$('#app-shell').hidden=true;$('#auth-screen').hidden=false;$('#auth-email').focus()}
function showApp(user,csrf){state.user=user;state.csrf=csrf;$('#auth-screen').hidden=true;$('#app-shell').hidden=false;$('#user-name').textContent=user.name.split(' ')[0];$('#user-initials').textContent=user.name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase();$('#profile-name').textContent=user.name;$('#profile-email').textContent=user.email;showPage('dashboard')}
function setAuthMode(mode){
  state.authMode=mode;$$('.auth-tab').forEach(el=>el.classList.toggle('active',el.dataset.authMode===mode));
  const register=mode==='register';$('#name-label').hidden=!register;$('#confirm-label').hidden=!register;
  $('#auth-name').required=register;$('#auth-confirm').required=register;
  $('#auth-heading').textContent=register?'Crie sua conta':'Entre na sua conta';
  $('#auth-subheading').textContent=register?'Inicie sua jornada de planejamento.':'Acesse seu painel financeiro pessoal.';
  $('#auth-submit').textContent=register?'Criar minha conta →':'Entrar na plataforma →';
  $('#auth-password').setAttribute('autocomplete',register?'new-password':'current-password');
  $('#auth-error').textContent='';
}
async function submitAuth(event){
  event.preventDefault();$('#auth-error').textContent='';
  const data={name:$('#auth-name').value,email:$('#auth-email').value,password:$('#auth-password').value,confirm:$('#auth-confirm').value};
  $('#auth-submit').disabled=true;
  try{
    if(state.authMode==='register'){
      await api('/api/auth/register',{method:'POST',body:data});setAuthMode('login');$('#auth-password').value='';$('#auth-confirm').value='';toast('Conta criada. Entre com suas credenciais.');
    }else{
      const res=await api('/api/auth/login',{method:'POST',body:data});$('#auth-password').value='';showApp(res.user,res.csrf);
    }
  }catch(err){$('#auth-error').textContent=err.message;}finally{$('#auth-submit').disabled=false}
}
const PAGE_NAMES = {dashboard:'Visão geral',transactions:'Transações',goals:'Metas e objetivos',planning:'Plano de economia',purchase:'Simulador de compras',education:'Educação financeira',faq:'Perguntas frequentes',profile:'Meu perfil',exports:'Relatórios'};
async function showPage(name){
  if(!PAGE_NAMES[name])return;
  state.page=name;
  $$('.app-page').forEach(el=>el.classList.toggle('active',el.id===`page-${name}`));
  $$('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.page===name));
  $('#breadcrumb-title').textContent=PAGE_NAMES[name];$('#sidebar').classList.remove('open');window.scrollTo({top:0,behavior:'instant'});
  const loaders={dashboard:loadDashboard,transactions:loadTransactions,goals:loadGoals,planning:loadPlan,education:loadEducation,faq:loadFAQ,profile:loadProfile};
  if(loaders[name]){await action(()=>loaders[name]());}
}
function asEmpty(text){return `<div class="empty-state">${encode(text)}</div>`}
function renderCategoryChart(d){
  const node=$('#donut-chart');const legend=$('#spending-legend');const total=d.expense;
  $('#donut-total').textContent=amount(total);
  if(!total){node.style.background='#282235';legend.innerHTML=asEmpty('Sem despesas neste mês.');return}
  const colors=['#8d35df','#e63169','#bc6eff','#fb75aa','#6340a8','#e985c3','#a9a2bc','#ffb3d2'];
  let offset=0;
  const stops=d.categories.map((c,i)=>{const width=c.amount/total*100;const item=`${colors[i%colors.length]} ${offset}% ${offset+width}%`;offset+=width;return item;});
  node.style.background=`conic-gradient(${stops.join(',')})`;
  legend.innerHTML=d.categories.slice(0,8).map((item,i)=>`<div class="legend-row"><span class="legend-dot" style="background:${colors[i%colors.length]}"></span><span class="legend-label" title="${encode(item.name)}">${encode(item.name)}</span><span class="legend-pct">${(item.amount/total*100).toFixed(0)}%</span><strong class="legend-value">${amount(item.amount)}</strong></div>`).join('');
}
function renderTrend(d){
  const node=$('#trend-chart');const ceiling=Math.max(...d.trend.flatMap(item=>[item.income,item.expense]),1);
  node.innerHTML=d.trend.map(row=>`<div class="trend-group"><div class="trend-bars"><div title="Receitas ${monthShort(row.month)}: ${amount(row.income)}" class="trend-bar purple-bg" style="height:${Math.max(2,row.income/ceiling*160)}px"></div><div title="Despesas ${monthShort(row.month)}: ${amount(row.expense)}" class="trend-bar crimson-bg" style="height:${Math.max(2,row.expense/ceiling*160)}px"></div></div><span class="trend-label">${monthShort(row.month)}</span></div>`).join('');
}
async function loadDashboard(){
  const month=$('#dashboard-month').value||monthNow();state.dashboardMonth=month;
  const [d,plan,education]=await Promise.all([api('/api/dashboard?month='+encodeURIComponent(month)),api('/api/plan'),api('/api/education')]);
  $('#metric-income').textContent=amount(d.income);$('#metric-expense').textContent=amount(d.expense);$('#metric-balance').textContent=amount(d.balance);$('#metric-optional').textContent=amount(d.optional);
  $('#metric-balance').style.color=d.balance<0?'#fa729c':'';
  renderCategoryChart(d);renderTrend(d);
  $('#summary-monthly').textContent=amount(plan.goalMonthly);
  const advice=plan.goals.length===0?'Cadastre metas para acompanhar o valor necessário a cada mês.':plan.needed<=0?'No cenário atual, o saldo cobre seus aportes mensais.':`Você precisa de ${amount(plan.needed)} adicionais por mês para cumprir os aportes.`;
  $('#summary-advice').textContent=advice;
  $('#dashboard-recommendations').innerHTML=education.recommended.slice(0,2).map(x=>`<div class="recommendation-mini-item"><strong>${encode(x.title)}</strong><small>${encode(x.reason)}</small></div>`).join('');
  $('#empty-help').hidden=d.transactionCount!==0;
}
async function loadTransactions(){
  const month=$('#transactions-month').value;
  const d=await api('/api/transactions'+(month?'?month='+encodeURIComponent(month):''));
  $('#transaction-rows').innerHTML=d.transactions.length?d.transactions.map(x=>`<tr><td>${x.date.split('-').reverse().join('/')}</td><td><strong>${encode(x.description)}</strong></td><td>${encode(x.category)} ${x.optional?'<small>Gasto opcional</small>':''}</td><td><span class="kind-pill ${x.kind==='despesa'?'expense':''}">${x.kind==='despesa'?'Despesa':'Receita'}</span></td><td class="${x.kind==='despesa'?'amount-expense':'amount-income'}">${x.kind==='despesa'?'−':'+'} ${amount(x.amount)}</td><td><button class="row-btn" data-delete-transaction="${x.id}" aria-label="Excluir transação">Excluir</button></td></tr>`).join(''):`<tr><td colspan="6">${asEmpty('Nenhuma transação encontrada para este filtro.')}</td></tr>`;
}
async function submitTransaction(event){
  event.preventDefault();const form=event.target;const body=formObject(form);body.optional=form.elements.optional.checked;
  const res=await action(()=>api('/api/transactions',{method:'POST',body}),'Transação salva com sucesso.');
  if(res){form.reset();$('#transaction-date').value=dateNow();$('#transaction-kind').value='despesa';$('#optional-label').hidden=false;await loadTransactions()}
}
async function loadGoals(){
  const {goals}=await api('/api/goals');const node=$('#goals-list');
  node.innerHTML=goals.length?goals.map(g=>{const fraction=g.target?Math.min(100,g.saved/g.target*100):0;
    return `<article class="goal-card"><h3>${encode(g.name)}</h3><span class="goal-date">Prazo: ${g.deadline.split('-').reverse().join('/')}</span><div class="goal-target">${amount(g.target)}</div><div class="progress-track"><div class="progress-fill" style="width:${fraction}%"></div></div><div class="goal-details"><span>Reservado: ${amount(g.saved)}</span><span>${fraction.toFixed(0)}%</span></div><div class="goal-monthly">${g.months?`Aporte mensal indicativo: <b>${amount(g.monthly)}</b>`:'Prazo vencido: atualize seu plano.'}</div><div class="goal-actions"><button class="btn btn-outline" data-edit-goal="${g.id}" data-saved="${g.saved}">Atualizar reservado</button><button class="btn btn-outline" data-delete-goal="${g.id}">Excluir</button></div></article>`}).join(''):asEmpty('Nenhuma meta cadastrada. Crie seu primeiro objetivo acima.');
}
async function submitGoal(event){
  event.preventDefault();const form=event.target;const body=formObject(form);
  const res=await action(()=>api('/api/goals',{method:'POST',body}),'Meta cadastrada com sucesso.');
  if(res){form.reset();$('#goal-deadline').value='';await loadGoals()}
}
async function loadPlan(){
  const d=await api('/api/plan');const node=$('#planning-content');
  let information='';
  if(!d.goals.length)information='<div class="plan-warning">Cadastre pelo menos uma meta para calcular aportes e sugestões de cortes.</div>';
  else if(!d.hasTransactions)information='<div class="plan-warning">Cadastre receitas e despesas no mês atual para calcular seu plano.</div>';
  else if(d.needed===0)information='<div class="plan-ok">O saldo calculado cobre o aporte previsto. Não é necessário cortar gastos adicionais neste cenário.</div>';
  else if(d.unmet>0)information=`<div class="plan-warning">Mesmo após os cortes elegíveis, faltariam ${amount(d.unmet)} por mês. Revise prazo, meta ou orçamento.</div>`;
  else information='<div class="plan-ok">Os cortes sugeridos cobrem a diferença calculada, se forem mantidos e as demais premissas permanecerem constantes.</div>';
  node.innerHTML=`<div class="plan-stats"><article class="metric-card purple-accent"><span>Saldo usado no cálculo</span><strong>${amount(d.balance)}</strong><small>${d.conservative?'Referência conservadora de renda':'Receitas − despesas'}</small></article><article class="metric-card pink-accent"><span>Aporte mensal total</span><strong>${amount(d.goalMonthly)}</strong><small>Somatório das metas vigentes</small></article><article class="metric-card crimson-accent"><span>Redução necessária</span><strong>${amount(d.needed)}</strong><small>Diferença a recuperar por mês</small></article></div><article class="panel plan-card"><div class="panel-head"><div><h3>Estratégia de redução sugerida</h3><p>Somente gastos opcionais fora das categorias protegidas.</p></div><span class="panel-tag">REGRAS MATEMÁTICAS</span></div>${d.cuts.length?d.cuts.map(c=>`<div class="cut-row"><strong>${encode(c.category)}</strong><span>de ${amount(c.amount)}</span><strong>Reduzir ${amount(c.cut)}</strong></div>`).join(''):`<div class="plan-empty">Sem cortes sugeridos para este cenário.</div>`}${information}</article><article class="panel"><h3>Como o cálculo funciona?</h3><p>O Beacon calcula quanto falta em cada meta, divide o valor pelos meses restantes e compara com o saldo do orçamento. Se houver déficit, indica cortes nas maiores categorias opcionais elegíveis, sem alterar os lançamentos.</p><p>Metodologia ilustrativa, sem IA generativa, rentabilidade de investimentos, sazonalidade ou previsão garantida de renda.</p></article>`;
}
function purchaseStatus(result){
  if(result.warning==='existing-shortfall')return ['Seu orçamento-base já apresenta insuficiência em pelo menos um mês, antes desta compra.','plan-warning'];
  if(result.warning==='new-shortfall')return ['A compra cria insuficiência em pelo menos um mês após os aportes planejados.','plan-warning'];
  if(result.warning==='low-margin')return ['A compra não gera saldo negativo no cenário, mas deixa margem financeira reduzida.','plan-warning'];
  return ['As despesas, parcelas e aportes cabem no orçamento projetado segundo as premissas informadas.','plan-ok'];
}
async function loadDemoData(source){
  if(!await confirmDialog('Adicionar receitas e despesas FICTÍCIAS à conta atual para testes? Os lançamentos terão a identificação DEMO | e não substituirão seus registros.'))return;
  const button=$(source==='purchase'?'#purchase-demo-button':'#load-demo-button');
  button.disabled=true;
  try{
    const data=await api('/api/demo',{method:'POST',body:{}});
    const message=data.created?`${data.created} lançamentos fictícios adicionados para demonstração.`:'Os lançamentos fictícios desses meses já estão cadastrados. Nenhuma duplicação foi realizada.';
    toast(message);
    if(source==='purchase'){
      const form=$('#purchase-form');
      form.elements.label.value='Notebook para estudos (exemplo)';
      form.elements.amount.value='600,00';
      form.elements.installments.value='6';
      form.elements.monthlyRate.value='0';
      form.elements.month.value=monthNow();
      const result=$('#purchase-results');result.hidden=true;result.innerHTML='';
      const status=$('#purchase-demo-status');status.textContent=message+' Compra de teste preenchida: R$ 600 em 6 parcelas sem juros. Clique em “Simular impacto da compra” para ver o resultado.';status.hidden=false;
      form.elements.amount.focus();
    }else{
      $('#dashboard-month').value=monthNow();
      await loadDashboard();
    }
  }catch(err){toast(err.message||'Não foi possível carregar os exemplos.',true)}
  finally{button.disabled=false}
}
async function submitPurchase(event){
  event.preventDefault();const body=formObject(event.target);
  const d=await action(()=>api('/api/purchase',{method:'POST',body}));if(!d)return;
  const [message,cls]=purchaseStatus(d);
  const node=$('#purchase-results');node.hidden=false;
  node.innerHTML=`<div class="result-header"><div class="result-mini"><span>Valor da compra</span><strong>${amount(d.amount)}</strong></div><div class="result-mini"><span>Primeira parcela</span><strong>${amount(d.payment)}</strong></div><div class="result-mini"><span>Total das parcelas</span><strong>${amount(d.total)}</strong></div><div class="result-mini"><span>Juros estimados</span><strong>${amount(d.interest)}</strong></div></div><article class="panel"><div class="panel-head"><div><h3>Impacto no seu orçamento</h3><p>Projeção ilustrativa do mês atual e seguintes.</p></div></div><div class="${cls}">${message}</div><div class="table-wrap purchase-result-table"><table><thead><tr><th>Mês</th><th>Parcela</th><th>Aportes às metas</th><th>Folga antes</th><th>Folga após a compra</th></tr></thead><tbody>${d.projection.map(row=>`<tr><td>${monthShort(row.month)}</td><td>${amount(row.payment)}</td><td>${amount(row.goal)}</td><td>${amount(row.before)}</td><td class="${row.after<0?'amount-expense':''}">${amount(row.after)}</td></tr>`).join('')}</tbody></table></div><p style="font-size:11px;margin-top:16px">Premissas: receitas e despesas do mês-base repetidas nos meses futuros. Juros e parcelas são estimativas, sem incorporar CET, impostos ou mudanças de renda.</p></article>`;
}
async function loadEducation(){
  const d=await api('/api/education');
  $('#education-recommendations').innerHTML=d.recommended.map(x=>`<button type="button" class="recommendation-tile" data-material="${encode(x.file)}"><strong>${encode(x.title)} →</strong><span>${encode(x.reason)}</span></button>`).join('');
  $('#materials-grid').innerHTML=d.materials.map((m,i)=>`<button type="button" class="material-card" data-material="${encode(m.file)}"><span class="material-number">MATERIAL ${String(i+1).padStart(2,'0')}</span><strong>${encode(m.title)} →</strong><p>${encode(m.description)}</p></button>`).join('');
}
async function openMaterial(name){
  const d=await action(()=>api('/api/material/'+encodeURIComponent(name)));if(!d)return;
  $('#reader-title').textContent=d.file.replace(/_+/g,' ').replace('.md','');
  $('#reader-content').textContent=d.content;
  $('#reader-panel').hidden=false;$('#reader-panel').scrollIntoView({behavior:'smooth',block:'start'});
}
async function loadFAQ(){const d=await api('/api/faq');state.faq=d.items;renderFAQ('')}
function renderFAQ(query){
  const key=query.toLocaleLowerCase('pt-BR');const filtered=state.faq.filter(x=>(x.question+' '+x.answer).toLocaleLowerCase('pt-BR').includes(key));
  $('#faq-list').innerHTML=filtered.length?filtered.map(x=>`<details><summary>${encode(x.question)}</summary><p>${encode(x.answer)}</p></details>`).join(''):asEmpty('Nenhuma pergunta encontrada. Tente outro termo.');
}
async function loadProfile(){
  const profile=await api('/api/profile');const f=$('#profile-form');
  f.elements.role.value=profile.role;f.elements.incomePattern.value=profile.incomePattern;
  f.elements.conservativeIncome.value=String(profile.conservativeIncome).replace('.',',');f.elements.protectedCategories.value=profile.protectedCategories;
}
async function submitProfile(event){event.preventDefault();const res=await action(()=>api('/api/profile',{method:'POST',body:formObject(event.target)}),'Perfil atualizado.');if(res)await loadProfile()}
async function downloadExport(path,name){
  try{
    const r=await fetch(path,{credentials:'same-origin'});
    if(!r.ok){const data=await r.json();throw new Error(data.error||'Falha na exportação.')}
    const file=await r.blob();const url=URL.createObjectURL(file);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);toast('Arquivo preparado para download.');
  }catch(err){toast(err.message,true)}
}
function confirmDialog(message){
  return new Promise(resolve=>{
    const overlay=$('#confirm-overlay');$('#confirm-text').textContent=message;overlay.hidden=false;$('#confirm-no').focus();
    const yes=$('#confirm-yes'),no=$('#confirm-no');
    function done(result){overlay.hidden=true;yes.removeEventListener('click',accept);no.removeEventListener('click',reject);document.removeEventListener('keydown',escape);resolve(result)}
    const accept=()=>done(true);const reject=()=>done(false);const escape=e=>{if(e.key==='Escape')done(false)};
    yes.addEventListener('click',accept);no.addEventListener('click',reject);document.addEventListener('keydown',escape);
  });
}
async function delegatedClick(event){
  const navigate=event.target.closest('[data-page],[data-goto]');if(navigate){await showPage(navigate.dataset.page||navigate.dataset.goto);return}
  const transaction=event.target.closest('[data-delete-transaction]');if(transaction){
    const yes=await confirmDialog('Excluir esta transação? O lançamento será removido permanentemente.');if(!yes)return;
    const res=await action(()=>api('/api/transactions/'+transaction.dataset.deleteTransaction,{method:'DELETE'}),'Transação excluída.');
    if(res)await loadTransactions();return;
  }
  const goal=event.target.closest('[data-delete-goal]');if(goal){
    const yes=await confirmDialog('Excluir esta meta? A ação não poderá ser desfeita.');if(!yes)return;
    const res=await action(()=>api('/api/goals/'+goal.dataset.deleteGoal,{method:'DELETE'}),'Meta excluída.');if(res)await loadGoals();return;
  }
  const edit=event.target.closest('[data-edit-goal]');if(edit){
    const saved=prompt('Novo valor TOTAL reservado na meta (R$):',String(edit.dataset.saved).replace('.',','));if(saved===null)return;
    const res=await action(()=>api('/api/goals/'+edit.dataset.editGoal,{method:'PATCH',body:{saved}}),'Valor reservado atualizado.');if(res)await loadGoals();return;
  }
  const mat=event.target.closest('[data-material]');if(mat){await openMaterial(mat.dataset.material);return}
}
async function boot(){
  const initial=monthNow();$('#dashboard-month').value=initial;$('#purchase-month').value=initial;$('#export-month').value=initial;
  $('#transaction-date').value=dateNow();$('#goal-deadline').min=dateNow();
  $('#auth-form').addEventListener('submit',submitAuth);
  $$('[data-auth-mode]').forEach(b=>b.addEventListener('click',()=>setAuthMode(b.dataset.authMode)));
  $('#toggle-password').addEventListener('click',()=>{const input=$('#auth-password');const visible=input.type==='password';input.type=visible?'text':'password';$('#toggle-password').textContent=visible?'Ocultar':'Mostrar'});
  document.addEventListener('click',delegatedClick);
  $('#mobile-toggle').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
  $('#dashboard-month').addEventListener('change',()=>action(loadDashboard));
  $('#transactions-month').addEventListener('change',()=>action(loadTransactions));
  $('#refresh-transactions').addEventListener('click',()=>action(loadTransactions));
  $('#transaction-form').addEventListener('submit',submitTransaction);
  $('#transaction-kind').addEventListener('change',event=>$('#optional-label').hidden=event.target.value!=='despesa');
  $('#goal-form').addEventListener('submit',submitGoal);
  $('#purchase-form').addEventListener('submit',submitPurchase);
  $('#purchase-demo-button').addEventListener('click',()=>loadDemoData('purchase'));
  $('#profile-form').addEventListener('submit',submitProfile);
  $('#faq-search').addEventListener('input',event=>renderFAQ(event.target.value));
  $('#reader-close').addEventListener('click',()=>$('#reader-panel').hidden=true);
  $('#export-csv').addEventListener('click',()=>downloadExport('/api/export/csv','beacon_transacoes.csv'));
  $('#export-pdf').addEventListener('click',()=>{const month=$('#export-month').value||monthNow();downloadExport('/api/export/pdf?month='+encodeURIComponent(month),`beacon_relatorio_${month}.pdf`)});
  $('#load-demo-button').addEventListener('click',()=>loadDemoData('dashboard'));
  $('#logout-button').addEventListener('click',async()=>{await action(()=>api('/api/auth/logout',{method:'POST',body:{}}));showAuth()});
  setAuthMode('login');
  try{const result=await api('/api/session');showApp(result.user,result.csrf)}catch{showAuth()}
}
window.addEventListener('DOMContentLoaded',boot);
