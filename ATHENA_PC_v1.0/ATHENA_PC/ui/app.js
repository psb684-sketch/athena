import {h,num,won,shortDay,icon,status,request,empty} from './shared.js';
import {initForms,openForm} from './forms.js';
import {renderOrders} from './orders.js';

let data, view='home', toastTimer, renderSerial=0, filtersInitialized=false;
const main=document.getElementById('main');
const filters={sales:{q:'',from:'',to:'',status:'',page:1},inventory:{q:'',status:'active',page:1},partners:{q:'',status:'active',page:1}};
const formButton=(name,label,id=null,cls='btn primary',i='plus')=>`<button class="${cls}" data-form="${name}" ${id!=null?`data-id="${id}"`:''}>${icon(i,18)}${label}</button>`;
const head=(title,description,actions,eyebrow='ATHENA / WORKSPACE')=>`<section class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div><div class="actions">${actions}</div></section>`;
const searchBox=placeholder=>`<div class="search">${icon('search',18)}<input id="list-search" type="search" placeholder="${placeholder}" aria-label="${placeholder}" autocomplete="off" value="${h(filters[view]?.q||'')}"></div>`;
const saleTable=(sales,compact=false)=>`<div class="table-wrap"><table><thead><tr><th>날짜</th><th>거래처${compact?'':' / 거래번호'}</th><th class="right">${compact?'거래금액':'현재 거래금액'}</th>${compact?'':'<th class="right">순입금액</th>'}<th class="right">미수금</th><th>상태</th></tr></thead><tbody>${sales.map(s=>`<tr class="click-row" data-form="sale-detail" data-id="${s.id}" tabindex="0" role="button" aria-label="${h(s.partner_name)} ${h(s.day)} 판매 상세"><td class="muted">${compact?shortDay(s.day):h(s.day)}</td><td class="primary-text">${h(s.partner_name)}${compact?'':`<span class="subtext">${h(s.number)}</span>`}</td><td class="right primary-text">${num(s.net)}</td>${compact?'':`<td class="right">${num(s.paid)}</td>`}<td class="right ${s.balance?'money-accent':'muted'}">${s.balance?num(s.balance):'—'}</td><td>${status(s)}</td></tr>`).join('')}</tbody></table></div>`;

function toast(message,error=false){const el=document.getElementById('toast');el.textContent=message;el.classList.toggle('error',error);el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,error?7500:3500);}

async function refresh(){
 const result=await request('/api/state');data=result;
 document.getElementById('business').textContent=data.settings.business;
 document.getElementById('demo-banner').hidden=!data.demo;
 document.getElementById('mode').innerHTML=data.demo?'<i></i>체험 장부':'<i></i>내 PC에 저장';
 document.getElementById('warning').textContent=data.backup_warning;
 document.getElementById('warning').hidden=!data.backup_warning;
 if(!filtersInitialized){filters.sales.from=data.today.slice(0,7)+'-01';filters.sales.to=data.today;filtersInitialized=true;}
 await render();
}

async function navigate(target){
 if(!['home','orders','sales','inventory','partners','trash','settings'].includes(target))target='home';
 view=target;history.replaceState(null,'',`#${target}`);await render();window.scrollTo({top:0});
}

async function render(){
 if(!data)return;
 renderSerial++;
 document.querySelectorAll('.nav [data-nav]').forEach(btn=>{btn.classList.toggle('active',btn.dataset.nav===view);btn.setAttribute('aria-current',btn.dataset.nav===view?'page':'false');});
 if(view==='home')renderHome();
 else if(view==='inventory')renderInventory();
 else if(view==='partners')renderPartners();
 else if(view==='orders')await renderOrders(main,()=>view==='orders');
 else if(view==='sales')await renderSales();
 else if(view==='trash')renderTrash();
 else renderSettings();
}

