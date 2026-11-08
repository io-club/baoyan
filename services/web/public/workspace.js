const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={password:'',tab:'activities',month:new Date().toISOString().slice(0,7),tags:[],view:'calendar',q:''};
state.tab=window.platformRoute?.()||'activities';
try{const saved=JSON.parse(sessionStorage.getItem('baoyan-ui-state')||'{}');Object.assign(state,{month:saved.month||state.month,day:saved.day||'',view:saved.view||state.view,q:saved.q||''});}catch{}
try{state.password=localStorage.getItem('baoyan-password')||'';}catch{}
const tabs=[['activities','保研日历'],['intel','情报工作台'],['advisors','导师库'],['outreach','套磁与草稿'],['materials','材料与口径'],['tasks','任务中心'],['agent','Agent'],['settings','设置']],actions={},views={};
const button=(text,action,cls='secondary')=>`<button type="button" class="${cls}" data-action="${action}">${esc(text)}</button>`;
const labels={queued:'等待开始',scheduled:'按计划进行',starting:'正在准备',running:'进行中',canceling:'正在停止',succeeded:'已完成',failed:'未完成',canceled:'已取消',stopped:'已停止',pending:'待整理',processed:'已整理',processing:'整理中',xiaohongshu:'小红书',qq:'QQ 群聊',manual:'手动添加',text:'文字材料',pdf:'PDF 文档',image:'图片',spreadsheet:'表格',file:'文件'};
const label=v=>labels[v]||v;
const badge=(text,cls='')=>`<span class="tag ${cls}">${esc(label(text))}</span>`;
const empty=text=>`<div class="empty">${esc(text)}</div>`;
let savedTables={};try{savedTables=JSON.parse(sessionStorage.getItem('baoyan-table-pages')||'{}')}catch{}
const tablePages=savedTables.pages||{},tableSizes=savedTables.sizes||{};
const table=(heads,rows)=>{
 const key=state.tab+'-'+heads.join('|'),remote=pageResults[key],size=tableSizes[key]||10,total=remote?.total??rows.length,page=Math.min(tablePages[key]||1,Math.max(1,Math.ceil(total/size)));tablePages[key]=page;
 const paged=!['intel','settings','agent'].includes(state.tab)&&!$('#editor').open;
 const visible=paged&&!remote?rows.slice((page-1)*size,page*size):rows;
 return `<div class="table-wrap"><table><thead><tr>${heads.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${visible.join('')||`<tr><td colspan="${heads.length}">${empty('暂无数据')}</td></tr>`}</tbody></table></div>`+(paged?`<div class="filterbar table-pagination" data-pagination="${esc(key)}">${pager(page,total,size,'tablePage:'+encodeURIComponent(key))}<label>每页<select data-table-size="${esc(key)}">${[10,20,50,100].map(n=>`<option ${n===size?'selected':''}>${n}</option>`).join('')}</select></label></div>`:'');
};

const intros={activities:'把重要日期记下来，为每一次机会留足准备。',intel:'把分散的信息收集在一起，找到对你有用的线索。',advisors:'了解研究方向，找到与你志趣相投的导师。',outreach:'认真准备每一次联系，让沟通有迹可循。',materials:'整理申请材料与信息口径，为不同的申请做好准备。',tasks:'查看收集与整理进展，安心把时间留给准备。',agent:'一起梳理信息、规划申请，推进眼前的下一步。',settings:'管理访问口令、模型服务与邮箱连接。'};
const toolbar=(title,buttons='')=>`<div class="toolbar"><h2>${tabs.find(t=>t[0]===state.tab)?.[1]||esc(title)}</h2>${buttons}<p class="page-intro">${intros[state.tab]||''}</p></div>`;
function stats(items){return '<div class="stat-strip">'+items.map(([name,value,unit])=>`<div class="stat-card"><small>${esc(name)}</small><strong>${value}<span>${esc(unit||'')}</span></strong></div>`).join('')+'</div>';}
function userError(value){return String(value||"操作失败，请重试");}

const show=html=>{window.platformUnmountCalendar?.();if(typeof attachmentUrls!=='undefined'){for(const u of attachmentUrls)URL.revokeObjectURL(u);attachmentUrls.clear();}$('#content').innerHTML=html;};
function toast(text){if(window.platformMessage){window.platformMessage(text);return;}$('#toast').textContent=text;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,5000);}
function logout(){state.password='';try{localStorage.removeItem('baoyan-password');}catch{}$('#app').hidden=true;$('#login').hidden=false;}
async function request(url,options={}){const headers={'X-Admin-Password':state.password,...options.headers};if(options.body&&!(options.body instanceof FormData))headers['Content-Type']='application/json';const r=await fetch(url,{...options,headers});if(r.status===401){logout();throw Error('口令无效或已更新，请重新登录');}if(!r.ok){let message=await r.text();try{const d=JSON.parse(message).detail;message=typeof d==='string'?d:JSON.stringify(d);}catch{}throw Error(message||`HTTP ${r.status}`);}return r.status===204?null:r.json();}
const api=(p,o)=>request('/api/platform'+p,o),taskApi=(p='',o)=>request('/api/tasks'+p,o);
const post=(p,v)=>api(p,{method:'POST',body:JSON.stringify(v)}),patch=(p,v)=>api(p,{method:'PATCH',body:JSON.stringify(v)});
const rows=async(resource,q='')=>(await api('/entities/'+resource+'?limit=1000&q='+encodeURIComponent(q))).items;
const pageResults={};
const advisorFilters={school:'',department:'',institute:'',category:''};
try{Object.assign(advisorFilters,JSON.parse(sessionStorage.getItem('baoyan-advisor-filters')||'{}'));}catch{}
const resourceHeads={activities:['活动 / 学校','截止','备注','操作'],advisors:['导师','学校 / 院系','联系','操作'],materials:['材料','说明 / 类型','内容 / 文件','操作'],targets:['对象','说明','操作'],templates:['模板','说明','操作'],'outreach-records':['导师','状态','标签 / 备注','操作'],tasks:['工作内容','进展','时间','操作']};
async function pagedRows(resource,q=''){
 const key=state.tab+'-'+resourceHeads[resource].join('|'),size=tableSizes[key]||10,page=tablePages[key]||1;
 const result=await api('/entities/'+resource+'?limit='+size+'&offset='+((page-1)*size)+'&q='+encodeURIComponent(q)+(resource==='advisors'?'&'+new URLSearchParams(advisorFilters):''));
 const last=Math.max(1,Math.ceil(result.total/size));if(page>last){tablePages[key]=last;return pagedRows(resource,q);}
 pageResults[key]={total:result.total};return result.items;
}
actions.tablePage=async(key,page)=>{tablePages[decodeURIComponent(key)]=Number(page);await render();};
$('#content').addEventListener('change',e=>{if(e.target.matches('[data-table-size]')){tableSizes[e.target.dataset.tableSize]=Number(e.target.value);tablePages[e.target.dataset.tableSize]=1;render();}});
async function allTasks(){const key='tasks-'+resourceHeads.tasks.join('|'),size=tableSizes[key]||10,page=tablePages[key]||1;const r=await taskApi('?limit='+size+'&offset='+((page-1)*size));const last=Math.max(1,Math.ceil(r.total/size));if(page>last){tablePages[key]=last;return allTasks();}pageResults[key]={total:r.total};return r;}

