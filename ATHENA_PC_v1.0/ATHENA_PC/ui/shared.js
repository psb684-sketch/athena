export const h = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const num = v => Number(v||0).toLocaleString('ko-KR');
export const won = v => `${num(v)}원`;
export const shortDay = v => v ? v.slice(5).replace('-','.') : '—';
export const methods = {transfer:'계좌이체',cash:'현금',card:'카드',other:'기타'};
export const kinds = {opening:'시작 재고',receive:'입고',adjust:'재고 조정',sale:'판매 출고',return:'반품 입고'};
export const status = s => s.kind==='opening' ? '<span class="tag neutral">시작 미수금</span>' : s.net===0 ? '<span class="tag neutral">전액 반품</span>' : s.balance>0 ? `<span class="tag amber">${s.paid>0?'부분 입금':'미입금'}</span>` : '<span class="tag green">입금 완료</span>';
export const icon = (name,size=20) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${{
 plus:'<path d="M12 5v14M5 12h14"/>',arrow:'<path d="m9 5 7 7-7 7"/>',box:'<path d="m3 7 9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10M7 5l9 4"/>',wallet:'<path d="M20 8V5H4a1 1 0 0 0-1 1v13h18V8H4M21 11h-6v5h6M17 13.5h.01"/>',receipt:'<path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6M9 15h3"/>',people:'<path d="M4 21v-2a5 5 0 0 1 10 0v2M16 14a5 5 0 0 1 4 5v2"/><circle cx="9" cy="7" r="4"/><path d="M16 3a4 4 0 0 1 0 8"/>',download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',check:'<path d="m5 12 4 4L19 6"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',print:'<path d="M7 8V3h10v5M7 17H3V8h18v9h-4M7 13h10v8H7zM17 11h1"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6"/>',return:'<path d="m8 5-5 5 5 5M3 10h12a6 6 0 0 1 0 12"/>',edit:'<path d="m15 4 5 5-11 11H4v-5zM13 6l5 5"/>'}[name]||''}</svg>`;
export async function request(url,options={}) {
 let response;
 try { response=await fetch(url,{cache:'no-store',...options}); }
 catch { throw new Error('아테나 실행 창이 열려 있는지 확인해 주세요. 저장 중이었다면 새로고침으로 기록을 먼저 확인해 주세요.'); }
 const data=await response.json().catch(()=>({error:'응답을 읽지 못했습니다.'}));
 if(!response.ok) throw new Error(data.error||'요청을 처리하지 못했습니다.');
 return data;
}
export const empty = (title,text,button='') => `<div class="empty"><span class="empty-icon">${icon('receipt',28)}</span><h3>${h(title)}</h3><p>${h(text)}</p>${button}</div>`;
