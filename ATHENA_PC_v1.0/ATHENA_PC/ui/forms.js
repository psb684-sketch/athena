import {h,num,won,icon,status,request,methods,kinds,empty} from './shared.js';

let env, dialog, content, formRevision, requestKey;
const state=()=>env.getState();
const today=()=>state().today;
const productName=p=>`${p.sku} · ${p.name}${p.spec?' / '+p.spec:''}`;
const partnerName=p=>`${p.name} · #${String(p.id).padStart(3,'0')}`;
const productOptions=()=>state().products.filter(p=>!p.archived).map(p=>`<option value="${h(productName(p))}"></option>`).join('');
const partnerOptions=()=>state().partners.filter(p=>!p.archived).map(p=>`<option value="${h(partnerName(p))}"></option>`).join('');
const findProduct=v=>state().products.find(p=>productName(p)===v&&!p.archived);
const findPartner=v=>state().partners.find(p=>partnerName(p)===v&&!p.archived);
const field=(label,name,value='',type='text',extra='')=>`<div class="field"><label for="f-${h(name)}">${h(label)}</label><input id="f-${h(name)}" name="${h(name)}" type="${type}" value="${h(value)}" ${extra}></div>`;
const dates=(value=today(),name='day',label='기록 날짜')=>field(label,name,value,'date',`required min="2000-01-01" max="${today()}"`);
const notes=(label='메모',name='note',value='',required=false)=>`<div class="field full"><label for="f-${name}">${label}</label><textarea id="f-${name}" name="${name}" maxlength="${required?300:1000}" ${required?'required':''} placeholder="${required?'사유를 입력해 주세요.':'필요한 내용만 남겨 주세요.'}">${h(value)}</textarea></div>`;
const methodField=(value='transfer')=>`<div class="field"><label for="f-method">결제 수단</label><select id="f-method" name="method">${Object.entries(methods).map(([k,v])=>`<option value="${k}" ${k===value?'selected':''}>${v}</option>`).join('')}</select></div>`;
const footer=label=>`<div class="dialog-footer"><span class="left">저장하면 장부에 바로 반영됩니다.</span><button class="btn" type="button" data-close>닫기</button><button class="btn primary" type="submit">${label}</button></div>`;

export function initForms(context){
 env=context; dialog=document.getElementById('dialog'); content=document.getElementById('dialog-content');
 content.addEventListener('click',async e=>{
  if(e.target.closest('[data-close]')){if(!content.querySelector('button[type=submit]:disabled'))dialog.close();return;}
  const btn=e.target.closest('[data-detail-action]');if(!btn)return;
  const {detailAction:action,id,partnerId}=btn.dataset;
  try {
   if(action==='print'){window.open(`/statement.html?id=${Number(id)}`,'_blank','noopener');return;}
   if(action==='payment'){payment(Number(partnerId),Number(id)||null);return;}
   if(action==='return'){await returnForm(Number(id));return;}
   if(action==='edit-partner'){partnerForm(Number(id));return;}
   if(action==='correction'){await correctionForm(Number(id),Number(btn.dataset.saleId));return;}
   if(action==='sale'){await saleDetail(Number(id));return;}
   if(action==='archive'){archiveForm(btn.dataset.table,Number(id),Number(btn.dataset.archived));return;}
   if(action==='delete'){deleteForm(btn.dataset.entity,Number(id),btn.dataset.label||'선택한 기록');return;}
   if(action==='edit-sale'){await saleEditForm(Number(id));return;}
   if(action==='edit-payment'){await paymentEditForm(Number(id),Number(btn.dataset.saleId));return;}
   if(action==='edit-return'){await returnEditForm(Number(id));return;}
   if(action==='edit-movement'){await movementEditForm(Number(id));return;}
  } catch(error){env.toast(error.message,true);}
 });
 dialog.addEventListener('cancel',e=>{if(content.querySelector('button[type=submit]:disabled'))e.preventDefault();});
}

function show(title,description,body,{wide=false,submit=null,action=null,build=null}={}){
 formRevision=state().revision; requestKey=crypto.randomUUID();
 dialog.classList.toggle('wide',wide);
 content.innerHTML=`<div class="dialog-head"><div><h2>${h(title)}</h2><p>${h(description)}</p></div><button type="button" class="icon-button" data-close aria-label="창 닫기">${icon('close')}</button></div>${submit?'<form id="active-form">':''}<div class="dialog-body"><div class="form-error" role="alert"></div>${body}</div>${submit?footer(submit)+'</form>':''}`;
 if(!dialog.open)dialog.showModal();dialog.scrollTop=0;
 if(submit)content.querySelector('form').addEventListener('submit',async e=>{
  e.preventDefault();const form=e.currentTarget;const button=form.querySelector('button[type=submit]');if(button.disabled)return;
  const errorBox=content.querySelector('.form-error');errorBox.textContent='';
  try{
   const values=Object.fromEntries(new FormData(form));
   const data=build?build(values,form):values;
   button.disabled=true;button.textContent='저장 중…';
   await request(`/api/${action}`,{method:'POST',headers:{'Content-Type':'application/json','X-Athena-CSRF':state().csrf},
    body:JSON.stringify({...data,revision:formRevision,request_key:requestKey})});
   dialog.close();await env.refresh();env.toast('장부에 저장했습니다.');
  }catch(error){errorBox.textContent=error.message;errorBox.scrollIntoView({block:'nearest'});button.disabled=false;button.textContent=submit;}
 });
}

