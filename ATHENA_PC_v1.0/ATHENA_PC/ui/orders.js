import {h,num,won,icon,request,empty} from './shared.js';

const statuses={pending:'대기',confirmed:'확인',completed:'완료',cancelled:'취소'};
const notice='주문 저장·상태 변경은 재고·매출·입금·미수금에 영향을 주지 않습니다.';
const tag=value=>`<span class="tag ${value==='pending'?'amber':value==='confirmed'||value==='completed'?'green':'neutral'}">${h(statuses[value])}</span>`;
const options=value=>Object.entries(statuses).map(([key,label])=>`<option value="${key}" ${key===value?'selected':''}>${label}</option>`).join('');
const filter={q:'',status:'',page:1};
let serial=0;

export async function renderOrders(main,isCurrent){
 const renderId=++serial;
 main.innerHTML=`<section class="page-head"><div><div class="eyebrow">ATHENA / ORDERS</div><h1>주문 대기함</h1><p>접수한 주문을 등록하고 진행 상태를 관리하세요.</p></div><button class="btn primary" data-form="order">${icon('plus',18)}주문 등록</button></section>
 <div class="info-box">${notice} 완료는 주문 관리 상태이며, 실제 판매는 판매·입금에서 별도로 등록하세요.</div>
 <section class="panel"><div class="toolbar"><div class="search">${icon('search',18)}<input id="order-search" type="search" maxlength="120" value="${h(filter.q)}" placeholder="주문번호 · 거래처 · 품목 · 메모 검색" aria-label="주문 검색"></div><select id="order-status-filter" aria-label="주문 상태 필터"><option value="">전체 상태</option>${options(filter.status)}</select></div><div id="order-list" aria-live="polite"></div></section>`;
 const holder=main.querySelector('#order-list');
 const select=main.querySelector('#order-status-filter');select.value=filter.status;
 let requestId=0,timer;
 async function draw(){
  const current=++requestId;
  holder.innerHTML='<div class="loading">주문을 불러오는 중입니다…</div>';
  try{
   const {orders}=await request('/api/orders?'+new URLSearchParams({q:filter.q,status:filter.status}));
   if(!isCurrent()||serial!==renderId||requestId!==current)return;
   const pages=Math.max(1,Math.ceil(orders.length/25));filter.page=Math.min(filter.page,pages);
   const visible=orders.slice((filter.page-1)*25,filter.page*25);
   holder.innerHTML=`<div class="list-summary"><span>주문 ${num(orders.length)}건</span><span>조회된 주문금액 ${won(orders.reduce((sum,o)=>sum+o.total,0))}</span></div>`+(orders.length?`<div class="table-wrap"><table><thead><tr><th>접수일 / 주문번호</th><th>거래처 / 품목</th><th class="right">주문금액</th><th>상태</th><th>작업</th></tr></thead><tbody>${visible.map(o=>`<tr><td>${h(o.day)}<span class="subtext">${h(o.number)}</span></td><td class="primary-text">${h(o.partner_name)}<span class="subtext break">${h(o.items)} · ${num(o.line_count)}종</span></td><td class="right">${num(o.total)}</td><td>${tag(o.status)}</td><td><div class="actions"><button class="btn small" data-form="order-detail" data-id="${o.id}" aria-label="${h(o.number)} 상세">상세</button><button class="text-button" data-form="order" data-id="${o.id}" aria-label="${h(o.number)} 수정">수정</button><button class="text-button" data-form="order-status" data-id="${o.id}" aria-label="${h(o.number)} 상태 변경">상태 변경</button><button class="text-button negative" data-form="order-delete" data-id="${o.id}" aria-label="${h(o.number)} 삭제">삭제</button></div></td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${filter.page} / ${pages} 페이지 · ${num(orders.length)}건</span><button class="btn small" data-order-page="-1" ${filter.page<=1?'disabled':''}>이전</button><button class="btn small" data-order-page="1" ${filter.page>=pages?'disabled':''}>다음</button></div>`:empty('조회된 주문이 없습니다.','주문을 등록하거나 검색 조건을 바꿔 주세요.','<button class="btn primary" data-form="order">주문 등록</button>'));
  }catch(error){if(isCurrent()&&serial===renderId&&requestId===current)holder.innerHTML=empty('주문을 불러오지 못했습니다.',error.message,'<button class="btn" data-order-retry>다시 불러오기</button>');}
 }
 main.querySelector('#order-search').addEventListener('input',e=>{filter.q=e.target.value;filter.page=1;++requestId;clearTimeout(timer);timer=setTimeout(()=>{if(isCurrent()&&serial===renderId)draw();},250);});
 select.addEventListener('change',e=>{filter.status=e.target.value;filter.page=1;clearTimeout(timer);draw();});
 holder.addEventListener('click',e=>{const page=e.target.closest('[data-order-page]');if(page&&!page.disabled){filter.page+=Number(page.dataset.orderPage);draw();}if(e.target.closest('[data-order-retry]'))draw();});
 await draw();
}

export async function openOrderForm(name,id,{state,show,content}){
 const order=id?await request(`/api/order/${id}`):null;
 if(name==='order-detail'){
  show('주문 상세',`${order.number} · ${order.day}`,`<div class="detail-strip"><div><label>거래처</label><b>${h(order.partner_name)}</b></div><div><label>상태</label>${tag(order.status)}</div><div><label>주문 합계</label><b>${won(order.total)}</b></div></div><div class="actions"><button class="btn" data-detail-action="order" data-id="${id}">주문 수정</button><button class="btn" data-detail-action="order-status" data-id="${id}">상태 변경</button><button class="btn danger" data-detail-action="order-delete" data-id="${id}">삭제</button></div><div class="detail-table"><table><thead><tr><th>품목 / 규격</th><th class="right">수량</th><th class="right">단가</th><th class="right">금액</th></tr></thead><tbody>${order.lines.map(l=>`<tr><td>${h(l.product_name)}<span class="subtext">${h(l.spec)}</span></td><td class="right">${num(l.qty)} ${h(l.unit)}</td><td class="right">${num(l.price)}</td><td class="right">${num(l.qty*l.price)}</td></tr>`).join('')}</tbody></table></div><p class="detail-note">${h(order.note||'메모 없음')}</p><p class="muted">마지막 변경: ${h(order.updated_at.slice(0,19).replace('T',' '))}</p><div class="info-box">${notice}</div>`,{wide:true});return;
 }
 if(name==='order-status'){
  show('주문 상태 변경',`${order.number} · ${order.partner_name}`,`<div class="field"><label for="order-new-status">상태</label><select id="order-new-status" name="status">${options(order.status)}</select></div><div class="info-box">대기: 접수 후 확인 전 · 확인: 주문 내용 확인 · 완료: 주문 관리 종료 · 취소: 접수 취소.<br>잘못 변경한 상태는 다시 선택할 수 있습니다. 완료로 바꿔도 판매가 등록되거나 재고가 차감되지 않습니다.</div>`,{submit:'상태 저장',action:'order-status',notice,build:v=>({id,status:v.status})});return;
 }
 if(name==='order-delete'){
  show('주문 삭제',`${order.number} · ${order.partner_name}`,`<div class="info-box amber">이 주문을 휴지통으로 이동합니다. 휴지통에서 복구할 수 있습니다. ${notice}</div>`,{submit:'휴지통으로 이동',action:'delete',notice,build:()=>({entity:'order',id})});return;
 }
 const partners=new Map(state().partners.filter(p=>!p.archived).map(p=>[p.id,p.name]));
 const products=new Map(state().products.filter(p=>!p.archived).map(p=>[p.id,{...p,product_name:p.name}]));
 if(order){partners.set(order.partner_id,order.partner_name);for(const l of order.lines)products.set(l.product_id,{...l,id:l.product_id});}
 if(!partners.size||!products.size)throw Error('주문을 등록하려면 거래처와 품목을 먼저 등록해 주세요.');
 const partnerOptions=[...partners].map(([key,label])=>`<option value="${key}" ${key===order?.partner_id?'selected':''}>${h(label)} · #${key}</option>`).join('');
 const productOptions=[...products].map(([key,p])=>`<option value="${key}">${h(p.product_name)}${p.spec?' / '+h(p.spec):''} · #${key}</option>`).join('');
 show(order?'주문 수정':'주문 등록',order?`${order.number} · ${statuses[order.status]}`:'새 주문은 대기 상태로 등록됩니다.',`<div class="form-grid"><div class="field"><label for="order-partner">거래처 *</label><select id="order-partner" name="partner_id" required><option value="">거래처 선택</option>${partnerOptions}</select></div><div class="field"><label for="order-day">접수일 *</label><input id="order-day" name="day" type="date" required min="2000-01-01" max="${state().today}" value="${h(order?.day||state().today)}"></div></div><h3 class="section-label">주문 품목</h3><div class="line-grid line-head"><span>품목 / 규격</span><span>수량</span><span>단가 (원)</span><span class="right">금액</span><span></span></div><div id="order-lines"></div><button class="text-button" type="button" id="order-add-line">${icon('plus',16)}품목 추가</button><div class="sale-totals"><div><label>주문 합계</label><strong id="order-total">0원</strong></div></div><div class="field"><label for="order-note">주문 메모</label><textarea id="order-note" name="note" maxlength="1000">${h(order?.note||'')}</textarea></div><div class="info-box">${notice} 재고가 부족해도 주문을 접수할 수 있습니다.</div>`,{wide:true,submit:order?'수정 저장':'주문 저장',action:'orders',notice,build:v=>({...v,...(order?{id}:{}),lines:[...content.querySelectorAll('.order-line')].map(row=>({product_id:Number(row.querySelector('[data-product]').value),qty:Number(row.querySelector('[data-qty]').value),price:Number(row.querySelector('[data-price]').value)}))})});
 const holder=content.querySelector('#order-lines');let next=0;
 function recalc(){let total=0;for(const row of holder.children){const amount=Number(row.querySelector('[data-qty]').value||0)*Number(row.querySelector('[data-price]').value||0);row.querySelector('.line-amount').textContent=num(amount);total+=amount;}content.querySelector('#order-total').textContent=won(total);}
 function addLine(source={}){
  if(holder.children.length>=100)return;
  const n=++next,row=document.createElement('div');row.className='order-line sale-line';
  row.innerHTML=`<div class="line-grid"><select data-product aria-label="주문 품목 ${n}" required><option value="">품목 선택</option>${productOptions}</select><input type="number" data-qty aria-label="주문 수량 ${n}" required min="1" max="1000000" step="1" value="${source.qty??1}"><input type="number" data-price aria-label="주문 단가 ${n}" required min="0" max="1000000000" step="1" value="${source.price??0}"><span class="line-amount right">0</span><button type="button" class="remove-line" aria-label="주문 품목 ${n} 삭제">삭제</button></div>`;
  holder.append(row);row.querySelector('[data-product]').value=String(source.product_id||'');
  row.querySelector('[data-product]').addEventListener('change',e=>{const p=products.get(Number(e.target.value));if(p)row.querySelector('[data-price]').value=p.price;recalc();});
  row.querySelector('.remove-line').addEventListener('click',()=>{if(holder.children.length>1){row.remove();recalc();}});row.addEventListener('input',recalc);recalc();
 }
 (order?.lines||[{}]).forEach(addLine);content.querySelector('#order-add-line').addEventListener('click',()=>addLine());
}
