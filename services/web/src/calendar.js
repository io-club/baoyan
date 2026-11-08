import {theme} from './components.js';
import {createApp,h,ref,computed,onMounted,onBeforeUnmount} from 'vue';
import {NConfigProvider,NButton,NCard,NTag,NSelect,NInput,NSwitch,NDrawer,NDrawerContent,NModal,NPagination,NEmpty,NSpin,NFormItem,NCheckbox,NColorPicker,NDatePicker,NSpace,zhCN,dateZhCN} from 'naive-ui';

const labels={registration_start:'报名开始',deadline:'报名截止',activity_start:'活动开始'};
const colors={registration_start:'success',deadline:'warning',activity_start:'info'};
const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const fmt=v=>v?String(v).replace('T',' ').slice(0,16):'未提供';
const safe=v=>{try{const u=new URL(v);return ['http:','https:'].includes(u.protocol)?u.href:'';}catch{return '';}};
let active;
export function unmountCalendar(){active?.unmount();active=null;}
export function mountCalendar(host,{api,dispatch}){
 unmountCalendar();
 active=createApp({setup(){
  let saved={};try{saved=JSON.parse(sessionStorage.getItem('baoyan-calendar-state')||'{}');}catch{}
  const month=ref(saved.month||iso(new Date()).slice(0,7)),kinds=ref(saved.kinds?.length?saved.kinds:['deadline']),q=ref(saved.q||''),selectedTags=ref(saved.tags||[]);
  const cal=ref({items:[],day_counts:{},total:0,activity_count:0}),tags=ref([]),settings=ref({show_untagged:true,countdown_untagged:false}),countdowns=ref({items:[],total:0}),countPage=ref(1);
  const busy=ref(false),error=ref(''),day=ref(''),dayPage=ref(1),dayData=ref({items:[],total:0}),dayBusy=ref(false),detail=ref(null),tagModal=ref(false),editModal=ref(false),edit=ref({}),editingId=ref(''),newTag=ref(''),saving=ref(false),detailTags=ref([]);
  const reminderModal=ref(false),rules=ref([]),notices=ref([]);
  let revision=0,dayRevision=0,disposed=false,searchTimer;
  const totalDays=computed(()=>{const [y,m]=month.value.split('-').map(Number);return new Date(y,m,0).getDate();});
  const monthTitle=computed(()=>`${Number(month.value.slice(0,4))} 年 ${Number(month.value.slice(5))} 月`);
  const options=computed(()=>tags.value.map(t=>({label:t.data.name,value:t.id}))),tagById=computed(()=>Object.fromEntries(tags.value.map(t=>[t.id,t.data])));
  const persist=()=>sessionStorage.setItem('baoyan-calendar-state',JSON.stringify({month:month.value,kinds:kinds.value,q:q.value,tags:selectedTags.value}));
  async function run(fn){error.value='';try{return await fn();}catch(e){if(!disposed)error.value=e.message;}}
  async function load(){const ticket=++revision;busy.value=true;persist();await run(async()=>{
    const query=new URLSearchParams({start:month.value+'-01',end:month.value+'-'+totalDays.value,per_day:3,event_types:kinds.value.join(','),q:q.value,tag_ids:selectedTags.value.join(',')});
    const [c,t,s,counts,r,n]=await Promise.all([api('/calendar?'+query),api('/entities/tags?limit=1000'),api('/calendar-settings'),api('/calendar-countdowns?limit=5&offset='+((countPage.value-1)*5)),api('/entities/reminders?limit=1000'),api('/entities/notifications?limit=20')]);
    if(ticket!==revision||disposed)return;cal.value=c;tags.value=t.items;settings.value=s;countdowns.value=counts;rules.value=r.items;notices.value=n.items.filter(x=>!x.data.read);
  });if(ticket===revision)busy.value=false;}
  async function loadDay(){if(!day.value)return;const ticket=++dayRevision;dayBusy.value=true;await run(async()=>{
    const result=await api('/calendar?'+new URLSearchParams({start:day.value,end:day.value,limit:10,offset:(dayPage.value-1)*10,group_activities:true,event_types:kinds.value.join(','),q:q.value,tag_ids:selectedTags.value.join(',')}));
    if(ticket===dayRevision&&!disposed)dayData.value=result;
  });if(ticket===dayRevision)dayBusy.value=false;}
  async function openDay(value){day.value=value;dayPage.value=1;dayData.value={items:[],total:0};await loadDay();}
  async function openDetail(item){await run(async()=>{const [a,links]=await Promise.all([api('/entities/activities/'+item.id),api('/relations/activity-tags/'+item.id)]);detail.value=a;detailTags.value=[...new Set([...links.map(t=>t.tag_id),...(Array.isArray(a.data.tags)?a.data.tags.filter(t=>tagById.value[t]):[])])];});}
  async function saveDetailTags(value){await run(async()=>{await api('/relations/activity-tags/'+detail.value.id,{method:'PUT',body:JSON.stringify({tag_ids:value})});detailTags.value=value;await load();await loadDay();});}
  async function saveTag(t,patch){await run(async()=>{await api('/entities/tags/'+t.id,{method:'PATCH',body:JSON.stringify(patch)});Object.assign(t.data,patch);await load();await loadDay();});}
  async function saveSettings(patch){await run(async()=>{settings.value=await api('/calendar-settings',{method:'PUT',body:JSON.stringify({...settings.value,...patch})});await load();await loadDay();});}
  function move(step){const [y,m]=month.value.split('-').map(Number);month.value=iso(new Date(y,m-1+step,1)).slice(0,7);load();}
  function editActivity(row){editingId.value=row?.id||'';const d=row?.data||{},raw=d.raw||{};edit.value={title:d.title||'',school:d.school||'',college:d.college||'',registration_start:String(d.registration_start||raw.sign_up_start||'').replaceAll('/','-').slice(0,10),deadline:String(d.deadline||'').slice(0,10),activity_start:String(d.activity_start||raw.start_time||'').replaceAll('/','-').slice(0,10),source_url:d.source_url||raw.office_url||raw.gzh_url||'',notes:d.notes||'',tags:row?detailTags.value:[]};editModal.value=true;}
  async function saveActivity(){saving.value=true;await run(async()=>{if(!edit.value.title.trim())throw Error('请填写活动标题');const {tags:chosen,...data}=edit.value;
    for(const k of ['registration_start','deadline','activity_start'])data[k]=data[k]||null;
    const row=await api('/entities/activities'+(editingId.value?'/'+editingId.value:''),{method:editingId.value?'PATCH':'POST',body:JSON.stringify(data)});
    await api('/relations/activity-tags/'+row.id,{method:'PUT',body:JSON.stringify({tag_ids:chosen})});editModal.value=false;if(detail.value?.id===row.id){detail.value=row;detailTags.value=chosen;}await load();await loadDay();
  });saving.value=false;}
  const btn=(text,onClick,props={})=>h(NButton,{onClick,...props},{default:()=>text});
  const tag=(text,type='default')=>h(NTag,{size:'small',bordered:false,type},{default:()=>text});
  const tagsFor=item=>(item.tags||[]).map(t=>h(NTag,{size:'small',bordered:false,color:{color:(t.color||'#2080f0')+'15',textColor:t.color||'#2080f0'}},{default:()=>t.name}));
  const source=row=>safe(row.data.source_url||row.data.raw?.office_url||row.data.raw?.gzh_url||row.data.raw?.sign_up_url);
  onMounted(load);onBeforeUnmount(()=>{disposed=true;clearTimeout(searchTimer);});
  return()=>h(NConfigProvider,{locale:zhCN,dateLocale:dateZhCN,themeOverrides:theme}, {default:()=>h('div',{class:'calendar-workbench','aria-busy':busy.value},[
   h('div',{class:'calendar-heading'},[h('div',[h('h2','保研日历'),h('p','按实际时间节点安排申请，不在整个活动区间重复铺开。')]),h(NSpace,null,{default:()=>[btn('标签与展示',()=>tagModal.value=true),btn('提醒规则',()=>reminderModal.value=true),btn('采集活动',()=>dispatch('crawlActivity')),btn('新增活动',()=>editActivity(),{type:'primary'})]})]),
   error.value?h('div',{class:'calendar-error',role:'alert'},error.value):null,
   notices.value.length?h(NCard,{size:'small',class:'calendar-notifications'},{default:()=>notices.value.map(n=>h('div',{class:'calendar-notice'},[h('span',n.data.message),btn('已读',()=>run(async()=>{await api('/entities/notifications/'+n.id,{method:'PATCH',body:JSON.stringify({read:true})});await load();}),{text:true,size:'small'})]))}):null,
   h('div',{class:'calendar-controls'},[
    h(NSpace,{align:'center'},{default:()=>[btn('‹',()=>move(-1),{'aria-label':'上一月'}),h('strong',monthTitle.value),btn('›',()=>move(1),{'aria-label':'下一月'}),btn('本月',()=>{month.value=iso(new Date()).slice(0,7);load();}),h(NDatePicker,{type:'month',formattedValue:month.value,valueFormat:'yyyy-MM','onUpdate:formattedValue':v=>{if(v){month.value=v;load();}},clearable:false,style:'width:130px'})]}),
    h(NSelect,{multiple:true,value:kinds.value,options:Object.entries(labels).map(([value,label])=>({value,label})),placeholder:'展示时间节点',style:'min-width:280px;flex:1','aria-label':'展示时间节点','onUpdate:value':v=>{if(v.length){kinds.value=v;load();}}}),
    h(NSelect,{multiple:true,clearable:true,value:selectedTags.value,options:options.value,placeholder:'筛选标签',style:'width:180px','onUpdate:value':v=>{selectedTags.value=v;load();}}),
    h(NInput,{value:q.value,placeholder:'搜索活动、学校',clearable:true,style:'width:190px','onUpdate:value':v=>{q.value=v;clearTimeout(searchTimer);searchTimer=setTimeout(load,350);}})
   ]),
   h('div',{class:'calendar-columns'},[
    h(NSpin,{show:busy.value},{default:()=>h(NCard,{contentStyle:'padding:0',class:'month-card'}, {default:()=>[
     h('div',{class:'month-summary'},[h('span',`${cal.value.activity_count} 项活动 · ${cal.value.total} 个时间节点`),h('span','点击日期查看当天活动')]),
     h('div',{class:'milestone-grid'},[
      ...['一','二','三','四','五','六','日'].map(d=>h('div',{class:'milestone-weekday'},d)),
      ...Array.from({length:(new Date(month.value+'-01T12:00:00').getDay()+6)%7},()=>h('div',{class:'milestone-day is-empty'})),
      ...Array.from({length:totalDays.value},(_,i)=>{const value=month.value+'-'+String(i+1).padStart(2,'0'),items=cal.value.items.filter(e=>e.date===value),n=cal.value.day_counts[value]||0;
       return h('div',{class:['milestone-day',value===iso(new Date())?'is-today':'']},[
        h('button',{class:'day-number',onClick:()=>openDay(value),'aria-label':value+' 当天活动'},i+1),
        ...items.map(item=>h('button',{class:['milestone-event','node-'+item.event_type],onClick:()=>openDetail(item)},[h('span',{class:'node-label'},labels[item.event_type]),h('span',{class:'event-title'},item.data.title)])),
        n>3?btn('查看全部 '+(cal.value.day_activity_counts?.[value]||n)+' 项活动',()=>openDay(value),{text:true,size:'tiny',class:'day-more'}):null
       ]);
      })
     ])
    ]})}),
    h('aside',{class:'calendar-side'},[h(NCard,{title:'重点倒计时',size:'small'}, {headerExtra:()=>btn('设置',()=>tagModal.value=true,{text:true,size:'small'}),default:()=>[
     ...countdowns.value.items.map(item=>h('button',{class:'countdown-item',onClick:()=>openDetail(item)},[h('div',{class:'countdown-days'},[h('strong',Math.max(0,Math.ceil(item.seconds_remaining/86400))),h('span','天')]),h('div',[h('strong',item.data.title),h('p',item.data.school||''),h('small','报名截止 '+fmt(item.data.deadline)),h('div',{class:'event-tags'},tagsFor(item))])])),
     !countdowns.value.items.length?h(NEmpty,{description:'暂无重点活动'},{extra:()=>h('small','在「标签与展示」中开启重点倒计时')}):null,
     countdowns.value.total>5?h(NPagination,{page:countPage.value,pageSize:5,itemCount:countdowns.value.total,simple:true,'onUpdate:page':v=>{countPage.value=v;load();}}):null
    ]}),h('div',{class:'calendar-legend'},Object.entries(labels).map(([key,name])=>h('span',[h('i',{class:'legend-dot node-'+key}),name])))])
   ]),
   h(NDrawer,{show:!!day.value,width:'min(520px,100vw)','onUpdate:show':v=>{if(!v)day.value='';}},{default:()=>h(NDrawerContent,{title:day.value+' · 当天活动',closable:true},{default:()=>h(NSpin,{show:dayBusy.value},{default:()=>[
    h('p',{class:'day-overview-count'},`共 ${dayData.value.total} 项活动，仅包含所选时间节点`),
    ...dayData.value.items.map(item=>h(NCard,{size:'small',class:'day-activity-card',hoverable:true,onClick:()=>openDetail(item)},{default:()=>[h('h3',item.data.title),h('p',`${item.data.school||''} ${item.data.college||''}`),h(NSpace,{size:6},{default:()=>(item.events||[]).map(e=>tag(labels[e.event_type]+' '+fmt(e.event_at),colors[e.event_type]))}),h('div',{class:'event-tags'},tagsFor(item))]})),
    !dayData.value.items.length?h(NEmpty,{description:'当天没有符合条件的活动'}):null
   ]}),footer:()=>h(NPagination,{page:dayPage.value,pageSize:10,itemCount:dayData.value.total,showQuickJumper:true,'onUpdate:page':v=>{dayPage.value=v;loadDay();}})})}),
   h(NDrawer,{show:!!detail.value,width:'min(640px,100vw)','onUpdate:show':v=>{if(!v)detail.value=null;}},{default:()=>h(NDrawerContent,{title:'活动详情',closable:true},{default:()=>detail.value?[
    h('h2',{class:'activity-detail-title'},detail.value.data.title),h('p',{class:'detail-school'},`${detail.value.data.school||''} ${detail.value.data.college||''}`),
    h('div',{class:'activity-milestones'},Object.entries(labels).map(([key,name])=>{const raw=detail.value.data.raw||{},value=detail.value.data[key]||raw[{registration_start:'sign_up_start',deadline:'sign_up_end',activity_start:'start_time'}[key]];return h('div',[tag(name,colors[key]),h('strong',fmt(value))]);})),
    h(NFormItem,{label:'活动标签'},{default:()=>h(NSelect,{multiple:true,value:detailTags.value,options:options.value,placeholder:'选择标签，自动保存','onUpdate:value':saveDetailTags})}),
    btn('管理标签与展示规则',()=>tagModal.value=true,{text:true,type:'primary'}),
    h('section',{class:'activity-notes'},[h('h3','个人备注'),h('p',detail.value.data.notes||'暂无备注')]),
    source(detail.value)?h('a',{href:source(detail.value),target:'_blank',rel:'noopener',class:'activity-source'},'查看原始通知 ↗'):null
   ]:null,footer:()=>h(NSpace,{justify:'end'},{default:()=>[btn('编辑活动',()=>editActivity(detail.value)),btn('关闭',()=>detail.value=null)]})})}),
   h(NModal,{show:reminderModal.value,preset:'card',title:'截止提醒规则',style:'width:min(620px,94vw)','onUpdate:show':v=>reminderModal.value=v},{default:()=>[
    ...rules.value.map(r=>h('div',{class:'reminder-rule-row'},[h('div',[h('strong',r.data.name),h('p',`报名截止前 ${r.data.days_before} 天提醒`)]),h(NSwitch,{value:!!r.data.enabled,'onUpdate:value':v=>run(async()=>{await api('/entities/reminders/'+r.id,{method:'PATCH',body:JSON.stringify({enabled:v})});await load();})}),btn('删除',async()=>{if(await window.platformConfirm('删除这条提醒规则？'))run(async()=>{await api('/entities/reminders/'+r.id,{method:'DELETE'});await load();});},{text:true,type:'error'})])),
    !rules.value.length?h(NEmpty,{description:'尚未设置截止提醒'}):null,
    btn('新增提醒规则',()=>{reminderModal.value=false;dispatch('newReminder');},{type:'primary'})
   ]}),
   h(NModal,{show:tagModal.value,preset:'card',title:'标签与展示',style:'width:min(820px,94vw)','onUpdate:show':v=>tagModal.value=v},{default:()=>[
    error.value?h('div',{class:'calendar-error'},error.value):null,
    h('p',{class:'tag-manager-help'},'控制哪些活动进入日历、哪些单独列为重点倒计时。多个标签中有一个开启，对应活动就会显示。'),
    h('div',{class:'tag-manager-head'},[h('span','标签'),h('span','日历显示'),h('span','重点倒计时'),h('span','操作')]),
    ...tags.value.map(t=>h('div',{class:'tag-manager-row'},[
     h('div',{class:'tag-name-editor'},[h(NColorPicker,{value:t.data.color||'#2080f0',showAlpha:false,modes:['hex'],style:'width:32px;flex:none',renderLabel:()=>'',onComplete:v=>saveTag(t,{color:v}),'onUpdate:value':v=>t.data.color=v,'aria-label':t.data.name+'颜色'}),h(NInput,{value:t.data.name,'aria-label':'标签名称','onUpdate:value':v=>t.data.name=v,onBlur:()=>t.data.name.trim()?saveTag(t,{name:t.data.name.trim()}):load()})]),
     h(NSwitch,{value:t.data.show_calendar!==false,'aria-label':t.data.name+'日历显示','onUpdate:value':v=>saveTag(t,{show_calendar:v})}),
     h(NSwitch,{value:t.data.show_countdown===true,'aria-label':t.data.name+'重点倒计时','onUpdate:value':v=>saveTag(t,{show_countdown:v})}),
     btn('删除',async()=>{if(await window.platformConfirm('删除标签「'+t.data.name+'」？活动本身会保留。'))run(async()=>{await api('/entities/tags/'+t.id,{method:'DELETE'});selectedTags.value=selectedTags.value.filter(x=>x!==t.id);detailTags.value=detailTags.value.filter(x=>x!==t.id);await load();await loadDay();});},{text:true,type:'error',size:'small'})
    ])),
    h('div',{class:'tag-manager-row untagged-row'},[h('strong','无标签活动'),h(NSwitch,{value:settings.value.show_untagged,'aria-label':'无标签活动日历显示','onUpdate:value':v=>saveSettings({show_untagged:v})}),h(NSwitch,{value:settings.value.countdown_untagged,'aria-label':'无标签活动重点倒计时','onUpdate:value':v=>saveSettings({countdown_untagged:v})}),h('small','单独设置')]),
    h('div',{class:'new-tag-row'},[h(NInput,{value:newTag.value,placeholder:'新标签名称','onUpdate:value':v=>newTag.value=v}),btn('添加标签',()=>run(async()=>{if(!newTag.value.trim())throw Error('请输入标签名称');await api('/entities/tags',{method:'POST',body:JSON.stringify({name:newTag.value.trim(),color:'#2080f0',show_calendar:true,show_countdown:false})});newTag.value='';await load();}),{type:'primary'})])
   ]}),
   h(NModal,{show:editModal.value,preset:'card',title:editingId.value?'编辑活动':'新增活动',style:'width:min(680px,94vw)','onUpdate:show':v=>editModal.value=v},{default:()=>[
    ...[['title','活动标题'],['school','学校'],['college','学院'],['registration_start','报名开始'],['deadline','报名截止'],['activity_start','活动开始'],['source_url','来源链接'],['notes','个人备注']].map(([key,name])=>h(NFormItem,{label:name},{default:()=>h(NInput,{value:edit.value[key],type:key==='notes'?'textarea':'text',placeholder:['registration_start','deadline','activity_start'].includes(key)?'YYYY-MM-DD 或 ISO 时间':name,'onUpdate:value':v=>edit.value[key]=v})})),
    h(NFormItem,{label:'活动标签'},{default:()=>h(NSelect,{multiple:true,value:edit.value.tags,options:options.value,'onUpdate:value':v=>edit.value.tags=v})}),
    error.value?h('p',{class:'calendar-error'},error.value):null
   ],footer:()=>h(NSpace,{justify:'end'},{default:()=>[btn('取消',()=>editModal.value=false),btn('保存',saveActivity,{type:'primary',loading:saving.value})]})})
  ])});
 }});active.mount(host);
}