export async function openForm(name,id=null){
 if(name==='sale')return saleForm();
 if(name==='product')return productForm(id);
 if(name==='partner')return partnerForm(id);
 if(name==='receive')return stockForm('receive',id);
 if(name==='adjust')return stockForm('adjust',id);
 if(name==='payment')return payment(id);
 if(name==='sale-detail')return saleDetail(id);
 if(name==='partner-detail')return partnerDetail(id);
 if(name==='movements')return movementDetail(id);
 if(name==='business')return businessForm();
 if(name==='restore')return restoreForm();
 if(name==='trash-restore')return trashAction(id,false);
 if(name==='trash-purge')return trashAction(id,true);
}

function productForm(id){
 const p=state().products.find(x=>x.id===id)||{};
 const body=`<div class="form-grid">${field('품목명 *','name',p.name||'','text','required maxlength="120" placeholder="예: 기능성 풋베드"')}${field('규격','spec',p.spec||'','text','maxlength="100" placeholder="예: M · 250–265"')}${field('품목 코드','sku',p.sku||'','text','maxlength="40" placeholder="비우면 자동 생성"')}${field('단위 *','unit',p.unit||'개','text','required maxlength="12" placeholder="개 / 켤레 / 박스"')}${field('기본 판매 단가 (원)','price',p.price||0,'number','required min="0" max="1000000000" step="1"')}${field('부족 알림 수량','minimum',p.minimum||0,'number','required min="0" max="1000000" step="1"')}${!id?field('시작 재고','opening_stock',0,'number','required min="0" max="1000000" step="1"'):''}</div>${id?`<div class="info-box">현재 재고 <b>${num(p.stock)}${h(p.unit)}</b> · 수량은 입고 또는 재고 조정에서 변경합니다.</div><div class="actions"><button type="button" class="text-button" data-detail-action="archive" data-table="products" data-id="${id}" data-archived="${p.archived?0:1}">${p.archived?'보관 해제':'사용하지 않는 품목으로 보관'}</button><button type="button" class="text-button negative" data-detail-action="delete" data-entity="product" data-id="${id}" data-label="${h(p.name)}">품목 삭제</button></div>`:'<div class="info-box">현재 보유한 수량을 시작 재고로 입력하세요. 이후 판매·입고·반품에 따라 자동으로 계산됩니다.</div>'}`;
 show(id?'품목 수정':'새 품목 등록','품목은 한 번 등록하고, 거래할 때 선택하세요.',body,{submit:id?'수정 저장':'품목 등록',action:'products',build:v=>({...v,id})});
}

function partnerForm(id){
 const p=state().partners.find(x=>x.id===id)||{};
  show(id?'거래처 수정':'새 거래처 등록','거래처별 판매와 미수금을 한 장부에 모읍니다.',`<div class="form-grid">${field('거래처명 *','name',p.name||'','text','required maxlength="120"')}${field('담당자','contact',p.contact||'','text','maxlength="60"')}${field('연락처','phone',p.phone||'','tel','maxlength="40"')}${field('주소','address',p.address||'','text','maxlength="200"')}${!id?field('기존에 받을 미수금 (원)','opening_balance',0,'number','required min="0" max="1000000000000" step="1"')+dates(today(),'opening_day','기존 미수금 기준일'):''}${notes('거래처 메모','note',p.note||'')}</div>${!id?'<div class="info-box">기존 미수금은 도입 전 장부 잔액입니다. 매출에는 포함되지 않으며, 등록 뒤 입금을 기록해 정산할 수 있습니다.</div>':`<div class="info-box">현재 받을 금액 <b>${won(p.balance)}</b></div><div class="actions"><button class="text-button" type="button" data-detail-action="archive" data-table="partners" data-id="${id}" data-archived="${p.archived?0:1}">${p.archived?'보관 해제':'거래가 끝난 거래처로 보관'}</button><button type="button" class="text-button negative" data-detail-action="delete" data-entity="partner" data-id="${id}" data-label="${h(p.name)}">거래처 삭제</button></div>`}`,{submit:id?'수정 저장':'거래처 등록',action:'partners',build:v=>({...v,id})});
}

function stockForm(kind,id){
 const p=state().products.find(x=>x.id===id&&!x.archived);
 show(kind==='receive'?'재고 입고':'재고 수량 조정',kind==='receive'?'들어온 수량을 입력하면 현재고에 더해집니다.':'실제로 센 수량으로 맞추고 조정 사유를 남깁니다.',`<datalist id="products-list">${productOptions()}</datalist><div class="form-grid"><div class="field full"><label for="f-product">품목 *</label><input id="f-product" name="product" list="products-list" required autocomplete="off" value="${h(p?productName(p):'')}" placeholder="품목명 또는 코드를 입력해 선택"><small id="stock-current">${p?`현재 재고 ${num(p.stock)}${h(p.unit)}`:'등록한 품목을 선택해 주세요.'}</small></div>${dates()}${kind==='receive'?field('입고 수량 *','qty',1,'number','required min="1" max="1000000" step="1"'):field('실제로 센 재고 *','counted',p?.stock??0,'number','required min="0" max="1000000" step="1"')}${notes(kind==='receive'?'입고 메모':'조정 사유 *','note','',kind==='adjust')}</div>`,{submit:kind==='receive'?'입고 저장':'재고 조정 저장',action:'stock',build:v=>{
  const product=findProduct(v.product);if(!product)throw Error('목록에서 품목을 선택해 주세요.');return {...v,product_id:product.id,kind};
 }});
 content.querySelector('#f-product').addEventListener('change',e=>{const p=findProduct(e.target.value);content.querySelector('#stock-current').textContent=p?`현재 재고 ${num(p.stock)}${p.unit}`:'목록에서 품목을 선택해 주세요.';if(p&&kind==='adjust')content.querySelector('#f-counted').value=p.stock;});
}