function renderHome(){
 const s=data.summary;const activeProducts=data.products.filter(p=>!p.archived);const activePartners=data.partners.filter(p=>!p.archived);const lows=activeProducts.filter(p=>p.stock<=p.minimum).sort((a,b)=>a.stock-b.stock).slice(0,3);
 const dateText=new Date(data.today+'T12:00:00').toLocaleDateString('ko-KR',{year:'numeric',month:'long',day:'numeric',weekday:'long'});
 const metric=(label,value,sub,i,unit='원')=>`<div class="metric"><div class="metric-top"><span>${label}</span>${icon(i,19)}</div><div class="metric-value">${num(value)}<small>${unit}</small></div><div class="metric-sub">${sub}</div></div>`;
 const max=Math.max(1,...data.week.map(d=>Math.abs(d.sales)));
 const weekTotal=data.week.reduce((a,b)=>a+b.sales,0);
 main.innerHTML=head('한눈에 보는 오늘',dateText,formButton('sale','판매 등록'),'YOUR DAILY LEDGER')+
 `${!activeProducts.length||!activePartners.length?`<section class="welcome"><span class="welcome-icon">${icon('box',26)}</span><div><h2>아테나에 첫 장부를 펼쳐 보세요.</h2><p>품목과 거래처를 등록하면 바로 판매를 기록할 수 있습니다.</p></div><div class="actions">${formButton('product',activeProducts.length?'품목 추가':'1. 품목 등록',null,'btn','box')}${formButton('partner',activePartners.length?'거래처 추가':'2. 거래처 등록',null,'btn primary','people')}</div></section>`:''}`+
 `<section class="metrics" aria-label="주요 현황">${metric('오늘 순판매',s.today_sales,`판매 ${s.today_count}건 · 오늘 반품 차감`,'receipt')}${metric('오늘 순입금',s.today_cash,'입금에서 환불·정정을 뺀 금액','wallet')}${metric('전체 미수금',s.receivable,`받을 금액이 있는 거래처 ${data.partners.filter(p=>p.balance>0).length}곳`,'clock')}${metric('이번 달 순판매',s.month_sales,`${Number(data.today.slice(5,7))}월 1일부터 오늘까지`,'box')}</section>`+
 `<div class="dashboard-grid"><div class="stack"><section class="panel"><div class="panel-head"><div><h2>최근 판매 기록</h2><p>거래를 누르면 입금·반품·명세서를 확인합니다.</p></div><button class="text-button" data-nav="sales">전체 보기 ${icon('arrow',14)}</button></div>${data.recent_sales.length?saleTable(data.recent_sales,true):empty('첫 판매를 기록해 보세요.','저장하면 재고가 줄고 미수금이 함께 계산됩니다.',formButton('sale','판매 등록'))}<div class="panel-note">금액 단위: 원 · 반품을 반영한 현재 거래금액입니다.</div></section>
 <section class="panel"><div class="panel-head"><div><h2>최근 7일의 판매</h2><p>반품을 차감한 날짜별 순판매 · 음수는 붉은 막대</p></div><strong class="money-accent">${won(weekTotal)}</strong></div><div class="panel-body"><div class="chart" role="img" aria-label="${h(data.week.map(d=>d.day+' '+won(d.sales)).join(', '))}">${data.week.map((d,i)=>`<div class="bar-column"><span class="bar-value">${num(d.sales)}</span><div class="bar-track"><div class="bar ${i===6?'today':''} ${d.sales<0?'negative':''}" style="height:${Math.abs(d.sales)/max*100}%" title="${d.day}: ${won(d.sales)}"></div></div><small>${i===6?'오늘':shortDay(d.day)}</small></div>`).join('')}</div></div></section></div>
 <div class="stack"><section class="panel"><div class="panel-head"><h2>바로 기록하기</h2></div><div class="panel-body quick-grid"><button class="quick" data-form="receive"><span>${icon('box')}</span><span><b>재고 입고</b><small>들어온 상품을 장부에 추가</small></span>${icon('arrow')}</button><button class="quick" data-form="payment"><span>${icon('wallet')}</span><span><b>입금 기록</b><small>받은 금액을 미수금에 반영</small></span>${icon('arrow')}</button><button class="quick" data-form="partner"><span>${icon('people')}</span><span><b>새 거래처</b><small>다음 거래부터 간편하게 선택</small></span>${icon('arrow')}</button></div></section>
 <section class="panel"><div class="panel-head"><h2>재고 확인</h2><button class="text-button" data-nav="inventory">${icon('arrow',16)}</button></div><div class="panel-body"><div class="alerts">${lows.length?lows.map(p=>`<div class="alert-row"><span class="alert-swatch">${icon('box',18)}</span><div><b>${h(p.name)}</b><small>${h(p.spec||p.sku)}</small></div><strong>${num(p.stock)}<small>${h(p.unit)} 남음</small></strong></div>`).join(''):`<div class="alert-row"><span class="alert-swatch">${icon('check',18)}</span><div><b>${activeProducts.length?'재고가 충분합니다.':'품목 등록을 기다립니다.'}</b><small>${activeProducts.length?'설정한 부족 기준을 모두 넘었습니다.':'기준 수량 이하일 때 알려드립니다.'}</small></div></div>`}</div></div><div class="panel-note">관리 품목 ${activeProducts.length}개 · 부족 품목 ${s.low_count}개</div></section>
 <section class="panel"><div class="panel-head"><h2>안전하게 보관 중</h2>${icon('shield',19)}</div><div class="panel-body"><p class="muted" style="font-size:12px;margin:0 0 12px">저장한 자료는 PC에 남고,<br>최근 30개 날짜의 자동 백업을 보관합니다.</p><button class="text-button" data-nav="settings">백업 확인 ${icon('arrow',14)}</button></div></section></div></div>`;
}

