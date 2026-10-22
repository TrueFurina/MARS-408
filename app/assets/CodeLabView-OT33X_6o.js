import{a as X,r as b,S as Y,j as a,b as n,g as e,t as i,u as q,F as j,h as T,i as $,f as E,L as K,m as U,v as D,c as M,y as G,z as le,U as ae,E as ne}from"./vue-vendor-BnleL1jK.js";import{S as ie,e as re,a as ue}from"./sourceLabExercises-D-e1iF10.js";import{c as Q}from"./index-DgOkINju.js";const de=9e4;let S=null,z=null,k=null,ce=0;function N(){const c=globalThis.isSecureContext===!0,s=globalThis.crossOriginIsolated===!0,r=typeof window<"u"&&window.self!==window.top;return s?{ready:!0,secureContext:c,isolated:s,embedded:r,message:""}:c?r?{ready:!1,secureContext:c,isolated:s,embedded:r,message:"当前实验室位于未隔离的嵌入式预览中，请在独立窗口运行 WASM 编译器。"}:{ready:!1,secureContext:c,isolated:s,embedded:r,message:"当前部署未启用 COOP/COEP 跨源隔离，请检查前端服务器或反向代理响应头。"}:{ready:!1,secureContext:c,isolated:s,embedded:r,message:"当前地址不是安全上下文，请通过 HTTPS、localhost 或 127.0.0.1 访问实验室。"}}function H(c=null){S?.terminate(),S=null,z=null,k&&(clearTimeout(k.timeout),c&&k.reject(c),k=null)}function ve(c){return S&&z===c||(S?.terminate(),S=c==="cpp"?new Worker(new URL("/MARS-408/app/assets/cppCompiler.worker-Bsj1GwvQ.js",import.meta.url),{type:"module"}):new Worker(new URL("/MARS-408/app/assets/cCompiler.worker-AfvyV6_I.js",import.meta.url),{type:"module"}),z=c,S.addEventListener("message",s=>{if(!k||s.data?.id!==k.id)return;if(s.data.type==="progress"){k.onProgress?.(s.data.stage);return}clearTimeout(k.timeout);const r=k;k=null,s.data.type==="result"?r.resolve(s.data.result):r.reject(new Error(s.data.message||"浏览器编译器执行失败"))}),S.addEventListener("error",s=>{H(new Error(s.message||"浏览器编译器 Worker 异常"))})),S}function Z(c,s,r="",f={}){if(!["c","cpp"].includes(c))return Promise.reject(new Error(`不支持的本地编译语言：${c}`));const y=N();if(!y.ready)return Promise.reject(new Error(y.message));if(k)return Promise.reject(new Error("已有编译任务正在运行"));const v=Math.max(5e3,Math.min(18e4,f.timeoutMs||de)),l=`compile-${Date.now()}-${++ce}`;return new Promise((p,_)=>{const x=setTimeout(()=>{H(new Error(`编译运行超过 ${Math.round(v/1e3)} 秒，任务已终止`))},v);k={id:l,resolve:p,reject:_,timeout:x,onProgress:f.onProgress},ve(c).postMessage({id:l,language:c,source:s,stdin:r})})}function ee(c,s="",r={}){return Z("c",c,s,r)}function pe(c,s="",r={}){return Z("cpp",c,s,r)}function V(){return k?(H(new Error("编译任务已取消")),!0):!1}function te(){return!!k}const me={class:"source-lab-workspace"},fe={class:"source-browser"},be={class:"browser-heading"},_e={class:"source-list"},he=["aria-selected","onClick"],ye={class:"source-path"},xe={class:"source-title"},ge={key:0,class:"completed-mark"},ke=["href"],Ce={class:"editor-panel"},we={class:"sandbox-toolbar"},$e={class:"sandbox-title"},Ee={class:"sandbox-actions"},Se={class:"lang-switch","aria-label":"代码视图"},Le=["aria-selected","disabled"],Pe=["aria-selected","disabled"],Me=["disabled"],je=["disabled"],Oe={key:0,class:"source-viewer"},Ae={key:1,class:"editor-wrap"},Re={key:0,class:"editor-placeholder"},Ie=["disabled"],Te={class:"terminal-panel"},Ue={class:"sandbox-toolbar",style:{"border-top":"1px solid var(--border-light)","border-bottom":"none"}},Ve={key:0,class:"sandbox-title"},We={key:1,class:"sandbox-title"},Be={class:"sandbox-output"},Fe={key:0,class:"output-placeholder"},qe={class:"learning-panel"},De={class:"topic-heading"},ze={class:"topic-chapter"},Ne={class:"topic-summary"},He={class:"learning-block"},Ge={class:"learning-block"},Je={class:"learning-block"},Xe={class:"concept-list"},Ye={class:"source-note"},J="mangdehenzhi_sourcelab_progress_v1",Ke=X({__name:"SourceLabPane",setup(c){const s=ie,r=s[0],f=b(r?r.id:""),y=b("source"),v=b(""),l=b(""),p=b(!1),_=b(""),x=b(null),A=N();function W(){try{const d=localStorage.getItem(J);if(d){const u=JSON.parse(d);return{completed:Array.isArray(u.completed)?u.completed:[],attempts:u.attempts&&typeof u.attempts=="object"?u.attempts:{}}}}catch{}return{completed:[],attempts:{}}}const C=b(W());function P(){try{localStorage.setItem(J,JSON.stringify(C.value))}catch{}}const m=M(()=>ue[f.value]),O=M(()=>new Set(C.value.completed)),R=M(()=>O.value.has(f.value)),I=M(()=>C.value.attempts[f.value]||0),B=M(()=>C.value.completed.length);function F(d){f.value=d,y.value="source",v.value="",l.value="",x.value=null}function g(d){p.value||(y.value=d,l.value="",x.value=null)}function t(){const d=m.value;if(d)try{navigator.clipboard?.writeText(d.source_excerpt)}catch{}}function w(){const d=m.value;d&&(v.value=d.experiment.starter_code,l.value="",x.value=null)}function h(d){return d<1e3?`${d} ms`:`${(d/1e3).toFixed(1)} s`}async function se(){const d=m.value;if(p.value||!d||!v.value.trim())return;if(!A.ready){l.value=A.message||"浏览器编译环境未就绪";return}p.value=!0,l.value="",x.value=null,_.value="";const u=o=>{const L={runtime:"正在初始化 WASM 运行时...",toolchain:"正在加载编译工具链...",compile:"正在编译...",run:"正在运行程序..."};_.value=L[o]||o};try{const o=await ee(v.value,d.experiment.stdin,{onProgress:u});x.value=o,C.value.attempts[d.id]=(C.value.attempts[d.id]||0)+1;const L=[];o.stdout&&L.push(o.stdout),o.stderr&&L.push(o.stderr),l.value=L.join(`
`)||"(无输出)",re(d,o.stage,o.code,o.stdout)?O.value.has(d.id)||(C.value.completed.push(d.id),l.value+=`

 实验通过：输出符合预期！`):o.stage==="run"&&(l.value+=`

 未通过：请对照「实验目标」检查输出。`),P()}catch(o){l.value=String(o?.message||o)}finally{p.value=!1,_.value=""}}function oe(){V(),p.value=!1,_.value="",l.value+=`
[任务已终止]`}return Y(()=>{te()&&V()}),(d,u)=>(a(),n("div",me,[e("aside",fe,[e("div",be,[u[3]||(u[3]=e("strong",null,"linux-0.11",-1)),e("small",null,"精选源码 · "+i(B.value)+"/"+i(q(s).length)+" 完成",1)]),e("div",_e,[(a(!0),n(j,null,T(q(s),o=>(a(),n("button",{key:o.id,type:"button",class:$({active:o.id===f.value}),"aria-selected":o.id===f.value,onClick:L=>F(o.id)},[e("span",ye,i(o.path),1),e("span",xe,i(o.title),1),O.value.has(o.id)?(a(),n("span",ge)):E("",!0)],10,he))),128))]),e("a",{class:"archive-link",href:m.value?.source_url,target:"_blank",rel:"noopener noreferrer"}," kernel.org 历史归档 ↗ ",8,ke)]),e("section",Ce,[e("div",we,[e("span",$e,[K(i(m.value?.path)+" ",1),e("small",null,"L"+i(m.value?.source_lines),1)]),e("div",Ee,[e("div",Se,[e("button",{type:"button",class:$({active:y.value==="source"}),"aria-selected":y.value==="source",disabled:p.value,onClick:u[0]||(u[0]=o=>g("source"))},"原始源码",10,Le),e("button",{type:"button",class:$({active:y.value==="experiment"}),"aria-selected":y.value==="experiment",disabled:p.value,onClick:u[1]||(u[1]=o=>g("experiment"))},"可运行实验",10,Pe)]),y.value==="source"?(a(),n("button",{key:0,class:"sandbox-btn",onClick:t},"复制")):(a(),n(j,{key:1},[e("button",{class:"sandbox-btn",disabled:p.value,onClick:w},"重置",8,Me),p.value?(a(),n("button",{key:1,class:"sandbox-run-btn stop",onClick:oe},"■ 终止")):(a(),n("button",{key:0,class:"sandbox-run-btn",disabled:!v.value.trim(),onClick:se},"▶ 编译运行",8,je))],64))])]),y.value==="source"?(a(),n("div",Oe,[e("pre",null,[e("code",null,i(m.value?.source_excerpt),1)])])):(a(),n("div",Ae,[!v.value&&m.value?(a(),n("div",Re,[...u[4]||(u[4]=[e("p",null,"点击「重置」载入本实验的起始代码，或在下方直接编写。",-1)])])):E("",!0),U(e("textarea",{"onUpdate:modelValue":u[2]||(u[2]=o=>v.value=o),class:"sandbox-editor",placeholder:"在这里输入 C 代码...",spellcheck:"false",disabled:p.value},null,8,Ie),[[D,v.value]])])),e("div",Te,[e("div",Ue,[u[5]||(u[5]=e("span",{class:"sandbox-title"}," 运行终端",-1)),x.value?(a(),n("span",Ve," exit "+i(x.value.code)+" · "+i(h(x.value.durationMs)),1)):E("",!0),p.value?(a(),n("span",We,i(_.value),1)):E("",!0)]),e("div",Be,[e("pre",{class:$(["output-text",{"has-error":x.value&&x.value.code!==0}])},i(l.value),3),!l.value&&!p.value?(a(),n("div",Fe," 点击「编译运行」执行实验代码 ")):E("",!0)])])]),e("aside",qe,[e("div",De,[e("span",ze,i(m.value?.chapter),1),e("strong",null,i(m.value?.title),1),e("small",null,i(m.value?.difficulty),1)]),e("p",Ne,i(m.value?.summary),1),e("section",He,[u[6]||(u[6]=e("h3",null," 实验目标",-1)),e("p",null,i(m.value?.experiment.objective),1)]),e("section",Ge,[u[7]||(u[7]=e("h3",null," 实践任务",-1)),e("ol",null,[(a(!0),n(j,null,T(m.value?.experiment.instructions||[],(o,L)=>(a(),n("li",{key:L},i(o),1))),128))])]),e("section",Je,[u[8]||(u[8]=e("h3",null," 关联概念",-1)),e("div",Xe,[(a(!0),n(j,null,T(m.value?.concepts||[],o=>(a(),n("span",{key:o},i(o),1))),128))])]),e("div",{class:$(["record-status",{passed:R.value}])},[e("strong",null,i(R.value?" 实验已通过":"⏳ 尚未通过"),1),e("small",null,i(I.value)+" 次运行记录",1)],2),e("p",Ye,i(m.value?.attribution),1)])]))}}),Qe=Q(Ke,[["__scopeId","data-v-3342e382"]]),Ze={class:"page-section active"},et={class:"section-header",style:{"text-align":"center"}},tt={class:"workspace-switch","aria-label":"实验工作区"},st=["aria-selected"],ot=["aria-selected"],lt={key:0},at={key:0,class:"compiler-notice",role:"status"},nt={class:"sandbox-layout"},it={class:"sandbox-editor-panel"},rt={class:"sandbox-toolbar"},ut={class:"lang-switch","aria-label":"编程语言"},dt=["aria-selected","disabled"],ct=["aria-selected","disabled"],vt={class:"sandbox-actions"},pt=["disabled"],mt=["value"],ft=["disabled"],bt=["placeholder","disabled"],_t={class:"sandbox-info"},ht={class:"sandbox-output-panel"},yt={class:"sandbox-toolbar"},xt={key:0,class:"sandbox-title"},gt={key:1,class:"sandbox-title"},kt=["disabled"],Ct={class:"sandbox-output"},wt={key:0,class:"output-placeholder"},$t={key:1,class:"output-placeholder"},Et=X({__name:"CodeLabView",setup(c){const s=b("playground"),r=b("c"),f=b(`#include <stdio.h>

int main(void) {
    printf("Hello, OS World!\\n");
    return 0;
}
`),y=b(""),v=b(""),l=b(!1),p=b(""),_=b(null),x=b(""),A=[{id:"hello",title:"Hello World",code:`#include <stdio.h>

int main(void) {
    printf("Hello, OS World!\\n");
    return 0;
}
`},{id:"fcfs",title:"FCFS 调度",code:`#include <stdio.h>

int main(void) {
    int n = 4;
    int at[] = {0, 1, 2, 3};
    int bt[] = {4, 3, 1, 2};
    int ct[4], wt[4], tat[4];
    int time = 0, i;
    for (i = 0; i < n; i++) {
        if (time < at[i]) time = at[i];
        ct[i] = time + bt[i];
        time = ct[i];
        tat[i] = ct[i] - at[i];
        wt[i] = tat[i] - bt[i];
        printf("P%d: 完成=%d 周转=%d 等待=%d\\n", i + 1, ct[i], tat[i], wt[i]);
    }
    return 0;
}
`},{id:"page-replace",title:"FIFO 页面置换",code:`#include <stdio.h>

int main(void) {
    int frames = 3;
    int refs[] = {7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2};
    int n = sizeof(refs) / sizeof(refs[0]);
    int queue[3] = {-1, -1, -1};
    int faults = 0, pos = 0, i, j, hit;
    for (i = 0; i < n; i++) {
        hit = 0;
        for (j = 0; j < frames; j++)
            if (queue[j] == refs[i]) { hit = 1; break; }
        if (!hit) {
            queue[pos] = refs[i];
            pos = (pos + 1) % frames;
            faults++;
            printf("访问 %2d -> 缺页\\n", refs[i]);
        } else {
            printf("访问 %2d -> 命中\\n", refs[i]);
        }
    }
    printf("总缺页次数: %d\\n", faults);
    return 0;
}
`}],W=[{id:"hello-cpp",title:"Hello C++",code:`#include <iostream>
#include <vector>

int main() {
    std::vector<int> v = {1, 2, 3, 4, 5};
    int sum = 0;
    for (int x : v) sum += x;
    std::cout << "sum = " << sum << std::endl;
    return 0;
}
`},{id:"producer-consumer",title:"生产者消费者模拟",code:`#include <iostream>
#include <queue>

int main() {
    std::queue<int> buffer;
    const int capacity = 3;
    int produced = 0, consumed = 0;
    for (int i = 0; i < 6; i++) {
        if (buffer.size() < capacity) {
            buffer.push(produced);
            std::cout << "生产 " << produced++ << std::endl;
        }
        if (!buffer.empty()) {
            std::cout << "消费 " << buffer.front() << std::endl;
            buffer.pop();
            consumed++;
        }
    }
    std::cout << "共消费 " << consumed << " 个" << std::endl;
    return 0;
}
`}],C=M(()=>r.value==="c"?A:W),P=b("hello"),m=N();x.value=m.ready?"":m.message;function O(g){return g<1e3?`${g} ms`:`${(g/1e3).toFixed(1)} s`}function R(g){const t=C.value.find(w=>w.id===g);t&&(f.value=t.code,v.value="",_.value=null)}function I(g){if(l.value)return;r.value=g;const t=C.value[0];t&&(P.value=t.id,f.value=t.code),v.value="",_.value=null}async function B(){if(l.value||!f.value.trim())return;if(!m.ready){v.value=x.value||"浏览器编译环境未就绪";return}l.value=!0,v.value="",_.value=null,p.value="";const g=t=>{const w={runtime:"正在初始化 WASM 运行时...",toolchain:"正在加载编译工具链...",compile:"正在编译...",run:"正在运行程序..."};p.value=w[t]||t};try{const t=r.value==="c"?await ee(f.value,y.value,{onProgress:g}):await pe(f.value,y.value,{onProgress:g});_.value=t;const w=[];t.stdout&&w.push(t.stdout),t.stderr&&w.push(t.stderr),v.value=w.join(`
`)||"(无输出)"}catch(t){v.value=String(t?.message||t)}finally{l.value=!1,p.value=""}}function F(){V(),l.value=!1,p.value="",v.value+=`
[任务已终止]`}return Y(()=>{te()&&V()}),(g,t)=>{const w=ne("RouterLink");return a(),n("div",Ze,[e("div",et,[t[10]||(t[10]=e("div",{class:"section-title"}," 浏览器 C/C++ 实验室",-1)),t[11]||(t[11]=e("div",{class:"section-desc"},"在浏览器内编译运行 C/C++（WASI），无需安装本地工具链",-1)),e("div",tt,[e("button",{type:"button",class:$({active:s.value==="playground"}),"aria-selected":s.value==="playground",onClick:t[0]||(t[0]=h=>s.value="playground")},"自由编程",10,st),e("button",{type:"button",class:$({active:s.value==="source"}),"aria-selected":s.value==="source",onClick:t[1]||(t[1]=h=>s.value="source")},"Linux 0.11 源码",10,ot)]),G(w,{class:"cloud-link",to:"/cloud-lab"},{default:le(()=>[...t[9]||(t[9]=[K("云端存档 →",-1)])]),_:1})]),s.value==="source"?(a(),n("div",lt,[G(Qe)])):(a(),n(j,{key:1},[q(m).ready?E("",!0):(a(),n("div",at,[t[12]||(t[12]=e("strong",null,"浏览器编译环境尚未就绪",-1)),e("span",null,i(x.value),1),t[13]||(t[13]=e("small",null,"开发模式需在 vite.config 中启用 COOP/COEP 响应头，生产环境需反向代理配置。",-1))])),e("div",nt,[e("div",it,[e("div",rt,[e("div",ut,[e("button",{type:"button",class:$({active:r.value==="c"}),"aria-selected":r.value==="c",disabled:l.value,onClick:t[2]||(t[2]=h=>I("c"))},"C",10,dt),e("button",{type:"button",class:$({active:r.value==="cpp"}),"aria-selected":r.value==="cpp",disabled:l.value,onClick:t[3]||(t[3]=h=>I("cpp"))},"C++",10,ct)]),e("div",vt,[U(e("select",{"onUpdate:modelValue":t[4]||(t[4]=h=>P.value=h),class:"example-select","aria-label":"示例代码",disabled:l.value,onChange:t[5]||(t[5]=h=>R(P.value))},[(a(!0),n(j,null,T(C.value,h=>(a(),n("option",{key:h.id,value:h.id},i(h.title),9,mt))),128))],40,pt),[[ae,P.value]]),e("button",{class:"sandbox-btn",onClick:t[6]||(t[6]=h=>{f.value="",v.value=""})},"清空"),l.value?(a(),n("button",{key:1,class:"sandbox-run-btn stop",onClick:F},"■ 终止")):(a(),n("button",{key:0,class:"sandbox-run-btn",disabled:!f.value.trim(),onClick:B},"▶ 运行",8,ft))])]),U(e("textarea",{"onUpdate:modelValue":t[7]||(t[7]=h=>f.value=h),class:"sandbox-editor",placeholder:r.value==="c"?"在这里输入 C 代码...":"在这里输入 C++ 代码...",spellcheck:"false",disabled:l.value},null,8,bt),[[D,f.value]]),e("div",_t,i(r.value==="c"?"clang · wasm32-wasi · C11":"clang++ · wasm32-wasi · C++17")+" — 单次最长 90s，源码 ≤ 20000 字符 ",1)]),e("div",ht,[e("div",yt,[t[14]||(t[14]=e("span",{class:"sandbox-title"}," 标准输入",-1)),_.value?(a(),n("span",xt,"exit "+i(_.value.code)+" · "+i(O(_.value.durationMs)),1)):E("",!0),l.value?(a(),n("span",gt,i(p.value),1)):E("",!0)]),U(e("textarea",{"onUpdate:modelValue":t[8]||(t[8]=h=>y.value=h),class:"sandbox-editor stdin-editor",placeholder:"可选：程序运行时读取的输入",spellcheck:"false",disabled:l.value,maxlength:"8000"},null,8,kt),[[D,y.value]]),t[15]||(t[15]=e("div",{class:"sandbox-toolbar",style:{"border-top":"1px solid var(--border-light)","border-bottom":"none"}},[e("span",{class:"sandbox-title"}," 运行输出")],-1)),e("div",Ct,[e("pre",{class:$(["output-text",{"has-error":_.value&&_.value.code!==0}])},i(v.value),3),!v.value&&!l.value?(a(),n("div",wt," 点击「运行」编译并执行代码，结果将显示在这里 ")):E("",!0),l.value?(a(),n("div",$t,i(p.value||"执行中..."),1)):E("",!0)])])])],64))])}}}),Mt=Q(Et,[["__scopeId","data-v-37832e0a"]]);export{Mt as default};