function saleForm(){
 if(!state().partners.some(p=>!p.archived)){env.toast('먼저 거래처를 등록해 주세요.');return partnerForm();}
 if(!state().products.some(p=>!p.archived)){env.toast('먼저 품목을 등록해 주세요.');return productForm();}
 let next=0;
 show('판매 등록','거래처와 품목을 선택하면 재고·입금·미수금이 함께 기록됩니다.',`<datalist id="products-list">${productOptions()}</datalist><datalist id="partners-list">${partnerOptions()}</datalist><div class="form-grid"><div class="field"><label for="f-partner">거래처 *</label><input id="f-partner" name="partner" list="partners-list" required autocomplete="off" placeholder="거래처명을 입력해 선택"></div>${dates(today(),'day','판매 날짜')}</div><div class="section-label">판매 품목</div><div class="line-grid line-head"><span>품목 / 규격</span><span>수량</span><span>단가 (원)</span><span class="right">금액</span><span></span></div><div id="sale-lines"></div><button class="text-button" type="button" id="add-line">${icon('plus',16)}품목 추가</button><div class="sale-totals"><div><label>판매 합계</label><strong id="sale-total">0원</strong></div><div><label>이번 입금</label><strong id="sale-paid">0원</strong></div><div><label>남은 미수금</label><strong id="sale-balance">0원</strong></div></div><div class="form-grid"><div class="field"><label for="f-paid">이번에 받은 금액 (원)</label><input id="f-paid" name="paid" type="number" min="0" max="1000000000000" step="1" value="0" required><button class="text-button" id="pay-full" type="button">전액 받음 ${icon('check',14)}</button></div>${methodField()}${notes()}</div>`,{wide:true,submit:'판매 저장',action:'sales',build:v=>{
  const partner=findPartner(v.partner);if(!partner)throw Error('목록에서 거래처를 선택해 주세요.');
  const lines=[...content.querySelectorAll('.sale-line')].map(row=>{const product=findProduct(row.querySelector('[data-product]').value);if(!product)throw Error('각 줄의 품목을 목록에서 선택해 주세요.');return {product_id:product.id,qty:Number(row.querySelector('[data-qty]').value),price:Number(row.querySelector('[data-price]').value)};});
  return {...v,partner_id:partner.id,lines};
 }});
 const lines=content.querySelector('#sale-lines');
 function total(){return [...lines.children].reduce((sum,row)=>sum+Number(row.querySelector('[data-qty]').value||0)*Number(row.querySelector('[data-price]').value||0),0);}
 function recalc(){for(const row of lines.children)row.querySelector('.line-amount').textContent=num(Number(row.querySelector('[data-qty]').value)*Number(row.querySelector('[data-price]').value));const amount=total(),paid=Number(content.querySelector('#f-paid').value||0);content.querySelector('#sale-total').textContent=won(amount);content.querySelector('#sale-paid').textContent=won(paid);content.querySelector('#sale-balance').textContent=won(amount-paid);content.querySelector('#sale-balance').classList.toggle('negative',paid>amount);}
 function add(){const n=++next;const row=document.createElement('div');row.className='sale-line';row.innerHTML=`<div class="line-grid"><input list="products-list" data-product aria-label="품목 ${n}" required autocomplete="off" placeholder="품목명 검색"><input type="number" data-qty aria-label="수량 ${n}" required min="1" max="1000000" step="1" value="1"><input type="number" data-price aria-label="단가 ${n}" required min="0" max="1000000000" step="1" value="0"><span class="line-amount right">0</span><button type="button" class="remove-line" aria-label="품목 ${n} 삭제">삭제</button></div><div class="line-hint"></div>`;lines.append(row);row.querySelector('[data-product]').addEventListener('change',e=>{const p=findProduct(e.target.value);if(p){row.querySelector('[data-price]').value=p.price;row.querySelector('.line-hint').textContent=`재고 ${num(p.stock)}${p.unit}`;row.querySelector('[data-qty]').focus();row.querySelector('[data-qty]').select();}else{row.querySelector('.line-hint').textContent='목록에서 품목을 선택해 주세요.';}recalc();});row.querySelector('.remove-line').addEventListener('click',()=>{if(lines.children.length===1){env.toast('품목은 한 줄 이상 필요합니다.');return;}row.remove();recalc();});row.addEventListener('input',recalc);}
 add();content.querySelector('#add-line').addEventListener('click',()=>{add();lines.lastElementChild.querySelector('input').focus();});content.querySelector('#f-paid').addEventListener('input',recalc);content.querySelector('#pay-full').addEventListener('click',()=>{content.querySelector('#f-paid').value=total();recalc();});
}