const get=(r,id)=>api(`/entities/${r}/${id}`),create=(r,v)=>post('/entities/'+r,v),update=(r,id,v)=>patch(`/entities/${r}/${id}`,v);
const options=list=>list.map(x=>[x.id,x.data.name||x.data.title||x.id]);
const field=(key,label,type='text',extra={})=>({key,label,type,...extra});
const time=v=>v?new Date(v).toLocaleString('zh-CN',{hour12:false}):'—';
const navPaths={activities:'M4 5h16v15H4z M8 3v4 M16 3v4 M4 10h16 M8 14h2 M14 14h2',intel:'M4 4h16v16H4z M8 8h8 M8 12h8 M8 16h4',advisors:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M17 4a4 4 0 0 1 0 7 M22 21v-2a4 4 0 0 0-3-4',outreach:'M3 5h18v14H3z M3 6l9 7 9-7',materials:'M3 7h7l2-3h9v16H3z',tasks:'M9 6h12 M9 12h12 M9 18h12 M3 6l1 1 2-2 M3 12l1 1 2-2 M3 18l1 1 2-2',agent:'M4 4h16v13H9l-5 4z M8 9h8 M8 13h5',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 3v2 M12 19v2 M3 12h2 M19 12h2 M5.6 5.6l1.4 1.4 M17 17l1.4 1.4 M5.6 18.4L7 17 M17 7l1.4-1.4'};
function nav(){window.platformNavigate?.(state.tab);$('#page-name').textContent=tabs.find(t=>t[0]===state.tab)?.[1]||'';}