function pagination(total){const f=filters[view];const pages=Math.max(1,Math.ceil(total/25));f.page=Math.min(f.page,pages);return `<div class="pagination"><span>${f.page} / ${pages} 페이지 · ${num(total)}건</span><button class="btn small" data-page="-1" ${f.page<=1?'disabled':''}>이전</button><button class="btn small" data-page="1" ${f.page>=pages?'disabled':''}>다음</button></div>`;}
function pageSlice(items){const f=filters[view];f.page=Math.max(1,Math.min(f.page,Math.ceil(items.length/25)||1));return items.slice((f.page-1)*25,f.page*25);}

function renderInventory(){
 const f=filters.inventory;
 main.innerHTML=head('재고','현재 수량과 입출고 이력을 한곳에서 확인하세요.',`${formButton('receive','입고 등록',null,'btn','box')}${formButton('product','품목 등록')}`)+`<section class="panel"><div class="toolbar">${searchBox('품목명 · 규격 · 코드 검색')}<select id="list-status" aria-label="품목 표시"><option value="active">사용 중인 품목</option><option value="low">재고 부족</option><option value="archived">보관된 품목</option></select><div class="grow actions">${formButton('movements','입출고 이력',null,'btn small','clock')}<a class="btn small" href="/api/export/products">${icon('download',15)}전체 CSV</a></div></div><div id="list-content"></div></section>`;
 document.getElementById('list-status').value=f.status;bindFilters(drawInventory);drawInventory();
}

function drawInventory(){
 const f=filters.inventory,q=f.q.toLocaleLowerCase();const items=data.products.filter(p=>`${p.name} ${p.sku} ${p.spec}`.toLocaleLowerCase().includes(q)&&(f.status==='archived'?p.archived:!p.archived&&(f.status!=='low'||p.stock<=p.minimum)));
 const visible=pageSlice(items);
 document.getElementById('list-content').innerHTML=`<div class="list-summary"><span>품목 ${num(items.length)}개</span><span>수량을 바꾸면 입출고 이력에 남습니다.</span></div>${items.length?`<div class="table-wrap"><table><thead><tr><th>품목 / 코드</th><th>규격</th><th class="right">현재고</th><th class="right">기본 단가</th><th>상태</th><th class="right">작업</th></tr></thead><tbody>${visible.map(p=>`<tr><td class="primary-text">${h(p.name)}<span class="subtext">${h(p.sku)}</span></td><td class="muted">${h(p.spec||'—')}</td><td class="right primary-text">${num(p.stock)} <small class="muted">${h(p.unit)}</small></td><td class="right">${num(p.price)}</td><td>${p.archived?'<span class="tag neutral">보관</span>':p.stock<=p.minimum?'<span class="tag amber">재고 부족</span>':'<span class="tag green">정상</span>'}</td><td class="right"><div class="actions" style="justify-content:flex-end">${!p.archived?`<button class="btn small" data-form="receive" data-id="${p.id}">입고</button><button class="btn small" data-form="adjust" data-id="${p.id}">조정</button>`:''}<button class="text-button" data-form="movements" data-id="${p.id}">이력</button><button class="icon-button" data-form="product" data-id="${p.id}" aria-label="${h(p.name+' '+p.spec)} 수정">${icon('edit',15)}</button></div></td></tr>`).join('')}</tbody></table></div>${pagination(items.length)}`:empty('표시할 품목이 없습니다.','품목을 등록하거나 검색 조건을 바꿔 주세요.',formButton('product','품목 등록'))}`;
}

