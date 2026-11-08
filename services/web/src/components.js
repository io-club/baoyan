import {createApp,defineComponent,h,ref,onMounted,onBeforeUnmount,onUpdated,nextTick} from 'vue';
import {NConfigProvider,NButton,NInput,NInputNumber,NSelect,NCheckbox,NDatePicker,NUpload,NDataTable,NTag,NCard,NStatistic,NEmpty,NProgress,NFormItem,NModal,createDiscreteApi,zhCN,dateZhCN} from 'naive-ui';

export const theme={common:{primaryColor:'#2080f0',primaryColorHover:'#4098fc',primaryColorPressed:'#1060c9'}};
const config={locale:zhCN,dateLocale:dateZhCN,themeOverrides:theme};
const instances=new Map();let scheduled=false,observer;
const DomContent=defineComponent({props:['nodes'],setup(props){const root=ref();let current;const sync=()=>{if(current!==props.nodes){if(!current||current.length!==props.nodes.length||props.nodes.some((node,index)=>node!==current[index]))root.value.replaceChildren(...props.nodes);current=props.nodes;}};onMounted(sync);onUpdated(sync);return()=>h('div',{ref:root,class:'ui-content'});}});
const dom=nodes=>h(DomContent,{nodes:Array.isArray(nodes)?nodes:Array.from(nodes)});
function mount(host,render,dispose){
 const app=createApp({render:()=>h(NConfigProvider,config,{default:render})});
 app.mount(host);instances.set(host,{app,dispose});return host;
}
function eligible(el){return !el.dataset.uiSource&&!el.closest('[data-ui-control],#calendar-workspace,.agent-frame');}
function hostFor(source,kind){
 const host=document.createElement('span');host.className='ui-control ui-'+kind;host.dataset.uiControl=kind;
 source.before(host);source.dataset.uiSource=kind;return host;
}
function bridgeProperty(el,key,changed){
 let proto=Object.getPrototypeOf(el),descriptor;
 while(proto&&!descriptor){descriptor=Object.getOwnPropertyDescriptor(proto,key);proto=Object.getPrototypeOf(proto);}
 if(!descriptor?.set)return()=>{};
 Object.defineProperty(el,key,{configurable:true,get:()=>descriptor.get.call(el),set:value=>{descriptor.set.call(el,value);changed();}});
 return()=>delete el[key];
}
function titleFor(el){return (el.getAttribute('aria-label')||(el.id?document.querySelector('label[for="'+CSS.escape(el.id)+'"]')?.textContent?.trim():'')||el.closest('label')?.childNodes[0]?.textContent?.trim()||el.closest('.ui-form-item')?.querySelector('.n-form-item-label')?.textContent?.trim()||el.placeholder||el.name||'').replace(/\s*\*$/,'');}
function emit(el,event='change'){el.dispatchEvent(new Event(event,{bubbles:true}));}
function controls(scope){
 scope.querySelectorAll('button').forEach(el=>{
  if(!eligible(el))return;
  const host=hostFor(el,'button'),disabled=ref(el.disabled),text=ref(el.textContent.trim()),shown=ref(!el.hidden);
  const restore=bridgeProperty(el,'disabled',()=>disabled.value=el.disabled);
  const changes=new MutationObserver(()=>{disabled.value=el.disabled;text.value=el.textContent.trim();shown.value=!el.hidden;});changes.observe(el,{attributes:true,childList:true,subtree:true,characterData:true});
  const type=el.classList.contains('danger')?'error':el.id==='editor-save'||el.type==='submit'||(!el.classList.contains('secondary')&&el.hasAttribute('data-action'))?'primary':'default';
  mount(host,()=>shown.value?h(NButton,{type,disabled:disabled.value,size:el.closest('td')?'small':'medium',onClick:e=>{e.preventDefault();el.click();},'aria-label':el.getAttribute('aria-label')||text.value},{default:()=>text.value}):null,()=>{restore();changes.disconnect();});
 });
 scope.querySelectorAll('input,textarea,select').forEach(el=>{
  if(!eligible(el)||el.type==='hidden'||el.type==='color')return;
  const host=hostFor(el,'field'),required=el.required;el.required=false;
  const label=titleFor(el),value=ref(el.tagName==='SELECT'&&el.multiple?Array.from(el.selectedOptions,x=>x.value):el.type==='checkbox'?el.checked:el.value),disabled=ref(el.disabled),indeterminate=ref(el.indeterminate||false);
  const update=()=>{value.value=el.tagName==='SELECT'&&el.multiple?Array.from(el.selectedOptions,x=>x.value):el.type==='checkbox'?el.checked:el.value;};
  const restores=[bridgeProperty(el,el.type==='checkbox'?'checked':'value',update),bridgeProperty(el,'disabled',()=>disabled.value=el.disabled)];
  if(el.type==='checkbox')restores.push(bridgeProperty(el,'indeterminate',()=>indeterminate.value=el.indeterminate));
  const set=v=>{if(el.tagName==='SELECT'&&el.multiple){for(const o of el.options)o.selected=(v||[]).includes(o.value);}else if(el.type==='checkbox')el.checked=v;else el.value=v??'';update();emit(el,'input');emit(el);};
  const common={disabled:disabled.value,'aria-label':label};
  mount(host,()=>{
   common.disabled=disabled.value;
   if(el.tagName==='SELECT')return h(NSelect,{...common,value:value.value,multiple:el.multiple,filterable:el.options.length>8,options:Array.from(el.options,o=>({label:o.textContent,value:o.value,disabled:o.disabled})),placeholder:label,'onUpdate:value':set});
   if(el.type==='checkbox')return h(NCheckbox,{...common,checked:!!value.value,indeterminate:indeterminate.value,'onUpdate:checked':set});
   if(el.type==='number')return h(NInputNumber,{...common,value:value.value===''?null:Number(value.value),min:el.min===''?undefined:Number(el.min),max:el.max===''?undefined:Number(el.max),'onUpdate:value':set});
   if(['date','datetime-local','month'].includes(el.type)){
    const format=el.type==='datetime-local'?"yyyy-MM-dd'T'HH:mm":el.type==='month'?'yyyy-MM':'yyyy-MM-dd';
    return h(NDatePicker,{...common,type:el.type==='datetime-local'?'datetime':el.type,formattedValue:value.value||null,valueFormat:format,clearable:true,'onUpdate:formattedValue':set});
   }
   if(el.type==='file')return h(NUpload,{...common,defaultUpload:false,max:el.multiple?undefined:1,multiple:el.multiple,accept:el.accept||undefined,onChange:({fileList})=>{const transfer=new DataTransfer();for(const f of fileList)if(f.file)transfer.items.add(f.file);el.files=transfer.files;emit(el);}},{default:()=>h(NButton,null,{default:()=>el.multiple?'选择文件':'选择文件'})});
   return h(NInput,{...common,value:String(value.value??''),type:el.tagName==='TEXTAREA'?'textarea':el.type==='password'?'password':'text',showPasswordOn:el.type==='password'?'click':undefined,autosize:el.tagName==='TEXTAREA'?{minRows:4,maxRows:14}:undefined,placeholder:el.placeholder||label,inputProps:{required,...(['email','url'].includes(el.type)?{type:el.type}:{}),'aria-label':label},'onUpdate:value':set,onBlur:()=>el.dispatchEvent(new FocusEvent('blur'))});
  },()=>restores.forEach(restore=>restore()));
 });
}
function tables(scope){
 scope.querySelectorAll('.table-wrap').forEach(wrapper=>{
  if(wrapper.dataset.uiContainer)return;const table=wrapper.querySelector('table');if(!table)return;
  const headers=Array.from(table.tHead?.rows[0]?.cells||[]),data=Array.from(table.tBodies[0]?.rows||[]).filter(row=>!row.querySelector('[colspan]')).map((row,i)=>({key:row.dataset.rowKey||i,cells:Array.from(row.cells,cell=>Array.from(cell.childNodes)),snapshots:Array.from(row.cells,cell=>cell.innerHTML)}));
  const columns=headers.map((cell,index)=>({key:String(index),title:()=>dom(cell.childNodes.length?Array.from(cell.childNodes):[document.createTextNode(cell.textContent)]),render:row=>dom(row.cells[index]||[])}));
  // Keep references to header nodes: moving them retains existing click/change listeners.
  columns.forEach((column,index)=>{const nodes=Array.from(headers[index].childNodes);column.title=()=>dom(nodes);});
  wrapper.replaceChildren();wrapper.dataset.uiContainer='table';
  const currentRows=ref(data);
  mount(wrapper,()=>h(NDataTable,{columns,data:currentRows.value,rowKey:r=>r.key,bordered:true,scrollX:headers.length>=6?1150:headers.length>=4?780:undefined,singleLine:true},{empty:()=>h(NEmpty,{description:'暂无数据'})}));
  instances.get(wrapper).updateTable=nextTable=>{
   const focused=document.activeElement,action=focused?.closest('.ui-button')?.nextElementSibling?.dataset.action;
   const previous=new Map(currentRows.value.map(row=>[row.key,row]));
   currentRows.value=Array.from(nextTable.tBodies[0]?.rows||[]).filter(row=>!row.querySelector('[colspan]')).map((row,i)=>{
    const key=row.dataset.rowKey||i,old=previous.get(key),snapshots=Array.from(row.cells,cell=>cell.innerHTML);
    return {key,snapshots,cells:Array.from(row.cells,(cell,index)=>old?.snapshots[index]===snapshots[index]?old.cells[index]:Array.from(cell.childNodes))};
   });
   if(action)nextTick(()=>{if(!focused.isConnected&&document.activeElement===document.body){const source=Array.from(wrapper.querySelectorAll('button[data-action]')).find(button=>button.dataset.action===action);source?.previousElementSibling?.querySelector('button')?.focus({preventScroll:true});}});
  };
 });
}
function fields(scope){
 scope.querySelectorAll('label.field').forEach(label=>{
  if(label.dataset.uiContainer)return;
  const children=Array.from(label.childNodes),text=children.filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim(),nodes=children.filter(n=>n.nodeType!==Node.TEXT_NODE);
  const host=document.createElement('div');host.dataset.uiContainer='form-item';host.className='ui-form-item';label.replaceWith(host);
  mount(host,()=>h(NFormItem,{label:text,showFeedback:false,labelPlacement:'top'},{default:()=>dom(nodes)}));
 });
}
function cards(scope){
 scope.querySelectorAll('.panel,.card,.stat-card').forEach(panel=>{
  if(panel.dataset.uiContainer||panel.closest('#calendar-workspace'))return;
  panel.dataset.uiContainer='card';const host=document.createElement('div');host.className=panel.className;host.dataset.uiContainer='card';
  let render,update;
  if(panel.classList.contains('stat-card')){const caption=panel.querySelector('small')?.textContent,number=panel.querySelector('strong'),unit=number?.querySelector('span')?.textContent||'',value=number?.textContent.replace(unit,'')||'0';const numeric=ref(value);update=value=>numeric.value=value;render=()=>h(NCard,null,{default:()=>h(NStatistic,{label:caption,value:numeric.value},{suffix:()=>unit})});}
  else{const heading=Array.from(panel.children).find(el=>el.tagName==='H3');const title=heading?.textContent;heading?.remove();const nodes=Array.from(panel.childNodes);render=()=>h(NCard,{title},{default:()=>dom(nodes)});}
  panel.replaceWith(host);mount(host,render);if(update)instances.get(host).updateStatistic=update;
 });
}
function ornaments(scope){
 scope.querySelectorAll('.tag,.empty,progress').forEach(el=>{
  if(!eligible(el)||el.dataset.uiContainer)return;
  const host=document.createElement('span');host.dataset.uiControl='display';host.className='ui-display';el.replaceWith(host);
  if(el.tagName==='PROGRESS'){host.className='ui-progress';mount(host,()=>h(NProgress,{type:'line',percentage:Math.min(100,Number(el.value)||0),showIndicator:false}));}
  else if(el.classList.contains('empty')){host.className='ui-empty';mount(host,()=>h(NEmpty,{description:el.textContent}));}
  else{const type=el.classList.contains('succeeded')?'success':el.classList.contains('failed')?'error':el.classList.contains('running')?'info':'default';mount(host,()=>h(NTag,{type,size:'small',bordered:false},{default:()=>el.textContent}));}
 });
}
function sweep(){
 scheduled=false;
 for(const [node,instance]of instances)if(!node.isConnected){instance.app.unmount();instance.dispose?.();instances.delete(node);}
 for(const scope of [document.querySelector('#content'),document.querySelector('#editor-form'),document.querySelector('#login-form')]){
  if(!scope)continue;cards(scope);tables(scope);fields(scope);controls(scope);ornaments(scope);
 }
}
function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(sweep);}
function installModal(){
 const editor=document.querySelector('#editor'),form=document.querySelector('#editor-form'),title=ref(''),shown=ref(false),host=document.createElement('div');host.dataset.uiContainer='modal';document.body.append(host);
 editor.dataset.uiSource='dialog';
 const titleObserver=new MutationObserver(()=>title.value=document.querySelector('#editor-title')?.textContent||'');titleObserver.observe(document.querySelector('#editor-title'),{childList:true,subtree:true,characterData:true});
 editor.showModal=()=>{title.value=document.querySelector('#editor-title').textContent;editor.open=true;shown.value=true;};
 editor.close=()=>{if(!editor.open)return;editor.open=false;shown.value=false;editor.dispatchEvent(new Event('close'));};
 mount(host,()=>h(NModal,{show:shown.value,displayDirective:'show',preset:'card',title:title.value,style:'width:min(760px,94vw);max-height:90vh;overflow:auto','onUpdate:show':v=>{if(!v)editor.close();}},{default:()=>dom([form])}),()=>titleObserver.disconnect());
}
export function installComponents(){
 window.platformPatchTable=(host,table)=>{const update=instances.get(host)?.updateTable;if(!update)return false;update(table);return true;};
 window.platformPatchStats=items=>document.querySelectorAll('#content .stat-card').forEach((host,index)=>instances.get(host)?.updateStatistic?.(items[index]?.[1]??0));
 installModal();observer=new MutationObserver(schedule);observer.observe(document.body,{childList:true,subtree:true});schedule();
 const {message,dialog}=createDiscreteApi(['message','dialog'],{configProviderProps:config});window.platformMessage=text=>message.info(String(text),{duration:5000});
 window.platformConfirm=text=>new Promise(resolve=>dialog.warning({title:'确认操作',content:String(text),positiveText:'确定',negativeText:'取消',onPositiveClick:()=>{resolve(true);},onNegativeClick:()=>{resolve(false);},onAfterLeave:()=>resolve(false)}));
 return()=>{observer.disconnect();for(const instance of instances.values()){instance.app.unmount();instance.dispose?.();}instances.clear();};
}
