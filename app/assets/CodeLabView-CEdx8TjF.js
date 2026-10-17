import{a as X,r as b,S as Y,j as n,b as a,g as e,t as i,u as q,F as j,h as T,i as $,f as E,L as K,m as U,v as D,c as M,y as G,z as le,U as ne,E as ae}from"./vue-vendor-BnleL1jK.js";import{S as ie,e as re,a as ue}from"./sourceLabExercises-D-e1iF10.js";import{c as Q}from"./index-DF53dV6p.js";const de=9e4;let S=null,z=null,k=null,ce=0;function N(){const c=globalThis.isSecureContext===!0,o=globalThis.crossOriginIsolated===!0,u=typeof window<"u"&&window.self!==window.top;return o?{ready:!0,secureContext:c,isolated:o,embedded:u,message:""}:c?u?{ready:!1,secureContext:c,isolated:o,embedded:u,message:"当前实验室位于未隔离的嵌入式预览中，请在独立窗口运行 WASM 编译器。"}:{ready:!1,secureContext:c,isolated:o,embedded:u,message:"当前部署未启用 COOP/COEP 跨源隔离，请检查前端服务器或反向代理响应头。"}:{ready:!1,secureContext:c,isolated:o,embedded:u,message:"当前地址不是安全上下文，请通过 HTTPS、localhost 或 127.0.0.1 访问实验室。"}}function H(c=null){S?.terminate(),S=null,z=null,k&&(clearTimeout(k.timeout),c&&k.reject(c),k=null)}function ve(c){return S&&z===c||(S?.terminate(),S=c==="cpp"?new Worker(new URL("/MARS-408/app/assets/cppCompiler.worker-Bsj1GwvQ.js",import.meta.url),{type:"module"}):new Worker(new URL("/MARS-408/app/assets/cCompiler.worker-AfvyV6_I.js",import.meta.url),{type:"module"}),z=c,S.addEventListener("message",o=>{if(!k||o.data?.id!==k.id)return;if(o.data.type==="progress"){k.onProgress?.(o.data.stage);return}clearTimeout(k.timeout);const u=k;k=null,o.data.type==="result"?u.resolve(o.data.result):u.reject(new Error(o.data.message||"浏览器编译器执行失败"))}),S.addEventListener("error",o=>{H(new Error(o.message||"浏览器编译器 Worker 异常"))})),S}function Z(c,o,u="",f={}){if(!["c","cpp"].includes(c))return Promise.reject(new Error(`不支持的本地编译语言：${c}`));const y=N();if(!y.ready)return Promise.reject(new Error(y.message));if(k)return Promise.reject(new Error("已有编译任务正在运行"));const v=Math.max(5e3,Math.min(18e4,f.timeoutMs||de)),l=`compile-${Date.now()}-${++ce}`;return new Promise((p,_)=>{const x=setTimeout(()=>{H(new Error(`编译运行超过 ${Math.round(v/1e3)} 秒，任务已终止`))},v);k={id:l,resolve:p,reject:_,timeout:x,onProgress:f.onProgress},ve(c).postMessage({id:l,language:c,source:o,stdin:u})})}function ee(c,o="",u={}){return Z("c",c,o,u)}function pe(c,o="",u={}){return Z("cpp",c,o,u)}function V(){return k?(H(new Error("编译任务已取消")),!0):!1}function te(){return!!k}const me={class:"source-lab-workspace"},fe={class:"source-browser"},be={class:"browser-heading"},_e={class:"source-list"},he=["onClick"],xe={class:"source-path"},ye={class:"source-title"},ge={key:0,class:"completed-mark"},ke=["href"],Ce={class:"editor-panel"},we={class:"sandbox-toolbar"},$e={class:"sandbox-title"},Ee={class:"sandbox-actions"},Se={class:"lang-switch","aria-label":"代码视图"},Le=["disabled"],Pe=["disabled"],Me=["disabled"],je=["disabled"],Oe={key:0,class:"source-viewer"},Ae={key:1,class:"editor-wrap"},Re={key:0,class:"editor-placeholder"},Ie=["disabled"],Te={class:"terminal-panel"},Ue={class:"sandbox-toolbar",style:{"border-top":"1px solid var(--border-light)","border-bottom":"none"}},Ve={key:0,class:"sandbox-title"},We={key:1,class:"sandbox-title"},Be={class:"sandbox-output"},Fe={key:0,class:"output-placeholder"},qe={class:"learning-panel"},De={class:"topic-heading"},ze={class:"topic-chapter"},Ne={class:"topic-summary"},He={class:"learning-block"},Ge={class:"learning-block"},Je={class:"learning-block"},Xe={class:"concept-list"},Ye={class:"source-note"},J="mangdehenzhi_sourcelab_progress_v1",Ke=X({__name:"SourceLabPane",setup(c){const o=ie,u=o[0],f=b(u?u.id:""),y=b("source"),v=b(""),l=b(""),p=b(!1),_=b(""),x=b(null),A=N();function W(){try{const d=localStorage.getItem(J);if(d){const r=JSON.parse(d);return{completed:Array.isArray(r.completed)?r.completed:[],attempts:r.attempts&&typeof r.attempts=="object"?r.attempts:{}}}}catch{}return{completed:[],attempts:{}}}const C=b(W());function P(){try{localStorage.setItem(J,JSON.stringify(C.value))}catch{}}const m=M(()=>ue[f.value]),O=M(()=>new Set(C.value.completed)),R=M(()=>O.value.has(f.value)),I=M(()=>C.value.attempts[f.value]||0),B=M(()=>C.value.completed.length);function F(d){f.value=d,y.value="source",v.value="",l.value="",x.value=null}function g(d){p.value||(y.value=d,l.value="",x.value=null)}function t(){const d=m.value;if(d)try{navigator.clipboard?.writeText(d.source_excerpt)}catch{}}function w(){const d=m.value;d&&(v.value=d.experiment.starter_code,l.value="",x.value=null)}function h(d){return d<1e3?`${d} ms`:`${(d/1e3).toFixed(1)} s`}async function se(){const d=m.value;if(p.value||!d||!v.value.trim())return;if(!A.ready){l.value=A.message||"浏览器编译环境未就绪";return}p.value=!0,l.value="",x.value=null,_.value="";const r=s=>{const L={runtime:"正在初始化 WASM 运行时...",toolchain:"正在加载编译工具链...",compile:"正在编译...",run:"正在运行程序..."};_.value=L[s]||s};try{const s=await ee(v.value,d.experiment.stdin,{onProgress:r});x.value=s,C.value.attempts[d.id]=(C.value.attempts[d.id]||0)+1;const L=[];s.stdout&&L.push(s.stdout),s.stderr&&L.push(s.stderr),l.value=L.join(`
`)||"(无输出)",re(d,s.stage,s.code,s.stdout)?O.value.has(d.id)||(C.value.completed.push(d.id),l.value+=`

 实验通过：输出符合预期！`):s.stage==="run"&&(l.value+=`

 未通过：请对照「实验目标」检查输出。`),P()}catch(s){l.value=String(s?.message||s)}finally{p.value=!1,_.value=""}}function oe(){V(),p.value=!1,_.value="",l.value+=`
[任务已终止]`}return Y(()=>{te()&&V()}),(d,r)=>(n(),a("div",me,[e("aside",fe,[e("div",be,[r[3]||(r[3]=e("strong",null,"linux-0.11",-1)),e("small",null,"精选源码 · "+i(B.value)+"/"+i(q(o).length)+" 完成",1)]),e("div",_e,[(n(!0),a(j,null,T(q(o),s=>(n(),a("button",{key:s.id,type:"button",class:$({active:s.id===f.value}),onClick:L=>F(s.id)},[e("span",xe,i(s.path),1),e("span",ye,i(s.title),1),O.value.has(s.id)?(n(),a("span",ge)):E("",!0)],10,he))),128))]),e("a",{class:"archive-link",href:m.value?.source_url,target:"_blank",rel:"noopener noreferrer"}," kernel.org 历史归档 ↗ ",8,ke)]),e("section",Ce,[e("div",we,[e("span",$e,[K(i(m.value?.path)+" ",1),e("small",null,"L"+i(m.value?.source_lines),1)]),e("div",Ee,[e("div",Se,[e("button",{type:"button",class:$({active:y.value==="source"}),disabled:p.value,onClick:r[0]||(r[0]=s=>g("source"))},"原始源码",10,Le),e("button",{type:"button",class:$({active:y.value==="experiment"}),disabled:p.value,onClick:r[1]||(r[1]=s=>g("experiment"))},"可运行实验",10,Pe)]),y.value==="source"?(n(),a("button",{key:0,class:"sandbox-btn",onClick:t},"复制")):(n(),a(j,{key:1},[e("button",{class:"sandbox-btn",disabled:p.value,onClick:w},"重置",8,Me),p.value?(n(),a("button",{key:1,class:"sandbox-run-btn stop",onClick:oe},"■ 终止")):(n(),a("button",{key:0,class:"sandbox-run-btn",disabled:!v.value.trim(),onClick:se},"▶ 编译运行",8,je))],64))])]),y.value==="source"?(n(),a("div",Oe,[e("pre",null,[e("code",null,i(m.value?.source_excerpt),1)])])):(n(),a("div",Ae,[!v.value&&m.value?(n(),a("div",Re,[...r[4]||(r[4]=[e("p",null,"点击「重置」载入本实验的起始代码，或在下方直接编写。",-1)])])):E("",!0),U(e("textarea",{"onUpdate:modelValue":r[2]||(r[2]=s=>v.value=s),class:"sandbox-editor",placeholder:"在这里输入 C 代码...",spellcheck:"false",disabled:p.value},null,8,Ie),[[D,v.value]])])),e("div",Te,[e("div",Ue,[r[5]||(r[5]=e("span",{class:"sandbox-title"}," 运行终端",-1)),x.value?(n(),a("span",Ve," exit "+i(x.value.code)+" · "+i(h(x.value.durationMs)),1)):E("",!0),p.value?(n(),a("span",We,i(_.value),1)):E("",!0)]),e("div",Be,[e("pre",{class:$(["output-text",{"has-error":x.value&&x.value.code!==0}])},i(l.value),3),!l.value&&!p.value?(n(),a("div",Fe," 点击「编译运行」执行实验代码 ")):E("",!0)])])]),e("aside",qe,[e("div",De,[e("span",ze,i(m.value?.chapter),1),e("strong",null,i(m.value?.title),1),e("small",null,i(m.value?.difficulty),1)]),e("p",Ne,i(m.value?.summary),1),e("section",He,[r[6]||(r[6]=e("h3",null," 实验目标",-1)),e("p",null,i(m.value?.experiment.objective),1)]),e("section",Ge,[r[7]||(r[7]=e("h3",null," 实践任务",-1)),e("ol",null,[(n(!0),a(j,null,T(m.value?.experiment.instructions||[],(s,L)=>(n(),a("li",{key:L},i(s),1))),128))])]),e("section",Je,[r[8]||(r[8]=e("h3",null," 关联概念",-1)),e("div",Xe,[(n(!0),a(j,null,T(m.value?.concepts||[],s=>(n(),a("span",{key:s},i(s),1))),128))])]),e("div",{class:$(["record-status",{passed:R.value}])},[e("strong",null,i(R.value?" 实验已通过":"⏳ 尚未通过"),1),e("small",null,i(I.value)+" 次运行记录",1)],2),e("p",Ye,i(m.value?.attribution),1)])]))}}),Qe=Q(Ke,[["__scopeId","data-v-5ea13876"]]),Ze={class:"page-section active"},et={class:"section-header",style:{"text-align":"center"}},tt={class:"workspace-switch","aria-label":"实验工作区"},st={key:0},ot={key:0,class:"compiler-notice",role:"status"},lt={class:"sandbox-layout"},nt={class:"sandbox-editor-panel"},at={class:"sandbox-toolbar"},it={class:"lang-switch","aria-label":"编程语言"},rt=["disabled"],ut=["disabled"],dt={class:"sandbox-actions"},ct=["disabled"],vt=["value"],pt=["disabled"],mt=["placeholder","disabled"],ft={class:"sandbox-info"},bt={class:"sandbox-output-panel"},_t={class:"sandbox-toolbar"},ht={key:0,class:"sandbox-title"},xt={key:1,class:"sandbox-title"},yt=["disabled"],gt={class:"sandbox-output"},kt={key:0,class:"output-placeholder"},Ct={key:1,class:"output-placeholder"},wt=X({__name:"CodeLabView",setup(c){const o=b("playground"),u=b("c"),f=b(`#include <stdio.h>

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
`}],C=M(()=>u.value==="c"?A:W),P=b("hello"),m=N();x.value=m.ready?"":m.message;function O(g){return g<1e3?`${g} ms`:`${(g/1e3).toFixed(1)} s`}function R(g){const t=C.value.find(w=>w.id===g);t&&(f.value=t.code,v.value="",_.value=null)}function I(g){if(l.value)return;u.value=g;const t=C.value[0];t&&(P.value=t.id,f.value=t.code),v.value="",_.value=null}async function B(){if(l.value||!f.value.trim())return;if(!m.ready){v.value=x.value||"浏览器编译环境未就绪";return}l.value=!0,v.value="",_.value=null,p.value="";const g=t=>{const w={runtime:"正在初始化 WASM 运行时...",toolchain:"正在加载编译工具链...",compile:"正在编译...",run:"正在运行程序..."};p.value=w[t]||t};try{const t=u.value==="c"?await ee(f.value,y.value,{onProgress:g}):await pe(f.value,y.value,{onProgress:g});_.value=t;const w=[];t.stdout&&w.push(t.stdout),t.stderr&&w.push(t.stderr),v.value=w.join(`
`)||"(无输出)"}catch(t){v.value=String(t?.message||t)}finally{l.value=!1,p.value=""}}function F(){V(),l.value=!1,p.value="",v.value+=`
[任务已终止]`}return Y(()=>{te()&&V()}),(g,t)=>{const w=ae("RouterLink");return n(),a("div",Ze,[e("div",et,[t[10]||(t[10]=e("div",{class:"section-title"}," 浏览器 C/C++ 实验室",-1)),t[11]||(t[11]=e("div",{class:"section-desc"},"在浏览器内编译运行 C/C++（WASI），无需安装本地工具链",-1)),e("div",tt,[e("button",{type:"button",class:$({active:o.value==="playground"}),onClick:t[0]||(t[0]=h=>o.value="playground")},"自由编程",2),e("button",{type:"button",class:$({active:o.value==="source"}),onClick:t[1]||(t[1]=h=>o.value="source")},"Linux 0.11 源码",2)]),G(w,{class:"cloud-link",to:"/cloud-lab"},{default:le(()=>[...t[9]||(t[9]=[K("云端存档 →",-1)])]),_:1})]),o.value==="source"?(n(),a("div",st,[G(Qe)])):(n(),a(j,{key:1},[q(m).ready?E("",!0):(n(),a("div",ot,[t[12]||(t[12]=e("strong",null,"浏览器编译环境尚未就绪",-1)),e("span",null,i(x.value),1),t[13]||(t[13]=e("small",null,"开发模式需在 vite.config 中启用 COOP/COEP 响应头，生产环境需反向代理配置。",-1))])),e("div",lt,[e("div",nt,[e("div",at,[e("div",it,[e("button",{type:"button",class:$({active:u.value==="c"}),disabled:l.value,onClick:t[2]||(t[2]=h=>I("c"))},"C",10,rt),e("button",{type:"button",class:$({active:u.value==="cpp"}),disabled:l.value,onClick:t[3]||(t[3]=h=>I("cpp"))},"C++",10,ut)]),e("div",dt,[U(e("select",{"onUpdate:modelValue":t[4]||(t[4]=h=>P.value=h),class:"example-select","aria-label":"示例代码",disabled:l.value,onChange:t[5]||(t[5]=h=>R(P.value))},[(n(!0),a(j,null,T(C.value,h=>(n(),a("option",{key:h.id,value:h.id},i(h.title),9,vt))),128))],40,ct),[[ne,P.value]]),e("button",{class:"sandbox-btn",onClick:t[6]||(t[6]=h=>{f.value="",v.value=""})},"清空"),l.value?(n(),a("button",{key:1,class:"sandbox-run-btn stop",onClick:F},"■ 终止")):(n(),a("button",{key:0,class:"sandbox-run-btn",disabled:!f.value.trim(),onClick:B},"▶ 运行",8,pt))])]),U(e("textarea",{"onUpdate:modelValue":t[7]||(t[7]=h=>f.value=h),class:"sandbox-editor",placeholder:u.value==="c"?"在这里输入 C 代码...":"在这里输入 C++ 代码...",spellcheck:"false",disabled:l.value},null,8,mt),[[D,f.value]]),e("div",ft,i(u.value==="c"?"clang · wasm32-wasi · C11":"clang++ · wasm32-wasi · C++17")+" — 单次最长 90s，源码 ≤ 20000 字符 ",1)]),e("div",bt,[e("div",_t,[t[14]||(t[14]=e("span",{class:"sandbox-title"}," 标准输入",-1)),_.value?(n(),a("span",ht,"exit "+i(_.value.code)+" · "+i(O(_.value.durationMs)),1)):E("",!0),l.value?(n(),a("span",xt,i(p.value),1)):E("",!0)]),U(e("textarea",{"onUpdate:modelValue":t[8]||(t[8]=h=>y.value=h),class:"sandbox-editor stdin-editor",placeholder:"可选：程序运行时读取的输入",spellcheck:"false",disabled:l.value,maxlength:"8000"},null,8,yt),[[D,y.value]]),t[15]||(t[15]=e("div",{class:"sandbox-toolbar",style:{"border-top":"1px solid var(--border-light)","border-bottom":"none"}},[e("span",{class:"sandbox-title"}," 运行输出")],-1)),e("div",gt,[e("pre",{class:$(["output-text",{"has-error":_.value&&_.value.code!==0}])},i(v.value),3),!v.value&&!l.value?(n(),a("div",kt," 点击「运行」编译并执行代码，结果将显示在这里 ")):E("",!0),l.value?(n(),a("div",Ct,i(p.value||"执行中..."),1)):E("",!0)])])])],64))])}}}),Lt=Q(wt,[["__scopeId","data-v-bbf12c2b"]]);export{Lt as default};