function renderPartners(){
 const f=filters.partners;
 main.innerHTML=head('거래처','거래처별 판매와 받을 금액을 확인하세요.',formButton('partner','거래처 등록'))+`<section class="panel"><div class="toolbar">${searchBox('거래처 · 담당자 · 연락처 검색')}<select id="list-status" aria-label="거래처 표시"><option value="active">거래 중</option><option value="unpaid">미수금 있는 거래처</option><option value="archived">보관된 거래처</option></select><a class="btn small grow" href="/api/export/partners">${icon('download',15)}전체 CSV</a></div><div id="list-content"></div></section>`;
 document.getElementById('list-status').value=f.status;bindFilters(drawPartners);drawPartners();
}

function drawPartners(){
 const f=filters.partners,q=f.q.toLocaleLowerCase();const items=data.partners.filter(p=>`${p.name} ${p.phone} ${p.contact}`.toLocaleLowerCase().includes(q)&&(f.status==='archived'?p.archived:!p.archived&&(f.status!=='unpaid'||p.balance>0)));
 const visible=pageSlice(items);
 document.getElementById('list-content').innerHTML=`<div class="list-summary"><span>거래처 ${num(items.length)}곳</span><span>조회된 미수금 <b>${won(items.reduce((sum,p)=>sum+p.balance,0))}</b></span></div>${items.length?`<div class="table-wrap"><table><thead><tr><th>거래처</th><th>담당자 / 연락처</th><th>최근 판매</th><th class="right">누적 순판매</th><th class="right">미수금</th><th></th></tr></thead><tbody>${visible.map(p=>`<tr class="click-row" data-form="partner-detail" data-id="${p.id}" role="button" tabindex="0" aria-label="${h(p.name)} 거래 원장"><td class="primary-text">${h(p.name)}${p.archived?' <span class="tag neutral">보관</span>':''}<span class="subtext">#${String(p.id).padStart(3,'0')}</span></td><td>${h(p.contact||'—')}<span class="subtext">${h(p.phone||'연락처 미등록')}</span></td><td class="muted">${h(p.last_day||'—')}</td><td class="right">${num(p.volume)}</td><td class="right ${p.balance?'money-accent':'muted'}">${p.balance?num(p.balance):'—'}</td><td class="right">${p.balance?`<button class="btn small subtle" data-form="payment" data-id="${p.id}">입금</button>`:icon('arrow',15)}</td></tr>`).join('')}</tbody></table></div>${pagination(items.length)}`:empty('표시할 거래처가 없습니다.','거래처를 등록하거나 검색 조건을 바꿔 주세요.',formButton('partner','거래처 등록'))}`;
}

async function renderSales(){
 const f=filters.sales;
 main.innerHTML=head('판매·입금','거래 내역을 누르면 입금 기록, 반품 처리, 명세서 인쇄가 가능합니다.',`${formButton('payment','입금 기록',null,'btn','wallet')}${formButton('sale','판매 등록')}`)+`<section class="panel"><div class="toolbar">${searchBox('거래처 · 거래번호 검색')}<div class="field-inline"><input id="filter-from" type="date" value="${f.from}" aria-label="조회 시작일"><span>~</span><input id="filter-to" type="date" value="${f.to}" aria-label="조회 종료일"></div><select id="list-status" aria-label="입금 상태"><option value="">전체 상태</option><option value="unpaid">미수금 있음</option></select><div class="actions grow"><button class="btn small" id="all-dates">전체 기간</button><a class="btn small" id="sales-export">${icon('download',15)}CSV</a></div></div><div id="list-content"><div class="loading">기록을 불러오는 중입니다…</div></div></section>`;
 document.getElementById('list-status').value=f.status;bindFilters(drawSales,true);
 for(const [id,key]of [['filter-from','from'],['filter-to','to']])document.getElementById(id).addEventListener('change',async e=>{f[key]=e.target.value;f.page=1;await drawSales();});
 document.getElementById('all-dates').addEventListener('click',async()=>{f.from='';f.to='';document.getElementById('filter-from').value='';document.getElementById('filter-to').value='';f.page=1;await drawSales();});
 await drawSales();
}

