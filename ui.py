"""ui.py - the single-page web UI, embedded so no static files are needed."""
HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inventory Management</title>
<style>
:root{--bg:#f6f7f9;--fg:#1c2330;--card:#fff;--line:#dfe3ea;--pri:#2457d6;--bad:#c0392b;--mut:#6b7385}
@media(prefers-color-scheme:dark){:root{--bg:#12151b;--fg:#e6e9ef;--card:#1b1f27;--line:#2c323e;--pri:#6b94ff;--bad:#ff7a6b;--mut:#9aa3b5}}
*{box-sizing:border-box}body{margin:0;font:14px system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header{display:flex;justify-content:space-between;align-items:center;padding:10px 16px;background:var(--card);border-bottom:1px solid var(--line)}
nav{display:flex;gap:4px;flex-wrap:wrap;padding:8px 16px}nav button{background:none;border:1px solid transparent}
nav button.on{border-color:var(--pri);color:var(--pri)}main{padding:8px 16px 40px;max-width:1100px;margin:auto}
button,input,select,textarea{font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:6px 10px}
button{cursor:pointer}button.pri{background:var(--pri);color:#fff;border-color:var(--pri)}button.bad{color:var(--bad)}button:disabled{opacity:.4}
.tw{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:8px;margin:8px 0}
table{border-collapse:collapse;width:100%}th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--mut);font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:10px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}.card small{color:var(--mut);display:block}.card b{font-size:22px}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0}.pg{display:flex;gap:10px;align-items:center;justify-content:flex-end}
.low{color:var(--bad);font-weight:600}#login,#register{max-width:360px;margin:15vh auto;display:grid;gap:10px;padding:20px;background:var(--card);border:1px solid var(--line);border-radius:10px}
dialog{border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--fg);min-width:min(92vw,380px)}dialog label{display:grid;gap:3px;margin:8px 0}
dialog menu{display:flex;gap:8px;justify-content:flex-end;padding:0}#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);padding:10px 16px;border-radius:8px;background:var(--fg);color:var(--bg);display:none;max-width:90vw}
</style>
</head>
<body>
<form id="login"><h2>Inventory Login</h2><input id="lu" placeholder="Username" autocomplete="username" required><input id="lp" type="password" placeholder="Password" autocomplete="current-password" required><button class="pri">Sign in</button><button type="button" id="showreg">Create account</button></form><form id="register" hidden><h2>Create account</h2><input id="ru" placeholder="Username (3-30)" required pattern="[a-z0-9_.]{3,30}"><input id="rn" placeholder="Full name" required><input id="rp" type="password" placeholder="Password (8+, letters + digits)" required><input id="rc" type="password" placeholder="Confirm password" required><button class="pri">Register</button><button type="button" id="backlogin">Back to login</button></form>
<div id="app" hidden>
<header><b>📦 Inventory</b><span><span id="who"></span> <button id="pw">Password</button> <button id="out">Log out</button></span></header>
<nav id="nav"></nav><main id="view"></main></div>
<dialog id="dlg"></dialog><div id="toast"></div>
<script>
const S={token:sessionStorage.getItem('t')||'',me:null,page:'',Q:{}};
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>Number(n||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const can=p=>S.me&&S.me.permissions.includes(p);
const qs=o=>new URLSearchParams(Object.entries(o).filter(([,v])=>v!==''&&v!=null)).toString();
function toast(m){const t=$('#toast');t.textContent=m;t.style.display='block';clearTimeout(toast.t);toast.t=setTimeout(()=>t.style.display='none',4500)}
async function api(path,method='GET',body){
  const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json',...(S.token?{Authorization:'Bearer '+S.token}:{})},body:body?JSON.stringify(body):undefined});
  const j=await r.json().catch(()=>({error:'Bad server response'}));
  if(r.status===401&&S.token&&path!=='/login'){logout();throw new Error('Session expired')}
  if(!r.ok)throw new Error(j.error+(j.details&&j.details.length?': '+j.details.join('; '):''));
  return j}
const guard=f=>async(...a)=>{try{return await f(...a)}catch(e){toast(e.message)}};
function table(cols,rows){return `<div class=tw><table><tr>${cols.map(c=>`<th>${c[0]}</th>`).join('')}</tr>${rows.map(r=>`<tr>${cols.map(c=>`<td>${c[1](r)}</td>`).join('')}</tr>`).join('')||'<tr><td>No data</td></tr>'}</table></div>`}
const pager=r=>`<div class=pg><button data-p="${r.page-1}" ${r.page<=1?'disabled':''}>‹</button>${r.page}/${r.pages} · ${r.total}<button data-p="${r.page+1}" ${r.page>=r.pages?'disabled':''}>›</button></div>`;
const btn=(a,k,l,c='')=>`<button class="${c}" data-a="${a}" data-k="${esc(k)}">${l}</button>`;
function ask(title,fields,init={}){return new Promise(res=>{const d=$('#dlg');
  d.innerHTML=`<form method=dialog><h3>${esc(title)}</h3>${fields.map(f=>`<label>${esc(f.l)}${f.t==='select'?`<select name=${f.n}>${f.o.map(o=>`<option ${String(init[f.n]??'')===o?'selected':''}>${esc(o)}</option>`).join('')}</select>`:f.t==='textarea'?`<textarea name=${f.n} rows=4 placeholder="${esc(f.p||'')}">${esc(init[f.n]??'')}</textarea>`:`<input name=${f.n} type=${f.t||'text'} step=any value="${esc(init[f.n]??'')}" ${f.ro?'readonly':''}>`}</label>`).join('')}<menu><button value=cancel>Cancel</button><button value=ok class=pri>Save</button></menu></form>`;
  d.returnValue='';d.onclose=()=>{if(d.returnValue!=='ok')return res(null);const o={};new FormData(d.querySelector('form')).forEach((v,k)=>o[k]=v);res(o)};d.showModal()})}
const bar=(items,extra='')=>`<div class=bar>${items}${extra}</div>`;
const val=id=>$('#'+id).value;
const setQ=(o)=>{Object.assign(S.Q,o,{page:1});show()};

const PF=[{n:'sku',l:'SKU'},{n:'name',l:'Name'},{n:'category',l:'Category'},{n:'unit',l:'Unit',t:'select',o:['pcs','box','kg','litre','pack']},{n:'cost_price',l:'Cost price',t:'number'},{n:'selling_price',l:'Selling price',t:'number'},{n:'reorder_point',l:'Reorder point',t:'number'},{n:'supplier_id',l:'Supplier ID (optional)'},{n:'allow_below_cost',l:'Allow price below cost',t:'select',o:['false','true']}];
const SF=[{n:'name',l:'Name'},{n:'contact',l:'Contact'},{n:'phone',l:'Phone'},{n:'email',l:'Email'},{n:'address',l:'Address'}];
const mvCols=[['Time',r=>esc(r.timestamp.slice(0,19).replace('T',' '))],['SKU',r=>esc(r.sku)],['Type',r=>r.type],['Change',r=>(r.qty_change>0?'+':'')+r.qty_change],['Balance',r=>r.balance_after],['User',r=>esc(r.user)],['Reason',r=>esc(r.reason)]];

const views={
async dashboard(){const d=await api('/dashboard');
  return `<div class=cards>${[['Products',d.products],['Categories',d.categories],['Suppliers',d.suppliers],['Stock units',d.stock_units],['Stock value',money(d.stock_value)],['Low stock',d.low_stock_count]].map(([a,b])=>`<div class=card><small>${a}</small><b>${esc(b)}</b></div>`).join('')}</div>
  <h3>Low stock</h3>${table([['SKU',r=>esc(r.sku)],['Name',r=>esc(r.name)],['On hand',r=>`<span class=low>${r.quantity_on_hand}</span>`],['Reorder',r=>r.reorder_point]],d.low_stock)}
  <h3>Purchase orders</h3><p>${Object.entries(d.po_by_status).map(([k,v])=>`${k}: <b>${v}</b>`).join(' · ')}</p>
  <h3>Recent movements</h3>${table(mvCols,d.recent_movements)}`},
async products(){const q=S.Q,staff=can('products.view_cost'),r=await api('/products?'+qs(q));
  const cols=[['SKU',r=>esc(r.sku)],['Name',r=>esc(r.name)],['Category',r=>esc(r.category)],['Unit',r=>esc(r.unit)],
   ...(staff?[['Qty',r=>r.low?`<span class=low>${r.quantity_on_hand} ⚠</span>`:r.quantity_on_hand],['Cost',r=>money(r.cost_price)]]:[['Stock',r=>r.in_stock?'In stock':'Out of stock']]),
   ['Price',r=>money(r.selling_price)],['',r=>(can('stock.card')?btn('card',r.sku,'Card'):'')+(can('products.write')?btn('editP',r.sku,'Edit'):'')+(can('products.delete')?btn('delP',r.sku,'Del','bad'):'')]];
  const sorts=staff?['sku','name','category','quantity_on_hand','selling_price','cost_price']:['sku','name','category','selling_price'];
  return bar(`<input id=f1 placeholder="Search SKU / name" value="${esc(q.search||'')}"><select id=f2><option value="">All categories</option>${r.categories.map(c=>`<option ${q.category===c?'selected':''}>${esc(c)}</option>`).join('')}</select><select id=f3>${sorts.map(s=>`<option ${q.sort===s?'selected':''}>${s}</option>`).join('')}</select><select id=f4><option>asc</option><option ${q.order==='desc'?'selected':''}>desc</option></select>${staff?`<label><input type=checkbox id=f5 ${q.low_only?'checked':''}> low only</label>`:''}<button class=pri id=go>Filter</button>`,can('products.write')?'<button class=pri data-a=newP>+ New product</button>':'')+table(cols,r.items)+pager(r)},
async stock(){const r=await api('/low-stock');
  return bar('<button class=pri data-a=move>Record stock movement</button>')+'<h3>Reorder alerts</h3>'+table([['SKU',x=>esc(x.sku)],['Name',x=>esc(x.name)],['On hand',x=>`<span class=low>${x.quantity_on_hand}</span>`],['Reorder point',x=>x.reorder_point],['Shortfall',x=>x.shortfall]],r.items)},
async suppliers(){const q=S.Q,r=await api('/suppliers?'+qs(q));
  return bar(`<input id=f1 placeholder="Search" value="${esc(q.search||'')}"><button class=pri id=go>Search</button>`,can('suppliers.write')?'<button class=pri data-a=newS>+ New supplier</button>':'')+table([['ID',x=>esc(x.id)],['Name',x=>esc(x.name)],['Contact',x=>esc(x.contact)],['Phone',x=>esc(x.phone)],['Email',x=>esc(x.email)],['',x=>(can('suppliers.write')?btn('editS',x.id,'Edit'):'')+(can('suppliers.delete')?btn('delS',x.id,'Del','bad'):'')]],r.items)+pager(r)},
async pos(){const q=S.Q,r=await api('/purchase-orders?'+qs(q));
  const act=x=>(x.status==='DRAFT'?btn('po_send',x.id,'Send'):'')+(x.status==='SENT'?btn('po_receive',x.id,'Receive'):'')+(['DRAFT','SENT'].includes(x.status)?btn('po_cancel',x.id,'Cancel','bad'):'');
  return bar(`<select id=f1><option value="">All status</option>${['DRAFT','SENT','RECEIVED','CANCELLED'].map(s=>`<option ${q.status===s?'selected':''}>${s}</option>`).join('')}</select><button class=pri id=go>Filter</button>`,'<button class=pri data-a=newPO>+ New PO</button>')+table([['PO',x=>esc(x.id)],['Supplier',x=>esc(x.supplier_name)],['Status',x=>x.status],['Lines',x=>x.lines.length],['Total',x=>money(x.total)],['Created',x=>esc(x.created_at.slice(0,10))],['',act]],r.items)+pager(r)},
async valuation(){const r=await api('/reports/valuation?'+qs(S.Q));
  return `<div class=cards>${[['Cost value',money(r.total_cost_value)],['Retail value',money(r.total_retail_value)],['Potential margin',money(r.potential_margin)]].map(([a,b])=>`<div class=card><small>${a}</small><b>${b}</b></div>`).join('')}</div>`+table([['Category',x=>esc(x[0])],['Units',x=>x[1].units],['Cost value',x=>money(x[1].cost_value)]],Object.entries(r.by_category))+table([['SKU',x=>esc(x.sku)],['Name',x=>esc(x.name)],['Qty',x=>x.quantity_on_hand],['Unit cost',x=>money(x.cost_price)],['Cost value',x=>money(x.cost_value)],['Retail value',x=>money(x.retail_value)]],r.items)+pager(r)},
async audit(){const q=S.Q,r=await api('/audit?'+qs(q));
  return bar(`<input id=f1 placeholder="User" value="${esc(q.user||'')}"><select id=f2><option value="">All entities</option>${['product','supplier','purchase_order','user'].map(s=>`<option ${q.entity===s?'selected':''}>${s}</option>`).join('')}</select><button class=pri id=go>Filter</button>`)+table([['Time',x=>esc(x.timestamp.slice(0,19).replace('T',' '))],['User',x=>esc(x.user)],['Action',x=>esc(x.action)],['Entity',x=>esc(x.entity)],['ID',x=>esc(x.entity_id)]],r.items)+pager(r)},
async warehouses(){const r=await api('/warehouses'); return bar(can('users.manage')?'<button class=pri data-a=newW>+ New warehouse</button>':'')+table([['ID',x=>esc(x.id)],['Name',x=>esc(x.name)],['Location',x=>esc(x.location)]],r.items)},
async lots(){const r=await api('/lots?'+qs(S.Q)); return bar('<select id=f1><option>FEFO</option><option '+(S.Q.method==='FIFO'?'selected':'')+'>FIFO</option></select><button class=pri id=go>Sort</button>',can('stock.move')?'<button class=pri data-a=newL>+ Add lot</button>':'')+table([['SKU',x=>esc(x.sku)],['Warehouse',x=>esc(x.warehouse)],['Lot',x=>esc(x.lot)],['Qty',x=>x.quantity],['Cost',x=>money(x.unit_cost)],['Expiry',x=>esc(x.expiry)]],r.items)},
async counts(){return '<h3>Stock Count</h3><p>ตรวจนับสต็อกและเทียบยอดระบบกับยอดจริง</p>'+bar(can('stock.move')?'<button class=pri data-a=count>Start stock count</button>':'')+'<div id=countout></div>'},
async forecast(){const sku=prompt('SKU for forecast'); if(!sku)return '<p>Enter SKU to view forecast.</p>'; const r=await api('/forecast/'+encodeURIComponent(sku)+'?days=30'); return '<div class=cards><div class=card><small>Daily average</small><b>'+esc(r.daily_average)+'</b></div><div class=card><small>30-day forecast</small><b>'+esc(r.forecast)+'</b></div></div>'},
async users(){const r=await api('/users?'+qs(S.Q));
  return bar('','<button class=pri data-a=newU>+ New user</button>')+table([['Username',x=>esc(x.username)],['Name',x=>esc(x.full_name)],['Role',x=>x.role],['Active',x=>x.active?'yes':'no'],['',x=>btn('editU',x.username,'Edit')]],r.items)+pager(r)}
};
const NAV=[['dashboard','Dashboard','reports.view'],['products','Products','products.view'],['stock','Stock','stock.move'],['suppliers','Suppliers','suppliers.view'],['pos','Purchase Orders','po.view'],['valuation','Valuation','reports.view'],['audit','Audit','audit.view'],['users','Users','users.manage'],['warehouses','Warehouses','products.view'],['lots','Lots / Expiry','stock.card'],['counts','Stock Count','stock.move'],['forecast','Forecast','reports.view']];

const show=guard(async()=>{$('#view').innerHTML=await views[S.page]();
  document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.n===S.page));
  const go=$('#go');if(go)go.onclick=()=>setQ({search:$('#f1')?.value,status:$('#f1')?.value,user:$('#f1')?.value,...( $('#f2')?{category:$('#f2').value,entity:$('#f2').value}:{}),...($('#f3')?{sort:$('#f3').value,order:$('#f4').value,low_only:$('#f5')?.checked?'1':''}:{})});
});
function nav(p){S.page=p;S.Q={};show()}
const crud=guard(async(path,method,body,msg)=>{await api(path,method,body);toast(msg);show()});
const acts={
 newP:async()=>{const v=await ask('New product',PF);if(v)crud('/products','POST',v,'Product created')},
 editP:async k=>{const p=await api('/products/'+k);const v=await ask('Edit '+k,PF.filter(f=>f.n!=='sku'),p);if(v)crud('/products/'+k,'PUT',v,'Product updated')},
 delP:k=>confirm('Delete '+k+'?')&&crud('/products/'+k,'DELETE',null,'Product deleted'),
 card:async k=>{const r=await api(`/products/${k}/card?page=${S.Q.cardPage||1}`);$('#view').innerHTML=bar(`<button data-a=back>← Back</button><b>${esc(r.product.sku)} · ${esc(r.product.name)}</b> · on hand ${r.product.quantity_on_hand}`)+table(mvCols,r.items)+`<small>Page ${r.page}/${r.pages} (${r.total} movements)</small>`},
 back:()=>show(),
 move:async()=>{const v=await ask('Stock movement',[{n:'sku',l:'SKU'},{n:'type',l:'Type',t:'select',o:['INBOUND','OUTBOUND','ADJUSTMENT']},{n:'quantity',l:'Quantity (adjustment may be negative)',t:'number'},{n:'reason',l:'Reason (required)'},{n:'reference',l:'Reference (optional)'},{n:'unit_cost',l:'Unit cost (inbound, optional)',t:'number'}]);if(v)crud('/stock','POST',v,'Movement recorded')},
 newS:async()=>{const v=await ask('New supplier',SF);if(v)crud('/suppliers','POST',v,'Supplier created')},
 editS:async k=>{const d=await api('/suppliers?search='+encodeURIComponent(k));const s=d.items.find(x=>x.id===k)||{};const v=await ask('Edit supplier',SF,s);if(v)crud('/suppliers/'+k,'PUT',v,'Supplier updated')},
 delS:k=>confirm('Delete supplier '+k+'?')&&crud('/suppliers/'+k,'DELETE',null,'Supplier deleted'),
 newPO:async()=>{const v=await ask('New purchase order',[{n:'supplier_id',l:'Supplier ID (e.g. SUP-0001)'},{n:'lines',l:'Lines: SKU,qty,unit_cost per line',t:'textarea',p:'DEMO-001,10,45.50'}]);if(!v)return;
   const lines=v.lines.split('\n').map(l=>l.trim()).filter(Boolean).map(l=>{const [sku,qty,unit_cost]=l.split(',').map(s=>s.trim());return{sku,qty,unit_cost}});crud('/purchase-orders','POST',{supplier_id:v.supplier_id,lines},'PO created')},
 po_send:k=>crud(`/purchase-orders/${k}/send`,'POST',null,'PO sent'),
 po_receive:k=>confirm('Receive all lines into stock?')&&crud(`/purchase-orders/${k}/receive`,'POST',null,'PO received - stock updated'),
 po_cancel:k=>confirm('Cancel '+k+'?')&&crud(`/purchase-orders/${k}/cancel`,'POST',null,'PO cancelled'),
 newW:async()=>{const v=await ask('New warehouse',[{n:'id',l:'ID'},{n:'name',l:'Name'},{n:'location',l:'Location'}]);if(v)crud('/warehouses','POST',v,'Warehouse created')},
newL:async()=>{const v=await ask('Add lot',[{n:'sku',l:'SKU'},{n:'warehouse',l:'Warehouse ID'},{n:'lot',l:'Lot number'},{n:'quantity',l:'Quantity',t:'number'},{n:'unit_cost',l:'Unit cost',t:'number'},{n:'expiry',l:'Expiry YYYY-MM-DD'}]);if(v)crud('/lots','POST',v,'Lot created')},
count:async()=>{const v=await ask('Stock count',[{n:'warehouse',l:'Warehouse ID'},{n:'items',l:'Items: SKU,counted per line',t:'textarea',p:'SKU001,10'}]);if(v){const items=v.items.split('\n').filter(Boolean).map(x=>{const [sku,counted]=x.split(',').map(s=>s.trim());return{sku,counted}});crud('/stock-count','POST',{warehouse:v.warehouse,items},'Stock count saved')}},
newU:async()=>{const v=await ask('New user',[{n:'username',l:'Username'},{n:'full_name',l:'Full name'},{n:'role',l:'Role',t:'select',o:['staff','customer','admin']},{n:'password',l:'Password (8+, letters+digits)',t:'password'}]);if(v)crud('/users','POST',v,'User created')},
 editU:async k=>{const v=await ask('Edit '+k,[{n:'role',l:'Role',t:'select',o:['staff','customer','admin']},{n:'active',l:'Active',t:'select',o:['true','false']},{n:'password',l:'New password (blank = keep)',t:'password'}]);if(!v)return;if(!v.password)delete v.password;crud('/users/'+k,'PUT',v,'User updated')}
};
document.addEventListener('click',e=>{const a=e.target.closest('[data-a]');if(a&&acts[a.dataset.a])return guard(acts[a.dataset.a])(a.dataset.k);
  const p=e.target.closest('[data-p]');if(p&&!p.disabled){S.Q.page=p.dataset.p;show()}
  const n=e.target.closest('#nav button');if(n)nav(n.dataset.n)});