$('#nav').onclick=e=>{const b=e.target.closest('[data-tab]');if(b){state.tab=b.dataset.tab;state.q='';nav();render();}};
$('#logout').onclick=e=>{e.preventDefault();logout();};
$('#editor-close').onclick=()=>$('#editor').close();
$('#login-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;$('#login-error').textContent='';try{const password=$('#password').value;const r=await fetch('/api/platform/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});const data=await r.json();if(!r.ok||!data.ok)throw Error('口令错误');state.password=password;try{localStorage.setItem('baoyan-password',password);}catch{}$('#login').hidden=true;$('#app').hidden=false;nav();await render();}catch(err){$('#login-error').textContent=err.message;}finally{e.submitter.disabled=false;}};
function form(title,fields,save,initial={}){$('#editor-title').textContent=title;$('#editor-error').textContent='';$('#editor-save').hidden=false;$('#editor-fields').innerHTML=fields.map(f=>{const v=initial[f.key]??f.default??'';let input;if(f.type==='select')input=`<select name="${f.key}" ${f.multiple?'multiple':''}>${f.options.map(o=>{const [value,label]=Array.isArray(o)?o:[o,o];const selected=f.multiple?(Array.isArray(v)?v:[]).includes(value):String(value)===String(v);return `<option value="${esc(value)}" ${selected?'selected':''}>${esc(label)}</option>`;}).join('')}</select>`;else if(['textarea','json'].includes(f.type))input=`<textarea name="${f.key}" ${f.required?'required':''}>${esc(f.type==='json'?JSON.stringify(v||{},null,2):v)}</textarea>`;else if(f.type==='checkbox')input=`<input name="${f.key}" type="checkbox" ${v?'checked':''}>`;else input=`<input name="${f.key}" type="${f.type}" ${f.type==='file'?'':`value="${esc(v)}"`} ${f.required?'required':''} ${f.min!==undefined?`min="${f.min}"`:''}>`;return `<label class="field">${esc(f.label)}${f.required?' *':''}${input}${f.help?`<small>${esc(f.help)}</small>`:''}</label>`;}).join('');$('#editor-form').onsubmit=async e=>{e.preventDefault();$('#editor-save').disabled=true;$('#editor-error').textContent='';try{const v={};for(const f of fields){const el=e.target.elements.namedItem(f.key);if(f.required&&!(f.type==='file'?el.files.length:el.value?.trim()))throw Error('请填写'+f.label);v[f.key]=f.type==='checkbox'?el.checked:f.type==='file'?el.files[0]:f.multiple?Array.from(el.selectedOptions,o=>o.value):f.type==='json'?JSON.parse(el.value||'{}'):f.type==='number'?Number(el.value):el.value;}await save(v);$('#editor').close();toast('操作成功');await render();}catch(err){$('#editor-error').textContent=err.message;}finally{$('#editor-save').disabled=false;}};$('#editor').showModal();}
function details(title,text){$('#editor-fields').classList.remove('log-view');$('#editor-title').textContent=title;$('#editor-fields').innerHTML=`<pre>${esc(text)}</pre>`;$('#editor-error').textContent='';$('#editor-save').hidden=true;$('#editor-form').onsubmit=e=>e.preventDefault();$('#editor').showModal();}
async function remove(resource,id){if(await window.platformConfirm('确认删除这条记录？')){await api(`/entities/${resource}/${id}`,{method:'DELETE'});if(resource==='intel-items')intelState.selected.delete(id);await render();}}
async function download(object,filename){const r=await fetch('/api/platform/files?object='+encodeURIComponent(object),{headers:{'X-Admin-Password':state.password}});if(!r.ok)throw Error('下载失败');const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=filename||object.split('/').pop();document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
window.platformApplyRoute=key=>{if(!views[key])return;state.tab=key;nav();render();};
window.platformDispatch=(action,...args)=>actions[action]?.(...args);
async function render(){sessionStorage.setItem('baoyan-ui-state',JSON.stringify({month:state.month,day:state.day,view:state.view,q:state.q}));sessionStorage.setItem('baoyan-table-pages',JSON.stringify({pages:tablePages,sizes:tableSizes}));document.body.dataset.page=state.tab;const taskView=state.tab==='tasks'&&$('#content [data-task-table]');if(!taskView)show(empty('加载中…'));try{await views[state.tab]();}catch(e){if(taskView){toast(e.message);return;}show('<section class="panel error"><h2>加载失败</h2><p>'+esc(e.message)+'</p>'+button('重试','refresh')+'</section>');}}

actions.refresh=render;
const dispatchAction=async e=>{const b=e.target.closest('[data-action]');if(!b)return;const [action,...args]=b.dataset.action.split(':');b.disabled=true;try{if(!actions[action])throw Error('操作不存在');await actions[action](...args);}catch(err){toast(err.message);}finally{b.disabled=false;}};
actions.delete=(r,id)=>remove(r,id);actions.file=o=>download(decodeURIComponent(o));
document.addEventListener('click',dispatchAction);
actions.attachmentFile=(object,filename)=>download(decodeURIComponent(object),decodeURIComponent(filename));
actions.import=r=>form('批量导入 JSON',[field('items','记录数组','json',{default:[]})],v=>{if(!Array.isArray(v.items))throw Error('请输入 JSON 数组');return post('/import/'+r,v);});

actions.export=async r=>{const data=await rows(r),url=URL.createObjectURL(new Blob([JSON.stringify(data.map(x=>x.data),null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=r+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};

function taskName(t){if(t.command?.includes('app.crawl_xhs'))return '小红书信息收集';if(t.command?.includes('app.qq_watcher'))return 'QQ 群消息收集';if(t.command?.includes('app.consume_intel'))return '情报整理与总结';if(t.command?.includes('app.crawl_activities'))return '院校活动收集';return /[\u4e00-\u9fa5]/.test(t.name)?t.name:'后台工作';}
function taskMessage(t){if(t.status==='failed')return '本次工作未完成，可查看详情后重新尝试。';if(t.status==='succeeded')return '处理完成，结果已保存。';if(t.status==='running')return t.kind==='service'?'正在持续收集新的信息。':'正在处理，请稍候。';return ({queued:'已加入待办，等待开始。',scheduled:'将在预定时间继续。',stopped:'已停止收集。',canceled:'已取消本次工作。',starting:'正在准备所需资料。',canceling:'正在结束当前工作。'})[t.status]||'进度将在这里更新。';}
let taskViewRequest=0;
views.tasks=async()=>{
 const request=++taskViewRequest,data=await allTasks(),items=data.items;
 if(request!==taskViewRequest||state.tab!=='tasks')return;
 const markup=toolbar('工作进展',button('刷新','refresh')+button('创建任务','newTask',''))+stats([['本页进行中',items.filter(t=>['running','starting','queued'].includes(t.status)).length,'项'],['本页已完成',items.filter(t=>t.status==='succeeded').length,'项'],['本页未完成',items.filter(t=>t.status==='failed').length,'项']])+table(['工作内容','进展','时间','操作'],items.map(t=>`<tr data-row-key="${esc(t.id)}"><td><strong>${esc(taskName(t))}</strong><p class="meta">${t.kind==='service'?'持续收集':t.kind==='scheduled'?'定期更新':'单次整理'}</p></td><td>${badge(t.status,t.status)}<p>${esc(t.status_message||t.error||taskMessage(t))}</p>${t.kind==='service'?'':`<progress max="100" value="${t.progress}"></progress>`}</td><td>${time(t.next_run_at||t.started_at||t.created_at)}</td><td>${button('查看日志','taskLog:'+t.id)}${button('处理记录','taskRuns:'+t.id)}${['succeeded','failed','canceled','stopped'].includes(t.status)?button('删除','taskDelete:'+t.id,'danger'):button('停止','taskCancel:'+t.id,'danger')}</td></tr>`));
 const existing=$('#content [data-task-table]');
 if(existing){
  const next=document.createElement('template');next.innerHTML=markup;
  if(window.platformPatchTable?.(existing,next.content.querySelector('table'))){
   window.platformPatchStats?.([['本页进行中',items.filter(t=>['running','starting','queued'].includes(t.status)).length],['本页已完成',items.filter(t=>t.status==='succeeded').length],['本页未完成',items.filter(t=>t.status==='failed').length]]);
   const key='tasks-'+resourceHeads.tasks.join('|'),size=tableSizes[key]||10;
   window.platformPatchPagination?.($('#content [data-naive-pagination]'),{page:tablePages[key]||1,size,total:data.total});
   return;
  }
 }
 show(markup);$('#content .table-wrap').dataset.taskTable='true';
};
actions.newTask=()=>form('创建后台任务',[field('name','任务名称','text',{required:true}),field('description','说明'),field('kind','类型','select',{options:[['oneshot','运行一次'],['scheduled','定时'],['service','常驻服务']]}),field('command','命令参数 JSON 数组','json',{default:['python','-c','print("hello")']}),field('schedule_cron','Cron（仅定时任务）'),field('timezone','时区','text',{default:'Asia/Shanghai'}),field('timeout_seconds','超时秒数','number',{default:3600,min:1}),field('restart_policy','服务重启策略','select',{options:['none','on-failure','always']})],v=>{if(!Array.isArray(v.command)||!v.command.length)throw Error('命令必须是非空数组');if(v.kind!=='scheduled')delete v.schedule_cron;return taskApi('',{method:'POST',body:JSON.stringify(v)});});
let logTimer=null;
$('#editor').addEventListener('close',()=>{clearInterval(logTimer);delete $('#editor').dataset.logTask;});
actions.taskLog=async id=>{
 clearInterval(logTimer);details('任务日志','正在读取日志…');$('#editor-fields').classList.add('log-view');$('#editor').dataset.logTask=id;
 const load=async()=>{const r=await fetch(`/api/tasks/${id}/logs?tail=500`,{headers:{'X-Admin-Password':state.password}});if(!r.ok)throw Error('无法获取日志');const text=await r.text();if(!$('#editor').open||$('#editor').dataset.logTask!==id)return;const pre=$('#editor-fields pre'),bottom=pre.scrollHeight-pre.scrollTop-pre.clientHeight<30;pre.textContent=text||'任务暂时没有输出，日志会自动刷新。';if(bottom)pre.scrollTop=pre.scrollHeight;};
 await load();$('#editor-fields').insertAdjacentHTML('beforeend','<p class="meta">每 2 秒自动刷新 · 显示最近 500 行</p>');
 logTimer=setInterval(()=>{if(!$('#editor').open||$('#editor').dataset.logTask!==id){clearInterval(logTimer);return;}load().catch(e=>{$('#editor-error').textContent=e.message;});},2000);
};

actions.taskRuns=async id=>{const runs=await taskApi('/'+id+'/runs');details('处理记录','');$('#editor-fields').innerHTML=table(['次数','状态','开始时间','结束时间'],runs.map(r=>`<tr><td>第 ${r.attempt} 次</td><td>${badge(r.status,r.status)}</td><td>${time(r.started_at)}</td><td>${time(r.finished_at)}</td></tr>`));};
actions.taskCancel=async id=>{if(await window.platformConfirm('确定停止这项工作？已保存的信息会保留。')){await taskApi('/'+id+'/cancel',{method:'POST'});await render();}};
actions.taskDelete=async id=>{if(await window.platformConfirm('确定删除这项工作记录？')){await taskApi('/'+id,{method:'DELETE'});await render();}};


views.activities=async()=>{show('<div id="calendar-workspace"></div>');window.platformMountCalendar(document.querySelector('#calendar-workspace'),{api,dispatch:(...args)=>window.platformDispatch(...args)});};
actions.crawlActivity=()=>form('采集保研活动',[field('start_page','起始页','number',{default:1,min:1}),field('end_page','结束页（留空采集全部）','number',{min:1}),field('page_size','每页条数','number',{default:25,min:1}),field('resume','从上次未完成进度继续','checkbox',{default:true})],async v=>{v.end_page=v.end_page||null;if(v.end_page&&v.end_page<v.start_page)throw Error('结束页不能小于起始页');await post('/activity-crawl',v);state.tab='tasks';nav();});
actions.newReminder=async()=>form('截止提醒',[field('name','规则名称','text',{required:true}),field('days_before','提前天数','number',{default:3,min:0}),field('tag_ids','适用标签（不选为全部）','select',{multiple:true,options:options(await rows('tags'))}),field('enabled','启用','checkbox',{default:true})],v=>create('reminders',v));
actions.toggleReminder=async id=>{const r=await get('reminders',id);await update('reminders',id,{enabled:!r.data.enabled});await render();};
actions.readNotice=async id=>{await update('notifications',id,{read:true});await render();};

const advisorFields=[field('name','导师姓名','text',{required:true}),field('school','学校'),field('department','学院 / 院系'),field('institute','研究所 / 研究中心'),field('category','分类'),field('title','职称'),field('research_directions_text','研究方向（每行一个）','textarea'),field('bio','个人简介','textarea'),field('email','邮箱','email'),field('homepage','个人主页','url'),field('photo','照片链接','url'),field('extra_fields','其他资料 JSON','json',{help:'保留来源中的原始字段，例如 center、研究方向、categories、raw_list 等；上方常用字段独立编辑。'})];
function safeUrl(v){try{const u=new URL(v,location.origin);return ['http:','https:'].includes(u.protocol)?u.href:'';}catch{return '';}}
views.advisors=async()=>{const [list,facets]=await Promise.all([pagedRows('advisors',state.q),api('/advisor-facets?'+new URLSearchParams(advisorFilters))]);
 const filters=[['school','学校'],['department','学院 / 院系'],['institute','研究所 / 中心'],['category','分类']].map(([key,title])=>`<label>${title}<select data-advisor-filter="${key}" aria-label="${title}"><option value="">全部${title}</option>${facets[key].map(x=>`<option value="${esc(x.value)}" ${advisorFilters[key]===x.value?'selected':''}>${esc(x.value)}（${x.count}）</option>`).join('')}</select></label>`).join('');
 show(toolbar('导师信息库',button('导入 JSON','import:advisors')+button('导出 JSON','export:advisors')+button('新增导师','newAdvisor',''))+`<div class="filterbar">${filters}${button('清除筛选','advisorReset')}</div><div class="filterbar"><input id="advisor-query" value="${esc(state.q)}" placeholder="搜索导师 / 研究方向">${button('搜索','advisorSearch')}</div>`+table(['导师','学校 / 院系','联系','操作'],list.map(a=>{const d=a.data,categories=[...new Set([d.category,...(d.categories||[])].filter(Boolean))];return `<tr><td>${d.photo?`<img class="avatar" src="${esc(safeUrl(d.photo))}" alt="">`:''}<strong>${esc(d.name)}</strong><p>${esc(d.title||'')}</p>${categories.map(c=>badge(c)).join('')}</td><td>${esc(d.school||'未分类')}<p>${esc(d.department||'未分类')}</p><p>${esc(d.institute||'')}</p></td><td>${esc(d.email)}<p>${d.homepage?`<a href="${esc(safeUrl(d.homepage))}" target="_blank" rel="noopener">个人主页</a>`:''}</p></td><td>${button('编辑','advisorEdit:'+a.id)}${button('删除','delete:advisors:'+a.id,'danger')}</td></tr>`;})));};
actions.advisorReset=()=>{Object.keys(advisorFilters).forEach(k=>advisorFilters[k]='');state.q='';tablePages['advisors-'+resourceHeads.advisors.join('|')]=1;sessionStorage.removeItem('baoyan-advisor-filters');return render();};
$('#content').addEventListener('change',e=>{const key=e.target.dataset.advisorFilter;if(!key)return;advisorFilters[key]=e.target.value;const keys=Object.keys(advisorFilters);keys.slice(0,3).includes(key)&&keys.slice(keys.indexOf(key)+1).forEach(k=>advisorFilters[k]='');sessionStorage.setItem('baoyan-advisor-filters',JSON.stringify(advisorFilters));tablePages['advisors-'+resourceHeads.advisors.join('|')]=1;render();});
const advisorPayload=v=>{const {research_directions_text,extra_fields,...data}=v;if(!extra_fields||typeof extra_fields!=='object'||Array.isArray(extra_fields))throw Error('其他资料 JSON 必须是对象');return {...extra_fields,...data,research_directions:research_directions_text.split(/\r?\n/).map(s=>s.trim()).filter(Boolean)};};
actions.newAdvisor=()=>form('新增导师',advisorFields,v=>create('advisors',advisorPayload(v)));actions.advisorEdit=async id=>{const d=(await get('advisors',id)).data;form('编辑导师',advisorFields,v=>update('advisors',id,advisorPayload(v)),{...d,research_directions_text:(d.research_directions||[]).join('\n'),extra_fields:Object.fromEntries(Object.entries(d).filter(([key])=>key!=='research_directions'&&!advisorFields.some(f=>f.key===key)))});};actions.advisorSearch=()=>{tablePages['advisors-'+resourceHeads.advisors.join('|')]=1;state.q=$('#advisor-query').value;return render();};

const materialFields=[field('name','材料名称','text',{required:true}),field('description','描述 / 统计口径','textarea'),field('type','材料类型','select',{options:['text','pdf','image','spreadsheet','file']}),field('content','文本内容','textarea'),field('upload','上传文件（可选）','file')];
async function saveMaterial(v,id,old={}){const {upload,...data}=v;data.files=old.files||[];if(upload){const body=new FormData();body.append('file',upload);data.files=[...data.files,await api('/files',{method:'POST',body})];}return id?update('materials',id,data):create('materials',data);}
views.materials=async()=>{const [materials,targets]=await Promise.all([pagedRows('materials'),pagedRows('targets')]);show(toolbar('申请材料与信息口径',button('新增申请对象','newTarget')+button('上传 / 新增材料','newMaterial',''))+table(['材料','说明 / 类型','内容 / 文件','操作'],materials.map(m=>`<tr><td><strong>${esc(m.data.name)}</strong></td><td>${esc(m.data.description)} ${badge(m.data.type||'text')}</td><td>${esc((m.data.content||'').slice(0,100))}${(m.data.files||[]).map(f=>`<p>${button(f.filename||'下载','file:'+encodeURIComponent(f.object))}</p>`).join('')}</td><td>${button('编辑','materialEdit:'+m.id)}${button('删除','delete:materials:'+m.id,'danger')}</td></tr>`))+'<h3>申请对象与口径</h3>'+table(['对象','说明','操作'],targets.map(t=>`<tr><td>${esc(t.data.name)}</td><td>${esc(t.data.description)}</td><td>${button('关联材料与备注','targetLinks:'+t.id)}${button('编辑','targetEdit:'+t.id)}${button('删除','delete:targets:'+t.id,'danger')}</td></tr>`)));};
actions.newMaterial=()=>form('新增材料',materialFields,v=>saveMaterial(v));actions.materialEdit=async id=>{const r=await get('materials',id);form('编辑材料',materialFields,v=>saveMaterial(v,id,r.data),r.data);};
const targetFields=[field('name','对象名称','text',{required:true}),field('description','说明','textarea')];actions.newTarget=()=>form('新增申请对象',targetFields,v=>create('targets',v));actions.targetEdit=async id=>form('编辑申请对象',targetFields,v=>update('targets',id,v),(await get('targets',id)).data);
actions.targetLinks=async id=>{const [materials,links]=await Promise.all([rows('materials'),api('/relations/target-materials/'+id)]);form('关联材料口径',[field('related_id','材料','select',{options:options(materials),required:true}),field('note','口径备注','textarea')],v=>post('/relations/target-materials',{entity_id:id,...v}));$('#editor-fields').insertAdjacentHTML('afterbegin',`<section class="panel">${links.map(l=>`<p><strong>${esc(l.material?.name||'已删除')}</strong> ${esc(l.note)} <button type="button" data-unlink="${l.material_id}">解绑</button></p>`).join('')||'尚无关联材料'}</section>`);document.querySelectorAll('[data-unlink]').forEach(b=>b.onclick=async()=>{try{await api(`/relations/target-materials/${id}/${b.dataset.unlink}`,{method:'DELETE'});b.parentElement.remove();}catch(e){$('#editor-error').textContent=e.message;}});};

const templateFields=[field('name','模板名称','text',{required:true}),field('description','描述'),field('subject','邮件主题模板','text',{help:'例如：申请交流 · {{school}} · {{name}} 老师'}),field('content','正文模板','textarea',{required:true,help:'变量名按导师记录中的实际字段填写，例如 {{name}}；不同学校可以使用不同字段，只引用正文需要的信息'})];
views.outreach=async()=>{const [templates,records,advisors]=await Promise.all([pagedRows('templates'),pagedRows('outreach-records'),rows('advisors')]),names=Object.fromEntries(advisors.map(a=>[a.id,a.data.name]));show(toolbar('套磁模板与草稿',button('新增模板','newTemplate')+button('新增套磁记录','newOutreach')+button('生成邮件草稿','composeDraft',''))+table(['模板','说明','操作'],templates.map(t=>`<tr><td>${esc(t.data.name)}</td><td>${esc(t.data.description)}</td><td>${button('参数预览','previewTemplate:'+t.id)}${button('编辑','templateEdit:'+t.id)}${button('删除','delete:templates:'+t.id,'danger')}</td></tr>`))+'<h3>导师联系记录</h3>'+table(['导师','状态','标签 / 备注','操作'],records.map(r=>`<tr><td>${esc(names[r.data.advisor_id]||r.data.recipient_name||'未关联')}</td><td>${badge(r.data.status||'未套磁')}</td><td>${esc(r.data.notes)} ${(r.data.tags||[]).map(t=>badge(t)).join('')}</td><td>${button('更新状态','outreachEdit:'+r.id)}${button('删除','delete:outreach-records:'+r.id,'danger')}</td></tr>`)));};
actions.newTemplate=()=>form('新增套磁模板',templateFields,v=>create('templates',v));actions.templateEdit=async id=>form('编辑模板',templateFields,v=>update('templates',id,v),(await get('templates',id)).data);
actions.previewTemplate=id=>window.platformOpenMailComposer({api,download,toast,templateId:id,previewOnly:true});

async function outreachForm(id){const [advisors,row]=await Promise.all([rows('advisors'),id?get('outreach-records',id):null]);form('套磁记录',[field('advisor_id','关联导师','select',{options:options(advisors),required:true}),field('status','状态','select',{options:['未套磁','已套磁','已回复','已套到','套不到','暂缓']}),field('tags_text','标签（逗号分隔）'),field('notes','联系记录 / 备注','textarea')],v=>{const {tags_text,...data}=v;data.tags=tags_text.split(/[,，]/).map(x=>x.trim()).filter(Boolean);return id?update('outreach-records',id,data):create('outreach-records',data);},row?{...row.data,tags_text:(row.data.tags||[]).join(',')}:{});}actions.newOutreach=()=>outreachForm();actions.outreachEdit=id=>outreachForm(id);
actions.composeDraft=()=>window.platformOpenMailComposer({api,download,toast,onSaved:render});

function readableMessage(text){return String(text||'');}
function readableSummary(batch){return String(batch.summary||'');}

const intelState={page:1,size:20,start:'',end:'',q:'',selected:new Set(),batchPage:1,total:0};
function intelQuery(limit=intelState.size,offset=(intelState.page-1)*intelState.size){
  const p=new URLSearchParams({limit,offset,q:intelState.q});
  if(intelState.start)p.set('created_from',new Date(intelState.start).toISOString());
  if(intelState.end)p.set('created_before',new Date(new Date(intelState.end).getTime()+60000).toISOString());
  return p;
}
function intelSelectionCount(){const el=$('#intel-selection-count');if(el)el.textContent=`已选 ${intelState.selected.size} 条（跨页保留，单次最多 100 条）`;}
$('#content').addEventListener('change',e=>{
  if(!e.target.matches('.intel-select'))return;
  if(e.target.checked){if(intelState.selected.size>=100){e.target.checked=false;toast('单次总结最多选择 100 条，请分批处理');return;}intelState.selected.add(e.target.value);}
  else intelState.selected.delete(e.target.value);
  intelSelectionCount();
});
function oldPager(page,total,size,action){const pages=Math.max(1,Math.ceil(total/size));return `<div class="filterbar"><button type="button" class="secondary" data-action="${action}:${page-1}" ${page<=1?'disabled':''}>上一页</button><span>第 ${page} / ${pages} 页 · 共 ${total} 条</span><button type="button" class="secondary" data-action="${action}:${page+1}" ${page>=pages?'disabled':''}>下一页</button></div>`;}
function pager(page,total,size,action){return '<div data-naive-pagination data-page="'+page+'" data-total="'+total+'" data-size="'+size+'" data-page-action="'+esc(action)+'"></div>';}
views.intel=async()=>{
  const [data,batches]=await Promise.all([api('/entities/intel-items?'+intelQuery()),api('/entities/intel-batches?limit=10&offset='+((intelState.batchPage-1)*10))]);
  const pages=Math.max(1,Math.ceil(data.total/intelState.size)),batchPages=Math.max(1,Math.ceil(batches.total/10));
  if(intelState.page>pages||intelState.batchPage>batchPages){intelState.page=Math.min(intelState.page,pages);intelState.batchPage=Math.min(intelState.batchPage,batchPages);return views.intel();}
  intelState.total=data.total;
  show(toolbar('情报收集与消费',button('收集小红书','xhs')+button('连接 QQ 群','qq')+button('添加情报','newIntel')+button('总结所选','consumeIntel',''))+
    '<p class="meta">按入库时间筛选（本机时区，结束时间包含所选分钟）。重新采集不会改变入库时间。</p>'+
    `<div class="filterbar"><label>开始时间<input id="intel-start" type="datetime-local" value="${esc(intelState.start)}"></label><label>结束时间<input id="intel-end" type="datetime-local" value="${esc(intelState.end)}"></label><label>关键词<input id="intel-query" value="${esc(intelState.q)}" placeholder="搜索情报"></label><label>每页条数<select id="intel-size">${[10,20,50,100].map(n=>`<option ${n===intelState.size?'selected':''}>${n}</option>`).join('')}</select></label>${button('筛选','intelFilter')}${button('今天','intelPreset:today')}${button('最近 7 天','intelPreset:week')}${button('重置','intelReset')}</div>`+
    `<div class="filterbar">${button('选择本页','intelSelectPage')}${button('选择筛选结果','intelSelectFiltered')}${button('清空选择','intelClear')}<span id="intel-selection-count"></span></div>`+
    table(['选择','收集时间 / 来源','标题 / 内容','附件','状态','操作'],data.items.map(i=>`<tr><td><input class="intel-select" aria-label="选择情报" type="checkbox" value="${i.id}" ${intelState.selected.has(i.id)?'checked':''}></td><td>${time(i.created_at)}<p>${badge(i.data.source)}</p></td><td><strong>${esc(i.data.title)}</strong><p class="intel-excerpt">${esc(displayIntelText(i.data).slice(0,180))}</p></td><td>${attachmentMarkup(i.data,true)||'<span class="meta">—</span>'}</td><td>${esc(i.data.processing_status||'pending')}</td><td>${button('全文','intelDetail:'+i.id)}${button('删除','delete:intel-items:'+i.id,'danger')}</td></tr>`))+
    pager(intelState.page,data.total,intelState.size,'intelPage')+'<h3>总结记录</h3>'+batches.items.map(b=>`<section class="panel"><p class="meta">${time(b.created_at)} · ${(b.data.source_ids||[]).length} 个来源</p><div class="prose">${esc(readableSummary(b.data))}</div><div class="actions">${(b.data.source_ids||[]).map((id,i)=>button('查看来源 '+(i+1),'intelDetail:'+id)).join('')}</div></section>`).join('')+pager(intelState.batchPage,batches.total,10,'intelBatchPage'));
  intelSelectionCount();loadAttachmentImages();
};
actions.intelFilter=async()=>{
  const start=$('#intel-start').value,end=$('#intel-end').value;
  if(start&&end&&new Date(start)>new Date(end))throw Error('结束时间不能早于开始时间');
  Object.assign(intelState,{start,end,q:$('#intel-query').value.trim(),size:Number($('#intel-size').value),page:1});intelState.selected.clear();await render();
};
actions.intelPreset=async preset=>{const now=new Date(),start=new Date(now);if(preset==='today')start.setHours(0,0,0,0);else start.setDate(start.getDate()-7);const local=d=>new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);$('#intel-start').value=local(start);$('#intel-end').value=local(now);await actions.intelFilter();};
actions.intelReset=async()=>{Object.assign(intelState,{page:1,start:'',end:'',q:''});intelState.selected.clear();await render();};
actions.intelPage=async page=>{intelState.page=Math.max(1,Number(page));await render();};
actions.intelBatchPage=async page=>{intelState.batchPage=Math.max(1,Number(page));await render();};
actions.intelClear=()=>{intelState.selected.clear();document.querySelectorAll('.intel-select').forEach(el=>el.checked=false);intelSelectionCount();};
actions.intelSelectPage=()=>{const boxes=Array.from(document.querySelectorAll('.intel-select')),extra=boxes.filter(el=>!intelState.selected.has(el.value));if(intelState.selected.size+extra.length>100)throw Error('单次总结最多选择 100 条，请先清空或减少选择');boxes.forEach(el=>{el.checked=true;intelState.selected.add(el.value);});intelSelectionCount();};
actions.intelSelectFiltered=async()=>{const result=await api('/entities/intel-items?'+intelQuery(100,0));if(result.total>100)throw Error(`筛选结果有 ${result.total} 条，单次最多 100 条，请缩小时间范围`);intelState.selected=new Set(result.items.map(i=>i.id));await render();};
actions.newIntel=()=>form('录入情报',[field('source','来源','text',{default:'manual',required:true}),field('source_id','来源唯一编号 / 链接','text',{required:true}),field('title','标题'),field('content','文本内容','textarea'),field('attachment','附件（可选）','file')],async v=>{const {attachment,...payload}=v;payload.attachments=[];if(attachment){const body=new FormData();body.append('file',attachment);payload.attachments.push(await api('/intel/attachments',{method:'POST',body}));}return post('/intel/buffer',payload);});
function intelAttachments(data){return data.attachments||((data.metadata?.images||[]).filter(a=>a.object).map(a=>({...a,filename:a.file||'图片'})));}
function attachmentMarkup(data,compact=false){const attachments=intelAttachments(data);if(!attachments.length)return '';const list=compact?attachments.slice(0,3):attachments;return '<div class="intel-attachments">'+list.map((a,i)=>{
 const image=String(a.content_type||'').startsWith('image/')&&a.content_type!=='image/svg+xml';
 return '<div class="intel-attachment">'+(image?'<img data-intel-image="'+esc(a.object)+'" alt="'+esc(a.filename||'图片附件')+'" loading="lazy">':'<span class="attachment-file-icon" aria-hidden="true">▤</span>')+'<div><strong>'+esc(a.filename||'附件 '+(i+1))+'</strong><small>'+esc(a.size?Math.ceil(a.size/1024)+' KB':'附件')+'</small>'+button('下载','attachmentFile:'+encodeURIComponent(a.object)+':'+encodeURIComponent(a.filename||'附件'))+'</div></div>';
 }).join('')+(compact&&attachments.length>3?'<small>另有 '+(attachments.length-3)+' 个附件</small>':'')+'</div>';}
let attachmentObserver=null;const attachmentUrls=new Set();
$('#editor').addEventListener('close',()=>{if(state.tab==='intel')loadAttachmentImages();});
function loadAttachmentImages(){if(attachmentObserver)attachmentObserver.disconnect();attachmentObserver=new IntersectionObserver(entries=>{entries.forEach(async entry=>{if(!entry.isIntersecting)return;const img=entry.target;attachmentObserver.unobserve(img);try{const r=await fetch('/api/platform/files?object='+encodeURIComponent(img.dataset.intelImage),{headers:{'X-Admin-Password':state.password}});if(!r.ok)throw Error();if(!img.isConnected)return;const url=URL.createObjectURL(await r.blob());attachmentUrls.add(url);img.src=url;}catch{img.alt='图片暂时无法读取';}});},{rootMargin:'150px'});document.querySelectorAll('[data-intel-image]:not([src])').forEach(img=>attachmentObserver.observe(img));}
function displayIntelText(data){return String(data.content||'').replace(/\[CQ:(image|file),[^\]]*\]/g,'').trim();}
actions.intelDetail=async id=>{
 const r=await get('intel-items',id),m=r.data.metadata||{};
 details(r.data.title||'情报全文',displayIntelText(r.data));const root=$('#editor-fields');
 root.insertAdjacentHTML('beforeend','<h3>附件（'+intelAttachments(r.data).length+'）</h3>'+ (attachmentMarkup(r.data)||'<p class="meta">暂无附件</p>'));
 const sourceLinks=[m.url||m.note_url,...intelAttachments(r.data).map(a=>a.source_url)].filter(v=>{try{return ['http:','https:'].includes(new URL(v).protocol);}catch{return false;}});
 root.insertAdjacentHTML('beforeend','<details class="intel-provenance"><summary>来源信息</summary><p>来源：'+esc(label(r.data.source))+' · '+esc(r.data.source_id)+'</p>'+[...new Set(sourceLinks)].map((url,i)=>'<p><a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">原始来源 '+(i+1)+'</a></p>').join('')+'</details>');
 loadAttachmentImages();
};
actions.consumeIntel=()=>{const ids=Array.from(intelState.selected);if(!ids.length)throw Error('请先选择情报');form(`总结 ${ids.length} 条情报`,[field('instruction','处理要求','textarea',{default:'提取保研相关事实、关键时间、风险和来源，不编造信息。',required:true})],async v=>{await post('/intel/consume',{ids,...v});intelState.selected.clear();state.tab='tasks';nav();});};
actions.xhs=()=>form('小红书采集',[field('query','关键词','text',{required:true}),field('cookie','本人登录后取得的 Cookie','password',{required:true,help:'不要发送到聊天或提交到 Git'}),field('limit','条数','number',{default:10,min:1})],async v=>{await post('/intel/xhs-crawl',v);state.tab='tasks';nav();});actions.qq=()=>form('QQ 群消息监视',[field('groups','群号（逗号分隔）','text',{required:true}),field('restart_policy','重启策略','select',{options:['always','on-failure','none']})],async v=>{await post('/intel/qq-monitor',{group_ids:v.groups.split(/[,，]/).map(x=>x.trim()).filter(Boolean),restart_policy:v.restart_policy});state.tab='tasks';nav();});

actions.qq=async()=>{const login=await api('/napcat/webui');form('QQ 群消息监视',[field('groups','群号（逗号分隔）','text',{required:true}),field('restart_policy','重启策略','select',{options:['always','on-failure','none']})],async v=>{await post('/intel/qq-monitor',{group_ids:v.groups.split(/[,，]/).map(x=>x.trim()).filter(Boolean),restart_policy:v.restart_policy});state.tab='tasks';nav();});$('#editor-fields').insertAdjacentHTML('afterbegin',`<p><a href="${esc(login.url)}" target="_blank" rel="noopener">打开 NapCat 扫码登录页面</a></p><p class="meta">先扫码登录，再指定群号启动监视。</p>`);};
views.agent=async()=>{const status=await api('/integrations');show(status.agent.online?'<iframe class="agent-frame" src="/canvas" title="OpenHands 会话"></iframe>':`<section class="panel"><h3>Agent 尚未连接</h3><p>请检查 Agent 服务和模型配置。</p>${button('配置服务','goSettings')}</section>`);};actions.goSettings=()=>{state.tab='settings';nav();return render();};

views.settings=async()=>{const [cfg,status]=await Promise.all([api('/config'),api('/integrations')]);const sections={application:{title:'访问口令',fields:[field('admin-password','访问口令','password'),field('public-base-url','站点地址','url')]},llm:{title:'大模型',fields:[field('base-url','OpenAI 兼容 API 地址（通常以 /v1 结尾）','url'),field('model','模型名称'),field('api-key','API Key','password')]},smtp:{title:'邮箱草稿箱',fields:[field('from','发件邮箱','email'),field('imap-host','IMAP 地址'),field('imap-port','SSL 端口','number',{default:993}),field('username','账号'),field('password','授权码','password'),field('oauth-client-id','Microsoft 公共客户端 Client ID'),field('oauth-tenant','Microsoft 租户','text',{default:'common'}),field('access-token','Outlook OAuth Access Token','password'),field('draft-folder','草稿箱','text',{default:'Drafts'})]}};show(toolbar('服务配置（Nacos）',button('Outlook 设备授权','outlookAuth'))+`<section class="panel"><h3>实际连接状态</h3>${Object.entries(status).map(([name,s])=>badge(`${name}：${s.online===undefined?(s.configured?'已配置':'待配置'):(s.online?'在线':'离线')}`,s.online?'succeeded':'')).join(' ')}</section><div class="grid">${Object.entries(sections).map(([key,s])=>`<section class="panel"><h3>${s.title}</h3><p>密钥以 *** 显示，未修改时保留原值。</p>${button('编辑配置','config:'+key)}</section>`).join('')}</div>`);actions.config=section=>form(sections[section].title,sections[section].fields,async v=>{const result=await patch('/config',{section,value:v});if(section==='llm'&&result.agent_message)setTimeout(()=>toast(result.agent_message),100);if(section==='application'&&v['admin-password']&&v['admin-password']!=='***'){state.password=v['admin-password'];try{localStorage.setItem('baoyan-password',state.password);}catch{}}},cfg[section]||{});};
setInterval(()=>{if(state.password&&state.tab==='tasks'&&!$('#editor').open)render();},8000);
if(state.password){$('#login').hidden=true;$('#app').hidden=false;nav();render();}

actions.outlookAuth=async()=>{const auth=await post('/mail/oauth/device',{});details('Outlook 设备授权','');$('#editor-fields').innerHTML='<p>请由你本人打开 Microsoft 官方页面完成登录与授权：</p><p><a id="oauth-link" target="_blank" rel="noopener">打开 Microsoft 验证页面</a></p><p>输入设备代码：<strong id="oauth-code"></strong></p><p id="oauth-status">等待你完成授权…</p>';$('#oauth-link').href=auth.verification_uri;$('#oauth-code').textContent=auth.user_code;const end=Date.now()+auth.expires_in*1000;const timer=setInterval(async()=>{if(!$('#editor').open||Date.now()>end){clearInterval(timer);return;}try{const result=await post('/mail/oauth/device/'+auth.session_id,{});if(result.status==='authorized'){clearInterval(timer);$('#oauth-status').textContent='授权成功，刷新令牌已安全保存在本地 Nacos。';}}catch(e){clearInterval(timer);$('#oauth-status').textContent=e.message;}},Math.max(5,auth.interval)*1000);};