function payment(partnerId=null,saleId=null){
 const p=state().partners.find(x=>x.id===partnerId);
 show('입금 기록',saleId?'선택한 거래의 미수금에 입금합니다.':'거래처의 오래된 미수금부터 자동으로 정산합니다.',`<datalist id="partners-list">${partnerOptions()}</datalist><div class="form-grid"><div class="field full"><label for="f-partner">거래처 *</label><input id="f-partner" name="partner" list="partners-list" value="${h(p?partnerName(p):'')}" required autocomplete="off" ${saleId?'readonly':''} placeholder="거래처 검색"><small id="payment-balance">${p?`거래처 전체 미수금 ${won(p.balance)}`:'거래처를 선택해 주세요.'}</small></div>${dates(today(),'day','입금 날짜')}${field('실제로 받은 금액 (원) *','amount','','number','required min="1" max="1000000000000" step="1" placeholder="입금액 입력"')}${methodField()}${notes('입금 메모')}</div><div class="info-box">${saleId?'이 거래 한 건에만 반영합니다.':'선택한 입금일 이전 거래부터 정산합니다.'} 미수금을 초과하는 금액은 저장하지 않습니다.</div>`,{submit:'입금 저장',action:'payments',build:v=>{const p=findPartner(v.partner);if(!p)throw Error('목록에서 거래처를 선택해 주세요.');return {...v,partner_id:p.id,sale_id:saleId};}});
 content.querySelector('#f-partner').addEventListener('change',e=>{const p=findPartner(e.target.value);content.querySelector('#payment-balance').textContent=p?`거래처 전체 미수금 ${won(p.balance)}`:'목록에서 거래처를 선택해 주세요.';});
 if(saleId)request(`/api/sale/${saleId}`).then(s=>{if(content.querySelector('#payment-balance'))content.querySelector('#payment-balance').textContent=`이 거래에서 받을 금액 ${won(s.balance)}`;}).catch(e=>env.toast(e.message,true));
}