function logout(){S.token='';S.me=null;sessionStorage.removeItem('t');$('#app').hidden=true;$('#login').hidden=false}
async function enter(){S.me=await api('/me');$('#register').hidden=true;$('#login').hidden=true;$('#app').hidden=false;$('#who').textContent=`${S.me.user.username} (${S.me.user.role})`;
  const items=NAV.filter(n=>can(n[2]));$('#nav').innerHTML=items.map(n=>`<button data-n="${n[0]}">${n[1]}</button>`).join('');nav(items[0][0])}
$('#login').onsubmit=guard(async e=>{e.preventDefault();const r=await api('/login','POST',{username:val('lu'),password:val('lp')});S.token=r.token;sessionStorage.setItem('t',r.token);$('#lp').value='';await enter()});
$('#out').onclick=logout;\n$('#showreg').onclick=()=>{$('#login').hidden=true;$('#register').hidden=false};\n$('#backlogin').onclick=()=>{$('#register').hidden=true;$('#login').hidden=false};\n$('#register').onsubmit=guard(async e=>{e.preventDefault();if(val('rp')!==val('rc'))throw new Error('Passwords do not match');const r=await api('/register','POST',{username:val('ru'),full_name:val('rn'),password:val('rp')});S.token=r.token;sessionStorage.setItem('t',S.token);await enter()});
$('#pw').onclick=guard(async()=>{const v=await ask('Change password',[{n:'old_password',l:'Current password',t:'password'},{n:'new_password',l:'New password',t:'password'}]);if(v){await api('/password','POST',v);toast('Password changed')}});
if(S.token)guard(enter)().then(()=>{if(!S.me)logout()});
</script>
</body>
</html>
'''
