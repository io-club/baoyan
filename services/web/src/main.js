import {openMailComposer} from './outreach-compose.js';
window.platformOpenMailComposer=openMailComposer;
import {createApp,defineComponent,h,ref,onMounted,nextTick} from 'vue';
import {createRouter,createWebHashHistory,useRoute} from 'vue-router';
import {mountCalendar,unmountCalendar} from './calendar.js';
import {installComponents,theme} from './components.js';
window.platformMountCalendar=mountCalendar;
window.platformUnmountCalendar=unmountCalendar;
import {NConfigProvider,NLayout,NLayoutSider,NMenu,NButton,NPagination,zhCN,dateZhCN} from 'naive-ui';
const tabs=[['activities','保研日历'],['intel','情报工作台'],['advisors','导师库'],['outreach','套磁与草稿'],['materials','材料与口径'],['tasks','任务中心'],['agent','Agent'],['settings','设置']];
const router=createRouter({history:createWebHashHistory(),routes:[...tabs.map(([key])=>({path:'/'+key,name:key,component:{render:()=>null}})),{path:'/:pathMatch(.*)*',redirect:'/activities'}]});
const icons={activities:'M4 5h16v15H4z M8 3v4 M16 3v4 M4 10h16',intel:'M4 4h16v16H4z M8 8h8 M8 12h8 M8 16h4',advisors:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8',outreach:'M3 5h18v14H3z M3 6l9 7 9-7',materials:'M3 7h7l2-3h9v16H3z',tasks:'M9 6h12 M9 12h12 M9 18h12 M3 6h2 M3 12h2 M3 18h2',agent:'M4 4h16v13H9l-5 4z M8 9h8 M8 13h5',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 3v2 M12 19v2 M3 12h2 M19 12h2'};
let internal=false;
window.platformRoute=()=>router.currentRoute.value.name||'activities';
window.platformNavigate=async key=>{if(router.currentRoute.value.name===key)return;internal=true;try{await router.push('/'+key);}finally{internal=false;}};
router.afterEach(to=>{if(!internal)window.platformApplyRoute?.(to.name);});
const apps=new Map();
function hydratePagination(){
 for(const [node,instance] of apps)if(!node.isConnected){instance.app.unmount();apps.delete(node);}
 document.querySelectorAll('[data-naive-pagination]:not([data-mounted])').forEach(host=>{
  host.dataset.mounted='true';host.dataset.uiControl='pagination';const data=host.dataset,pagination=ref({page:Number(data.page),size:Number(data.size),total:Number(data.total)});
  const app=createApp({render:()=>h(NConfigProvider,{locale:zhCN,dateLocale:dateZhCN,themeOverrides:theme},{default:()=>h(NPagination,{page:pagination.value.page,pageSize:pagination.value.size,itemCount:pagination.value.total,showQuickJumper:true,pageSlot:5,
   'onUpdate:page':page=>{const [action,...args]=data.pageAction.split(':');window.platformDispatch?.(action,...args,String(page));}},{prefix:()=>`共 ${pagination.value.total} 条`})})});
  app.mount(host);apps.set(host,{app,update:value=>pagination.value=value});
 });
}
window.platformPatchPagination=(host,value)=>apps.get(host)?.update(value);
const App=defineComponent({setup(){const route=useRoute();const collapsed=ref(innerWidth<760);
 onMounted(async()=>{await nextTick();installComponents();new MutationObserver(hydratePagination).observe(document.querySelector('#content'),{childList:true,subtree:true});
  const script=document.createElement('script');script.src='/workspace.js?v=17';script.onerror=()=>{document.querySelector('#content').textContent='页面资源加载失败，请刷新重试。';};document.body.append(script);
 });
 return()=>h(NConfigProvider,{locale:zhCN,dateLocale:dateZhCN,themeOverrides:theme},{default:()=>h(NLayout,{hasSider:true,class:'app-layout'},{default:()=>[
  h(NLayoutSider,{width:184,collapsed:collapsed.value,collapsedWidth:56,collapseMode:'width',bordered:true,showTrigger:'bar','onUpdate:collapsed':v=>collapsed.value=v},{default:()=>[
   h('div',{class:'app-brand'},collapsed.value?'保研':'保研平台'),
   h(NMenu,{value:route.name,collapsed:collapsed.value,collapsedWidth:56,indent:16,options:tabs.map(([key,label])=>({key,icon:()=>h('svg',{viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':1.5},[h('path',{d:icons[key]})]),label:()=>h('span',{'data-tab':key},label)})),'onUpdate:value':key=>{if(window.platformApplyRoute)window.platformApplyRoute(key);else window.platformNavigate(key);}}),
   h('div',{class:'app-session'},[h(NButton,{quaternary:true,size:'small',onClick:()=>document.querySelector('#logout').click()},{default:()=>collapsed.value?'退出':'退出登录'})])
  ]}),
  h(NLayout,{class:['app-workspace',route.name==='agent'?'agent-layout':'']},{default:()=>[
   h('nav',{id:'nav',hidden:true}),h('span',{id:'page-name',hidden:true}),h('a',{id:'logout',hidden:true,href:'#'},'退出'),h('main',{id:'content'})
  ]})
 ]})});
}});
const app=createApp(App);app.use(router);router.isReady().then(()=>app.mount('#shell'));