let listRequest=0;
async function drawSales(){
 const f=filters.sales;const serial=++listRequest;const currentRender=renderSerial;
 const query=new URLSearchParams({q:f.q,from:f.from,to:f.to,status:f.status});
 const exportLink=document.getElementById('sales-export');if(exportLink)exportLink.href='/api/export/sales?'+query;
 if(f.from&&f.to&&f.from>f.to){document.getElementById('list-content').innerHTML=empty('조회 날짜를 확인해 주세요.','시작일이 종료일보다 늦습니다.');return;}
 try{const response=await request('/api/sales?'+query);if(view!=='sales'||serial!==listRequest||currentRender!==renderSerial)return;const items=response.sales;const visible=pageSlice(items);
 document.getElementById('list-content').innerHTML=`<div class="list-summary"><span>거래 ${num(items.length)}건 · 시작 미수금 포함</span><span>조회된 미수금 <b>${won(items.reduce((sum,s)=>sum+s.balance,0))}</b></span></div>${items.length?saleTable(visible)+pagination(items.length):empty('조회된 거래가 없습니다.','기간을 바꾸거나 첫 판매를 등록해 주세요.',formButton('sale','판매 등록'))}<div class="panel-note">판매일로 조회하며, 반품·입금은 현재까지의 누적 금액입니다. 기간 매출은 ‘오늘의 장부’에서 확인하세요.</div>`;
 }catch(error){if(view==='sales'&&serial===listRequest){document.getElementById('list-content').innerHTML=empty('기록을 불러오지 못했습니다.',error.message);toast(error.message,true);}}
}

function bindFilters(draw,debounce=false){
 let timer;
 document.getElementById('list-search').addEventListener('input',e=>{filters[view].q=e.target.value;filters[view].page=1;clearTimeout(timer);if(debounce){const target=view;timer=setTimeout(()=>{if(view===target)draw();},250);}else draw();});
 document.getElementById('list-status').addEventListener('change',e=>{filters[view].status=e.target.value;filters[view].page=1;draw();});
}

function renderTrash(){
 const labels={product:'품목',partner:'거래처',sale:'판매',payment:'입금',return:'반품',movement:'입출고 기록',order:'주문'};
 main.innerHTML=head('휴지통','삭제한 기록을 복구하거나 복구할 수 없게 영구 삭제합니다.','', 'ATHENA / RECOVERY')+
 `<section class="panel"><div class="panel-head"><div><h2>삭제된 기록</h2><p>복구하면 재고·입금·미수금도 삭제 전 상태로 돌아갑니다.</p></div><span class="tag neutral">${num(data.trash.length)}건</span></div>${data.trash.length?`<div class="table-wrap"><table><thead><tr><th>삭제 시각</th><th>종류</th><th>기록</th><th>영향</th><th class="right">작업</th></tr></thead><tbody>${data.trash.map(item=>`<tr><td class="muted">${h(item.deleted_at.slice(0,19).replace('T',' '))}</td><td><span class="tag neutral">${h(labels[item.entity]||item.entity)}</span></td><td class="primary-text">${h(item.label)}</td><td class="muted break">${h(Object.entries(item.impact).map(([k,v])=>`${k} ${typeof v==='number'?num(v):v}`).join(' · '))}</td><td class="right"><div class="actions" style="justify-content:flex-end"><button class="btn small" data-form="trash-restore" data-id="${item.id}">복구</button><button class="btn small danger" data-form="trash-purge" data-id="${item.id}">영구 삭제</button></div></td></tr>`).join('')}</tbody></table></div>`:empty('휴지통이 비어 있습니다.','삭제한 기록은 이곳에서 복구할 수 있습니다.') }<div class="panel-note">영구 삭제 후에는 화면에서 복구할 수 없습니다. 삭제·복구 이력은 장부 안전을 위해 작업 기록에 남습니다.</div></section>`;
}

