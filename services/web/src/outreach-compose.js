import {createApp,h,ref,watch,onMounted,onBeforeUnmount} from 'vue';
import {NConfigProvider,NModal,NFormItem,NSelect,NInput,NButton,NAlert,NSpace,NCollapse,NCollapseItem,zhCN,dateZhCN} from 'naive-ui';
import {theme} from './components.js';
export function openMailComposer({api,download,toast,onSaved,templateId=null,previewOnly=false}){
 const host=document.createElement('div');document.body.append(host);
 let app;
 app=createApp({setup(){
  const open=ref(true),templates=ref([]),materials=ref([]),advisors=ref([]),advisor=ref(null),template=ref(templateId),selectedAdvisor=ref(null),materialIds=ref([]),params=ref({}),subject=ref(null),content=ref(null),recipientName=ref(null),recipientEmail=ref(null),preview=ref(null),busy=ref(false),saving=ref(false),error=ref('');
  let timer,seq=0,searchSeq=0,searchText='',offset=0,total=0,loading=false,disposed=false;
  const post=(path,body)=>api(path,{method:'POST',body:JSON.stringify(body)});
  const payload=()=>({advisor_id:advisor.value||null,template_id:template.value||null,parameters:params.value,subject:subject.value,content:content.value,recipient_name:recipientName.value,recipient_email:recipientEmail.value,material_ids:materialIds.value});
  async function refresh(){const id=++seq;busy.value=true;error.value='';try{const result=await post('/mail/preview',payload());if(id===seq&&!disposed)preview.value=result;}catch(e){if(id===seq)error.value=e.message;}finally{if(id===seq)busy.value=false;}}
  function schedule(){clearTimeout(timer);++seq;busy.value=true;timer=setTimeout(refresh,220);}
  async function search(text='',append=false){if(append&&loading)return;const id=++searchSeq;loading=true;if(!append){searchText=text;offset=0;advisors.value=[];}try{const result=await api('/advisors?'+new URLSearchParams({q:searchText,limit:50,offset}));if(id!==searchSeq)return;advisors.value=append?[...advisors.value,...result.items]:result.items;offset+=result.items.length;total=result.total;}catch(e){error.value=e.message;}finally{if(id===searchSeq)loading=false;}}
  async function chooseAdvisor(id){advisor.value=id;selectedAdvisor.value=null;recipientName.value=null;recipientEmail.value=null;subject.value=null;content.value=null;preview.value=null;const current=id;if(id)try{const result=await api('/advisors/'+id);if(advisor.value===current)selectedAdvisor.value=result;}catch(e){error.value=e.message;}schedule();}
  function close(){open.value=false;}
  onMounted(async()=>{try{const [t,m]=await Promise.all([api('/entities/templates?limit=1000'),api('/entities/materials?limit=1000')]);templates.value=t.items;materials.value=m.items;await search();await refresh();}catch(e){error.value=e.message;}});
  onBeforeUnmount(()=>{disposed=true;++seq;clearTimeout(timer);});
  watch([subject,content,recipientName,recipientEmail,params],schedule,{deep:true});
  watch(template,()=>{subject.value=null;content.value=null;params.value={};preview.value=null;schedule();});
  async function save(){saving.value=true;error.value='';try{const result=await post('/mail/compose',payload());await download(result.object);toast(result.imap_error||(result.imap_saved?'草稿已保存到邮箱并下载':'邮件草稿已下载'));close();await onSaved?.();}catch(e){error.value=e.message;}finally{saving.value=false;}}
  const item=(label,node)=>h(NFormItem,{label},{default:()=>node});
  const input=(value,change,extra={})=>h(NInput,{value:value??'', 'onUpdate:value':change,...extra});
  return()=>h(NConfigProvider,{locale:zhCN,dateLocale:dateZhCN,themeOverrides:theme},{default:()=>h(NModal,{show:open.value,preset:'card',title:previewOnly?'模板预览':'生成邮件草稿',style:{width:'min(860px,94vw)'},'onUpdate:show':v=>open.value=v,onAfterLeave:()=>{app.unmount();host.remove();}},{default:()=>[
   item('导师',h(NSelect,{value:advisor.value,filterable:true,remote:true,clearable:true,placeholder:'搜索导师姓名、学校或方向',options:[...(selectedAdvisor.value&&!advisors.value.some(a=>a.id===selectedAdvisor.value.id)?[selectedAdvisor.value]:[]),...advisors.value].map(a=>({value:a.id,label:[a.name,a.school,a.department].filter(Boolean).join(' · ')})),onSearch:text=>search(text),'onUpdate:value':chooseAdvisor,onScroll:e=>{if(e.target.scrollTop+e.target.clientHeight>=e.target.scrollHeight-30&&offset<total)search('',true);}})),
   item('邮件模板',h(NSelect,{value:template.value,clearable:true,options:templates.value.map(t=>({value:t.id,label:t.data.name})),'onUpdate:value':v=>template.value=v,placeholder:'选择模板，或直接填写主题和正文'})),
   item('收件人姓名',input(recipientName.value??preview.value?.recipient_name,v=>recipientName.value=v,{placeholder:'选择导师后自动填写'})),
   item('收件邮箱',input(recipientEmail.value??preview.value?.recipient_email,v=>recipientEmail.value=v,{placeholder:'选择导师后自动填写'})),
   ...((preview.value?.variables||[]).some(v=>v.automatic)?[h(NCollapse,null,{default:()=>h(NCollapseItem,{title:'已自动带入导师信息',name:'advisor'},{default:()=>h('dl',{},preview.value.variables.filter(v=>v.automatic).flatMap(v=>[h('dt',{},v.name),h('dd',{},v.display||'导师库尚未填写此信息')]))})})]:[]),
   ...(preview.value?.variables||[]).filter(v=>!v.automatic).map(v=>item('模板参数 · '+v.name,input(params.value[v.name]??v.display,text=>params.value={...params.value,[v.name]:text}))),
   item('邮件主题',input(subject.value??preview.value?.subject,v=>subject.value=v,{placeholder:'模板可包含主题及导师变量'})),
   item('邮件正文',input(content.value??preview.value?.content,v=>content.value=v,{type:'textarea',autosize:{minRows:10,maxRows:22},placeholder:'正文支持 {{name}}、{{school}}、{{research_directions}} 等变量'})),
   !previewOnly?item('附件材料',h(NSelect,{value:materialIds.value,multiple:true,clearable:true,options:materials.value.map(m=>({value:m.id,label:m.data.name})),'onUpdate:value':v=>materialIds.value=v})):null,
   preview.value?.missing?.length?h(NAlert,{type:'warning',style:{marginBottom:'12px'}},{default:()=>`尚缺信息：${preview.value.missing.join('、')}。导师字段请先在导师库补全。`}):null,
   preview.value?.errors?.length?h(NAlert,{type:'warning',style:{marginBottom:'12px'}},{default:()=>preview.value.errors.join('；')}):null,
   error.value?h(NAlert,{type:'error'},{default:()=>error.value}):null
  ],footer:()=>h(NSpace,{justify:'end'},{default:()=>[h(NButton,{onClick:close},{default:()=>previewOnly?'关闭':'取消'}),!previewOnly?h(NButton,{type:'primary',loading:saving.value,disabled:busy.value||!preview.value||!!preview.value.missing.length||!!preview.value.errors.length,onClick:save},{default:()=> '生成并下载草稿'}):null]})})});
 }});app.mount(host);
}