async function saleDetail(id){
 const s=await request(`/api/sale/${id}`);
 const paymentRows=s.payments.map(p=>`<tr><td>${h(p.day)}</td><td>${h(methods[p.method])}<span class="subtext break">${h(p.note)}</span></td><td class="right ${p.amount<0?'negative':''}">${p.amount>0?'+':''}${won(p.amount)}</td><td><div class="actions">${p.amount>0&&!s.payments.some(q=>q.note.startsWith(`[입금정정 #${p.id}]`))?`<button class="text-button" data-detail-action="edit-payment" data-id="${p.id}" data-sale-id="${id}">수정</button><button class="text-button" data-detail-action="correction" data-id="${p.id}" data-sale-id="${id}">정정</button><button class="text-button negative" data-detail-action="delete" data-entity="payment" data-id="${p.id}" data-label="${h(p.day+' 입금 '+won(p.amount))}">삭제</button>`:''}</div></td></tr>`).join('');
 const returnRows=s.returns.map(r=>`<tr><td>${h(r.day)}</td><td class="break">${h(r.note)}</td><td class="right">${won(r.total)}</td><td><div class="actions"><button class="text-button" data-detail-action="edit-return" data-id="${r.id}">수정</button><button class="text-button negative" data-detail-action="delete" data-entity="return" data-id="${r.id}" data-label="${h(r.day+' 반품 '+won(r.total))}">삭제</button></div></td></tr>`).join('');
 const body=`<div class="detail-strip"><div><label>거래 당시 거래처</label><b>${h(s.partner_name)}</b></div><div><label>현재 거래금액</label><b>${won(s.net)}</b></div><div><label>순입금액</label><b>${won(s.paid)}</b></div><div><label>받을 금액</label><b class="money-accent">${won(s.balance)}</b></div></div><div class="actions">${s.balance>0?`<button class="btn primary" data-detail-action="payment" data-id="${id}" data-partner-id="${s.partner_id}">${icon('wallet')}입금 기록</button>`:''}${s.kind==='sale'?`<button class="btn" data-detail-action="print" data-id="${id}">${icon('print')}거래명세서</button>${s.lines.some(l=>l.qty>l.returned_qty)?`<button class="btn" data-detail-action="return" data-id="${id}">${icon('return')}반품 기록</button>`:''}`:''}<button class="btn danger" data-detail-action="delete" data-entity="sale" data-id="${id}" data-label="${h(s.number)}">거래 전체 삭제</button>${status(s)}</div>${s.lines.length?`<h3 class="section-label">판매 품목</h3><div class="detail-table"><table class="compact"><thead><tr><th>품목 / 규격</th><th class="right">판매</th><th class="right">반품</th><th class="right">단가</th><th class="right">잔여 금액</th></tr></thead><tbody>${s.lines.map(l=>`<tr><td>${h(l.product_name)}<small class="subtext">${h(l.spec)}</small></td><td class="right">${num(l.qty)}</td><td class="right">${num(l.returned_qty)}</td><td class="right">${num(l.price)}</td><td class="right">${num((l.qty-l.returned_qty)*l.price)}</td></tr>`).join('')}</tbody></table></div>`:''}${s.note?`<p class="detail-note">${h(s.note)}</p>`:''}<h3 class="section-label">입금·환불 기록</h3>${s.payments.length?`<div class="detail-table"><table class="compact"><thead><tr><th>날짜</th><th>수단 / 메모</th><th class="right">입금 증감</th><th></th></tr></thead><tbody>${paymentRows}</tbody></table></div>`:'<p class="muted">아직 입금 기록이 없습니다.</p>'}${s.returns.length?`<h3 class="section-label">반품 기록</h3><div class="detail-table"><table class="compact"><tbody>${returnRows}</tbody></table></div>`:''}<div class="info-box">삭제하면 연결된 재고·입금·반품도 함께 원상 복구되며, 휴지통에서 다시 되살릴 수 있습니다.</div>`;
 const editableBody=body.replace('<div class="actions">',`<div class="actions"><button class="btn" data-detail-action="edit-sale" data-id="${id}">${icon('edit')}거래 수정</button>`);
 show(s.kind==='opening'?'시작 미수금':'판매 상세',`${s.number} · ${s.day}`,editableBody,{wide:true});
}

async function returnForm(id){
 const s=await request(`/api/sale/${id}`);const lines=s.lines.filter(l=>l.qty>l.returned_qty);
 show('반품 기록',`${s.partner_name} · ${s.number}`,`<div class="form-grid">${dates(today(),'day','반품 날짜')}${methodField()}</div><h3 class="section-label">반품할 수량만 입력해 주세요.</h3><div class="detail-table"><table class="compact"><thead><tr><th>품목 / 규격</th><th class="right">남은 수량</th><th>반품 수량</th></tr></thead><tbody>${lines.map(l=>`<tr><td>${h(l.product_name)}<span class="subtext">${h(l.spec)} · ${won(l.price)}</span></td><td class="right">${num(l.qty-l.returned_qty)}</td><td><input style="width:95px" type="number" name="return-${l.id}" aria-label="${h(l.product_name+' '+l.spec)} 반품 수량" min="0" max="${l.qty-l.returned_qty}" step="1" value="0" required data-return></td></tr>`).join('')}</tbody></table></div><div class="sale-totals"><div><label>반품 금액</label><strong id="return-total">0원</strong></div><div><label>돌려줄 금액</label><strong id="refund-total">0원</strong></div><div><label>반품 후 미수금</label><strong id="return-balance">${won(s.balance)}</strong></div></div><div id="refund-check" class="info-box amber" hidden><label class="check-line"><input type="checkbox" name="refund_confirmed">표시된 금액을 실제로 환불했습니다.</label></div><div class="form-grid">${notes('반품 사유 *','note','',true)}</div><div class="info-box">반품한 상품은 재판매 가능한 재고로 돌아옵니다. 파손품은 반품 처리 후 재고 조정에서 수량과 사유를 기록하세요.</div>`,{submit:'반품 저장',action:'returns',build:v=>{const selected=lines.map(l=>({sale_line_id:l.id,qty:Number(v[`return-${l.id}`]||0)})).filter(l=>l.qty>0);if(!selected.length)throw Error('반품 수량을 한 개 이상 입력해 주세요.');return {sale_id:id,day:v.day,method:v.method,note:v.note,lines:selected,refund_confirmed:v.refund_confirmed==='on'};}});
 content.querySelectorAll('[data-return]').forEach(input=>input.addEventListener('input',()=>{const total=lines.reduce((sum,l)=>sum+Number(content.querySelector(`[name="return-${l.id}"]`).value||0)*l.price,0);const refund=Math.max(0,s.paid-(s.net-total));content.querySelector('#return-total').textContent=won(total);content.querySelector('#refund-total').textContent=won(refund);content.querySelector('#return-balance').textContent=won(Math.max(0,s.balance-total));content.querySelector('#refund-check').hidden=!refund;content.querySelector('[name=refund_confirmed]').required=refund>0;}));
}

async function correctionForm(id,saleId){
 const sale=await request(`/api/sale/${saleId}`);const p=sale.payments.find(p=>p.id===id);
 show('잘못 기록한 입금 정정',`${sale.number} · ${won(p.amount)}`,`<div class="info-box amber">이 입금액 전체를 취소하는 정정 기록을 남깁니다. 기존 기록은 보존되며, 미수금이 ${won(p.amount)} 늘어납니다. 실제 상품 반품·환불은 ‘반품 기록’을 사용하세요.</div><div class="form-grid">${dates(today(),'day','정정 날짜')}${notes('정정 사유 *','note','',true)}</div>`,{submit:'입금 정정 저장',action:'payment-correction',build:v=>({...v,id})});
}

async function saleEditForm(id){
 const s=await request(`/api/sale/${id}`);const partner=state().partners.find(p=>p.id===s.partner_id);
 if(s.kind==='opening'){
  show('시작 미수금 수정',s.number,`<datalist id="partners-list">${partnerOptions()}</datalist><div class="form-grid"><div class="field full"><label for="f-partner">거래처 *</label><input id="f-partner" name="partner" list="partners-list" value="${h(partner?partnerName(partner):'')}" required></div>${dates(s.day,'day','기준 날짜')}${field('시작 미수금 (원) *','total',s.total,'number','required min="1" max="1000000000000" step="1"')}${notes('메모','note',s.note||'')}</div><div class="info-box">이미 기록된 입금액보다 작게 줄일 수 없습니다. 수정 전 값은 이력에 보존됩니다.</div>`,{submit:'수정 저장',action:'sale-edit',build:v=>{const p=findPartner(v.partner);if(!p)throw Error('목록에서 거래처를 선택해 주세요.');return {...v,id,partner_id:p.id};}});return;
 }
 let next=0;
 show('판매 수정',`${s.number} · 수정 전 값은 이력에 보존됩니다.`,`<datalist id="products-list">${productOptions()}</datalist><datalist id="partners-list">${partnerOptions()}</datalist><div class="form-grid"><div class="field"><label for="f-partner">거래처 *</label><input id="f-partner" name="partner" list="partners-list" required value="${h(partner?partnerName(partner):'')}"></div>${dates(s.day,'day','판매 날짜')}</div><div class="section-label">판매 품목</div><div class="line-grid line-head"><span>품목 / 규격</span><span>수량</span><span>단가 (원)</span><span class="right">금액</span><span></span></div><div id="sale-lines"></div><button class="text-button" type="button" id="add-line">${icon('plus',16)}품목 추가</button><div class="sale-totals"><div><label>수정 판매 합계</label><strong id="sale-total">0원</strong></div><div><label>현재 순입금</label><strong>${won(s.paid)}</strong></div><div><label>예상 미수금</label><strong id="sale-balance">0원</strong></div></div><div class="form-grid">${notes('메모','note',s.note||'')}</div>${s.returns.length?'<div class="info-box amber">반품이 연결되어 있습니다. 품목·수량 수정은 반품을 먼저 휴지통으로 옮긴 뒤 가능합니다.</div>':'<div class="info-box">수량을 바꾸면 재고도 차이만큼 자동 조정됩니다.</div>'}`,{wide:true,submit:'판매 수정 저장',action:'sale-edit',build:v=>{const p=findPartner(v.partner);if(!p)throw Error('목록에서 거래처를 선택해 주세요.');const saleLines=[...content.querySelectorAll('.sale-line')].map(row=>{const product=findProduct(row.querySelector('[data-product]').value);if(!product)throw Error('각 줄의 품목을 목록에서 선택해 주세요.');return {product_id:product.id,qty:Number(row.querySelector('[data-qty]').value),price:Number(row.querySelector('[data-price]').value)};});return {...v,id,partner_id:p.id,lines:saleLines};}});
 const holder=content.querySelector('#sale-lines');
 function recalc(){let total=0;for(const row of holder.children){const amount=Number(row.querySelector('[data-qty]').value||0)*Number(row.querySelector('[data-price]').value||0);row.querySelector('.line-amount').textContent=num(amount);total+=amount;}content.querySelector('#sale-total').textContent=won(total);content.querySelector('#sale-balance').textContent=won(total-s.paid);}
 function addLine(source={}){const n=++next,p=state().products.find(x=>x.id===source.product_id);const row=document.createElement('div');row.className='sale-line';row.innerHTML=`<div class="line-grid"><input list="products-list" data-product aria-label="품목 ${n}" required value="${h(p?productName(p):'')}"><input type="number" data-qty required min="1" max="1000000" step="1" value="${source.qty||1}"><input type="number" data-price required min="0" max="1000000000" step="1" value="${source.price??0}"><span class="line-amount right">0</span><button type="button" class="remove-line">삭제</button></div><div class="line-hint">${p?`재고 ${num(p.stock)}${h(p.unit)}`:''}</div>`;holder.append(row);row.querySelector('[data-product]').addEventListener('change',e=>{const selected=findProduct(e.target.value);if(selected){row.querySelector('[data-price]').value=selected.price;row.querySelector('.line-hint').textContent=`재고 ${num(selected.stock)}${selected.unit}`;}recalc();});row.querySelector('.remove-line').addEventListener('click',()=>{if(holder.children.length===1){env.toast('품목은 한 줄 이상 필요합니다.');return;}row.remove();recalc();});row.addEventListener('input',recalc);}
 s.lines.forEach(addLine);content.querySelector('#add-line').addEventListener('click',()=>addLine());recalc();
}

async function paymentEditForm(id,saleId){
 const sale=await request(`/api/sale/${saleId}`);const p=sale.payments.find(x=>x.id===id);if(!p)throw Error('입금 기록을 찾을 수 없습니다.');
 show('입금 수정',`${sale.number} · 수정 전 값은 이력에 보존됩니다.`,`<div class="form-grid">${dates(p.day,'day','입금 날짜')}${field('입금액 (원) *','amount',p.amount,'number','required min="1" max="1000000000000" step="1"')}${methodField(p.method)}${notes('입금 메모','note',p.note||'')}</div><div class="info-box">수정 후 판매금액을 초과하거나 미수금이 음수가 되면 저장되지 않습니다.</div>`,{submit:'입금 수정 저장',action:'payment-edit',build:v=>({...v,id})});
}

async function returnEditForm(id){
 const r=await request(`/api/return/${id}`),s=r.sale;const paidWithoutRefund=s.paid-(r.refund?.amount||0);
 show('반품 수정',`${s.number} · 수정 전 값은 이력에 보존됩니다.`,`<div class="form-grid">${dates(r.day,'day','반품 날짜')}${methodField(r.refund?.method||'transfer')}</div><h3 class="section-label">수정할 반품 수량</h3><div class="detail-table"><table class="compact"><thead><tr><th>품목</th><th class="right">수정 가능</th><th>반품 수량</th></tr></thead><tbody>${r.lines.map(l=>`<tr><td>${h(l.product_name)}<span class="subtext">${h(l.spec)} · ${won(l.price)}</span></td><td class="right">${num(l.qty-l.other_returned)}</td><td><input style="width:95px" type="number" name="return-${l.id}" min="0" max="${l.qty-l.other_returned}" step="1" value="${l.current_qty}" data-return></td></tr>`).join('')}</tbody></table></div><div class="sale-totals"><div><label>수정 반품금액</label><strong id="return-total">${won(r.total)}</strong></div><div><label>수정 후 환불액</label><strong id="refund-total">${won(Math.abs(r.refund?.amount||0))}</strong></div><div><label>수정 후 미수금</label><strong id="return-balance">${won(s.balance)}</strong></div></div><div id="refund-check" class="info-box amber"><label class="check-line"><input type="checkbox" name="refund_confirmed">수정 후 표시된 실제 환불 금액을 확인했습니다.</label></div><div class="form-grid">${notes('반품 사유 *','note',r.note,true)}</div>`,{wide:true,submit:'반품 수정 저장',action:'return-edit',build:v=>{const lines=r.lines.map(l=>({sale_line_id:l.id,qty:Number(v[`return-${l.id}`]||0)})).filter(l=>l.qty>0);if(!lines.length)throw Error('반품 수량을 한 개 이상 입력해 주세요. 전체 취소는 삭제를 사용하세요.');return {id,day:v.day,method:v.method,note:v.note,lines,refund_confirmed:v.refund_confirmed==='on'};}});
 function recalc(){const total=r.lines.reduce((sum,l)=>sum+Number(content.querySelector(`[name="return-${l.id}"]`).value||0)*l.price,0);const net=s.net+r.total-total;const refund=Math.max(0,paidWithoutRefund-net);content.querySelector('#return-total').textContent=won(total);content.querySelector('#refund-total').textContent=won(refund);content.querySelector('#return-balance').textContent=won(net-(paidWithoutRefund-refund));content.querySelector('#refund-check').hidden=!refund;content.querySelector('[name=refund_confirmed]').required=refund>0;}
 content.querySelectorAll('[data-return]').forEach(input=>input.addEventListener('input',recalc));recalc();
}

async function movementEditForm(id){
 const m=await request(`/api/movement/${id}`);if(!['opening','receive','adjust'].includes(m.kind))throw Error('판매·반품 입출고는 해당 거래에서 수정해 주세요.');
 show('입출고 기록 수정',`${m.name} · ${kinds[m.kind]}`,`<div class="form-grid">${dates(m.day,'day','기록 날짜')}${field(m.kind==='adjust'?'수량 증감 *':'수량 *','qty',m.qty,'number',`required min="${m.kind==='adjust'?-1000000:1}" max="1000000" step="1"`)}${notes(m.kind==='adjust'?'조정 사유 *':'메모','note',m.note,m.kind==='adjust')}</div><div class="info-box">수량을 수정하면 현재 재고가 차이만큼 자동 변경됩니다. 재고가 음수가 되는 수정은 저장되지 않습니다.</div>`,{submit:'입출고 수정 저장',action:'movement-edit',build:v=>({...v,id})});
}

async function partnerDetail(id){
 const data=await request(`/api/partner/${id}`);const p=data.partner;
 show(p.name,'거래처 원장 · 판매부터 입금까지',`<div class="detail-strip"><div><label>받을 금액</label><b class="money-accent">${won(p.balance)}</b></div><div><label>누적 순판매</label><b>${won(p.volume)}</b></div><div><label>연락처</label><b style="font-size:16px">${h(p.phone||'미등록')}</b></div></div><div class="actions">${p.balance>0?`<button class="btn primary" data-detail-action="payment" data-partner-id="${id}">${icon('wallet')}입금 기록</button>`:''}<button class="btn" data-detail-action="edit-partner" data-id="${id}">${icon('edit')}정보 수정</button><a class="btn" href="/api/export/ledger?partner_id=${id}">${icon('download')}원장 CSV</a></div>${p.note?`<p class="detail-note">${h(p.note)}</p>`:''}<h3 class="section-label">거래 원장 <span class="muted">${num(data.ledger.length)}건</span></h3>${data.ledger.length?`<div class="detail-table"><table class="compact"><thead><tr><th>날짜</th><th>내용</th><th class="right">판매 증감</th><th class="right">입금 증감</th><th class="right">미수 잔액</th></tr></thead><tbody>${data.ledger.map(l=>`<tr class="click-row" data-detail-action="sale" data-id="${l.sale_id}"><td>${h(l.day)}</td><td>${h(l.kind)}<span class="subtext">${h(l.number)}</span></td><td class="right">${l.debit?num(l.debit):'—'}</td><td class="right">${l.credit?num(l.credit):'—'}</td><td class="right primary-text">${num(l.balance)}</td></tr>`).join('')}</tbody></table></div>`:empty('아직 거래 기록이 없습니다.','판매를 등록하면 이곳에 쌓입니다.')}<div class="info-box">날짜순 누적 잔액입니다. 판매·반품은 판매 증감에, 입금·환불·입금 정정은 입금 증감에 표시됩니다.</div>`,{wide:true});
}

async function movementDetail(id){
 const p=state().products.find(p=>p.id===id);const data=await request(`/api/movements${id?'?product_id='+id:''}`);
 const movementRows=data.movements.map(m=>`<tr><td>${h(m.day)}</td>${!p?`<td>${h(m.name)}<span class="subtext">${h(m.spec)}</span></td>`:''}<td><span class="tag ${m.qty>0?'green':'neutral'}">${h(kinds[m.kind])}</span></td><td class="right primary-text ${m.qty>0?'money-accent':''}">${m.qty>0?'+':''}${num(m.qty)} ${h(m.unit)}</td><td class="break">${h(m.note)}</td><td>${['opening','receive','adjust'].includes(m.kind)?`<div class="actions"><button class="text-button" data-detail-action="edit-movement" data-id="${m.id}">수정</button><button class="text-button negative" data-detail-action="delete" data-entity="movement" data-id="${m.id}" data-label="${h(m.day+' '+kinds[m.kind])}">삭제</button></div>`:''}</td></tr>`).join('');
 show(p?`${p.name} · 입출고 이력`:'전체 입출고 이력',p?`${p.spec} · 현재 ${num(p.stock)}${p.unit}`:'모든 수량 변경을 기록 순서와 날짜로 확인합니다.',`<div class="actions"><a class="btn small" href="/api/export/movements${id?'?product_id='+id:''}">${icon('download',16)}CSV 내려받기</a></div><h3 class="section-label">${num(data.movements.length)}건의 기록</h3>${data.movements.length?`<div class="detail-table"><table class="compact"><thead><tr><th>날짜</th>${!p?'<th>품목</th>':''}<th>내용</th><th class="right">수량 증감</th><th>메모</th><th></th></tr></thead><tbody>${movementRows}</tbody></table></div>`:empty('아직 입출고 이력이 없습니다.','입고나 판매를 저장하면 자동으로 기록됩니다.')}`,{wide:true});
}

function deleteForm(entity,id,label){
 const names={product:'품목',partner:'거래처',sale:'판매 거래',payment:'입금',return:'반품',movement:'입출고 기록'};
 show(`${names[entity]||'기록'} 삭제`,label,`<div class="info-box amber">삭제하면 장부·재고·미수금이 자동으로 다시 계산됩니다. 연결된 기록도 함께 처리되며 휴지통에서 복구할 수 있습니다.</div><p class="muted">정말 잘못 입력한 기록인지 확인해 주세요.</p>`,{submit:'휴지통으로 이동',action:'delete',build:()=>({entity,id})});
}

function trashAction(id,purge){
 const item=state().trash.find(x=>x.id===id);if(!item)throw Error('휴지통 기록을 찾을 수 없습니다.');
 show(purge?'영구 삭제':'기록 복구',item.label,purge?'<div class="info-box amber">영구 삭제하면 다시 복구할 수 없습니다. 삭제·복구 이력만 안전 기록으로 남습니다.</div>':'<div class="info-box">재고·입금·미수금도 삭제 전 상태로 복구합니다. 현재 장부와 충돌하면 안전을 위해 복구하지 않습니다.</div>',{submit:purge?'복구할 수 없게 삭제':'장부로 복구',action:purge?'trash-purge':'trash-restore',build:()=>({id})});
}

function archiveForm(table,id,archived){
 const item=state()[table].find(x=>x.id===id);
 show(archived?'항목 보관':'보관 해제',item.name,`<div class="info-box">${archived?'기존 거래와 이력은 그대로 남습니다. 신규 거래 선택 목록에서만 숨겨집니다. 재고 또는 미수금이 남아 있으면 보관할 수 없습니다.':'신규 거래 선택 목록에 다시 표시됩니다.'}</div>`,{submit:archived?'보관하기':'보관 해제',action:'archive',build:()=>({table,id,archived})});
}

function businessForm(){
 const s=state().settings;
 show('사업장 정보','거래명세서에 표시할 정보를 입력하세요.',`<div class="form-grid">${field('사업장명 *','business',s.business,'text','required maxlength="120"')}${field('대표 / 담당자','owner',s.owner,'text','maxlength="60"')}${field('전화','phone',s.phone,'tel','maxlength="40"')}${field('주소','address',s.address,'text','maxlength="200"')}</div>`,{submit:'정보 저장',action:'settings'});
}

function restoreForm(){
 show('백업 복원','선택한 백업 시점의 장부로 돌아갑니다.',`<div class="info-box amber">현재 장부를 백업 내용으로 교체합니다. 복원 전 자료는 별도 백업으로 자동 보존됩니다. 파일 안의 거래처·판매·재고 연결이 정상인지 검사한 뒤 복원합니다.</div><div class="form-grid"><div class="field full"><label for="restore-file">아테나 백업 파일 (.db)</label><input id="restore-file" type="file" accept=".db" required></div><div class="field full"><label for="restore-confirm">확인하려면 ‘복원’을 입력해 주세요.</label><input id="restore-confirm" autocomplete="off" placeholder="복원"></div></div><div class="actions" style="margin-top:25px"><button class="btn danger" id="restore-submit">선택한 백업으로 복원</button><button class="btn" data-close>닫기</button></div>`);
 const revision=formRevision;
 content.querySelector('#restore-submit').addEventListener('click',async e=>{
  const btn=e.currentTarget;const errorBox=content.querySelector('.form-error');errorBox.textContent='';
  try{const file=content.querySelector('#restore-file').files[0];if(!file)throw Error('백업 파일을 선택해 주세요.');if(file.size>50*1024*1024)throw Error('50MB 이하의 백업을 선택해 주세요.');if(content.querySelector('#restore-confirm').value!=='복원')throw Error('확인란에 ‘복원’을 입력해 주세요.');btn.disabled=true;btn.textContent='검사 및 복원 중…';
   await request('/api/restore',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Athena-CSRF':state().csrf,'X-Athena-Restore':'RESTORE','X-Athena-Revision':String(revision)},body:await file.arrayBuffer()});dialog.close();await env.refresh();env.toast('백업을 복원했습니다.');
  }catch(error){errorBox.textContent=error.message;btn.disabled=false;btn.textContent='선택한 백업으로 복원';}
 });
}