function renderSettings(){
 const s=data.settings;
 main.innerHTML=head('설정 및 백업','사업장 정보와 장부 보관 상태를 확인하세요.','')+`<div class="settings-grid"><div class="stack"><section class="panel"><div class="panel-head"><h2>사업장 정보</h2>${formButton('business','수정',null,'btn small','edit')}</div><div class="panel-body"><dl class="definition"><dt>사업장명</dt><dd>${h(s.business)}</dd><dt>대표 / 담당자</dt><dd>${h(s.owner||'미등록')}</dd><dt>전화</dt><dd>${h(s.phone||'미등록')}</dd><dt>주소</dt><dd>${h(s.address||'미등록')}</dd></dl><div class="info-box">여기에 입력한 정보가 거래명세서에 표시됩니다.</div></div></section><section class="panel"><div class="panel-head"><h2>아테나 PC</h2><span class="tag green">${h(data.version)}</span></div><div class="panel-body"><p style="font-size:13px">이 PC에서 인터넷 없이 실행되는 장부입니다. 화면을 닫아도 저장된 기록은 남습니다.</p><div class="info-box">품목·재고 · 거래처 · 판매·입금 · 부분 반품·환불 · 미수 원장 · 거래명세서 · CSV · 백업·복원</div><p class="muted" style="font-size:12px">저장 폴더</p><p class="path">${h(data.data_directory)}</p><p class="muted" style="font-size:11px">장부 전체를 종료하려면 실행 창에서 Ctrl+C를 누르세요.</p></div></section></div><div class="stack"><section class="panel"><div class="panel-head"><h2>장부 백업</h2>${icon('shield',20)}</div><div class="panel-body"><p class="muted" style="font-size:12px">저장할 때마다 자동 백업을 갱신하고, 최근 30개 날짜의 자료를 보관합니다.</p><a href="/api/backup" class="btn primary">${icon('download')}현재 장부 백업 내려받기</a><div class="info-box">PC 고장에도 대비하려면 내려받은 백업 파일을 USB 등 다른 저장장치에 보관하세요.</div><h3 class="section-label">보관 중인 백업</h3>${data.backups.slice(0,8).map(name=>`<div class="backup-item"><span>${h(name.startsWith('before-schema')?'업데이트 전 장부':name.startsWith('before-restore')?'복원 전 장부':name.startsWith('athena-auto')?'자동 백업 '+name.slice(12,-3):'수동 백업')}</span><a href="/api/backup-file?name=${encodeURIComponent(name)}">내려받기</a></div>`).join('')||'<p class="muted">아직 백업이 없습니다.</p>'}<div class="restore-zone"><h3 class="section-label" style="margin-top:0">백업에서 복원</h3><p class="muted" style="font-size:12px">이전 장부로 되돌리거나 다른 PC로 자료를 옮길 때 사용하세요.</p>${formButton('restore','백업 파일 선택',null,'btn','clock')}</div></div></section></div></div><section class="panel" style="margin-top:22px"><div class="panel-head"><h2>최근 작업 기록</h2><span class="muted" style="font-size:11px">최대 100건 표시</span></div>${data.audit.length?`<div class="table-wrap"><table class="compact"><thead><tr><th>시각</th><th>작업</th><th>내용</th></tr></thead><tbody>${data.audit.map(a=>`<tr><td>${h(a.created_at.slice(0,19).replace('T',' '))}</td><td>${h(a.action)}</td><td class="break">${h(a.note)}</td></tr>`).join('')}</tbody></table></div>`:empty('아직 작업 기록이 없습니다.','등록·수정·입출고·정산 내역이 여기에 남습니다.')}</section>`;
}

document.addEventListener('click',async e=>{
 const nav=e.target.closest('[data-nav]');if(nav){e.preventDefault();await navigate(nav.dataset.nav);return;}
 const form=e.target.closest('[data-form]');if(form&&!form.closest('dialog')){try{await openForm(form.dataset.form,form.dataset.id?Number(form.dataset.id):null);}catch(error){toast(error.message,true);}return;}
 const pager=e.target.closest('[data-page]');if(pager&&!pager.disabled){filters[view].page+=Number(pager.dataset.page);if(view==='inventory')drawInventory();else if(view==='partners')drawPartners();else await drawSales();}
});
main.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('tr[role=button]')){e.preventDefault();e.target.click();}});
document.getElementById('refresh').addEventListener('click',async()=>{try{await refresh();toast('최신 기록을 불러왔습니다.');}catch(error){toast(error.message,true);}});
window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
initForms({getState:()=>data,refresh,toast});
view=['home','orders','sales','inventory','partners','trash','settings'].includes(location.hash.slice(1))?location.hash.slice(1):'home';
refresh().catch(error=>{main.innerHTML=empty('아테나를 열지 못했습니다.',error.message,'<button class="btn primary" id="reload">다시 연결</button>');document.getElementById('reload').addEventListener('click',()=>location.reload());});
