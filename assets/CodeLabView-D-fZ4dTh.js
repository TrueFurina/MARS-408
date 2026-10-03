import{a as J,r as h,S as X,j as o,b as a,g as e,t as r,u as V,F as R,h as O,i as C,f as S,L as oe,m as P,v as F,c as T,y as ae,U as re}from"./vue-vendor-DQUnlWCz.js";import{_ as Y}from"./index-B8bVdvVO.js";const le=9e4;let E=null,q=null,x=null,ue=0;function z(){const l=globalThis.isSecureContext===!0,s=globalThis.crossOriginIsolated===!0,u=typeof window<"u"&&window.self!==window.top;return s?{ready:!0,secureContext:l,isolated:s,embedded:u,message:""}:l?u?{ready:!1,secureContext:l,isolated:s,embedded:u,message:"当前实验室位于未隔离的嵌入式预览中，请在独立窗口运行 WASM 编译器。"}:{ready:!1,secureContext:l,isolated:s,embedded:u,message:"当前部署未启用 COOP/COEP 跨源隔离，请检查前端服务器或反向代理响应头。"}:{ready:!1,secureContext:l,isolated:s,embedded:u,message:"当前地址不是安全上下文，请通过 HTTPS、localhost 或 127.0.0.1 访问实验室。"}}function D(l=null){E?.terminate(),E=null,q=null,x&&(clearTimeout(x.timeout),l&&x.reject(l),x=null)}function ce(l){return E&&q===l||(E?.terminate(),E=l==="cpp"?new Worker(new URL("/MARS-408/assets/cppCompiler.worker-Bsj1GwvQ.js",import.meta.url),{type:"module"}):new Worker(new URL("/MARS-408/assets/cCompiler.worker-Cb6lPpoo.js",import.meta.url),{type:"module"}),q=l,E.addEventListener("message",s=>{if(!x||s.data?.id!==x.id)return;if(s.data.type==="progress"){x.onProgress?.(s.data.stage);return}clearTimeout(x.timeout);const u=x;x=null,s.data.type==="result"?u.resolve(s.data.result):u.reject(new Error(s.data.message||"浏览器编译器执行失败"))}),E.addEventListener("error",s=>{D(new Error(s.message||"浏览器编译器 Worker 异常"))})),E}function Q(l,s,u="",f={}){if(!["c","cpp"].includes(l))return Promise.reject(new Error(`不支持的本地编译语言：${l}`));const g=z();if(!g.ready)return Promise.reject(new Error(g.message));if(x)return Promise.reject(new Error("已有编译任务正在运行"));const v=Math.max(5e3,Math.min(18e4,f.timeoutMs||le)),i=`compile-${Date.now()}-${++ue}`;return new Promise((_,b)=>{const y=setTimeout(()=>{D(new Error(`编译运行超过 ${Math.round(v/1e3)} 秒，任务已终止`))},v);x={id:i,resolve:_,reject:b,timeout:y,onProgress:f.onProgress},ce(l).postMessage({id:i,language:l,source:s,stdin:u})})}function Z(l,s="",u={}){return Q("c",l,s,u)}function de(l,s="",u={}){return Q("cpp",l,s,u)}function K(){return x?(D(new Error("编译任务已取消")),!0):!1}function ee(){return!!x}const M="https://mirrors.edge.kernel.org/pub/linux/kernel/Historic/old-versions/linux-0.11.tar.gz",j="Linux 0.11 (C) 1991 Linus Torvalds，摘自 kernel.org 历史归档",te=[{id:"scheduler-counter",title:"计数器调度选择",path:"kernel/sched.c",source_lines:"122-141",chapter:"进程调度",knowledge_point_code:"cpu_scheduling",difficulty:"入门",summary:"观察 Linux 0.11 如何选择 counter 最大的可运行任务，并在时间片耗尽后按 priority 重算。",concepts:["TASK_RUNNING","counter","priority","时间片"],source_excerpt:`/* this is the scheduler proper: */
while (1) {
    c = -1;
    next = 0;
    i = NR_TASKS;
    p = &task[NR_TASKS];
    while (--i) {
        if (!*--p)
            continue;
        if ((*p)->state == TASK_RUNNING && (*p)->counter > c)
            c = (*p)->counter, next = i;
    }
    if (c) break;
    for(p = &LAST_TASK ; p > &FIRST_TASK ; --p)
        if (*p)
            (*p)->counter = ((*p)->counter >> 1) +
                    (*p)->priority;
}
switch_to(next);`,source_url:M,attribution:j,experiment:{objective:"用用户态结构体复现调度器的核心选择规则。",instructions:["运行初始代码，确认 counter 最大的任务首先被选中。","把所有任务的 counter 改为 0，补充重算逻辑并观察 priority 的作用。","尝试增加一个非 TASK_RUNNING 状态的任务，确认它不会被选择。"],starter_code:`#include <stdio.h>

#define TASK_RUNNING 0

typedef struct {
    int pid;
    int state;
    int counter;
    int priority;
} task_t;

int pick_next(task_t tasks[], int count) {
    int next = 0;
    int best = -1;
    for (int i = 0; i < count; i++) {
        if (tasks[i].state == TASK_RUNNING && tasks[i].counter > best) {
            best = tasks[i].counter;
            next = i;
        }
    }
    return next;
}

int main(void) {
    task_t tasks[] = {
        {0, TASK_RUNNING, 0, 0},
        {1, TASK_RUNNING, 3, 2},
        {2, TASK_RUNNING, 6, 4},
        {3, 2, 9, 5}
    };
    int next = pick_next(tasks, 4);
    printf("selected pid=%d counter=%d\\n", tasks[next].pid, tasks[next].counter);
    return 0;
}`,stdin:"",expected_output_contains:["selected pid=2","counter=6"]}},{id:"fork-inheritance",title:"fork 状态继承",path:"kernel/fork.c",source_lines:"77-91, 120-132",chapter:"进程创建",knowledge_point_code:"process_concept",difficulty:"入门",summary:"区分子进程从父进程复制的字段，以及创建时必须重置的运行状态。",concepts:["task_struct","copy_process","父子进程","资源引用计数"],source_excerpt:`p = (struct task_struct *) get_free_page();
if (!p)
    return -EAGAIN;
task[nr] = p;
*p = *current;  /* NOTE! this doesn't copy the supervisor stack */
p->state = TASK_UNINTERRUPTIBLE;
p->pid = last_pid;
p->father = current->pid;
p->counter = p->priority;
p->signal = 0;
p->alarm = 0;
p->leader = 0;
p->utime = p->stime = 0;
p->cutime = p->cstime = 0;
p->start_time = jiffies;
/* file and inode reference counts are incremented here */
p->state = TASK_RUNNING;  /* do this last, just in case */
return last_pid;`,source_url:M,attribution:j,experiment:{objective:"模拟结构体复制后对子进程身份、计数器和累计时间的重置。",instructions:["比较 parent 与 child 的字段，找出继承和重置的差异。","删除 child.signal 的清零语句，观察错误继承。","增加一个 open_files 字段，模拟 fork 后共享打开文件表。"],starter_code:`#include <stdio.h>

typedef struct {
    int pid;
    int father;
    int priority;
    int counter;
    int signal;
    int runtime;
} task_t;

task_t copy_process(task_t parent, int child_pid) {
    task_t child = parent;
    child.pid = child_pid;
    child.father = parent.pid;
    child.counter = child.priority;
    child.signal = 0;
    child.runtime = 0;
    return child;
}

int main(void) {
    task_t parent = {42, 1, 5, 2, 8, 120};
    task_t child = copy_process(parent, 43);
    printf("child pid=%d father=%d counter=%d signal=%d runtime=%d\\n",
           child.pid, child.father, child.counter, child.signal, child.runtime);
    return 0;
}`,stdin:"",expected_output_contains:["child pid=43","father=42","counter=5","signal=0"]}},{id:"copy-on-write",title:"写时复制页",path:"mm/memory.c",source_lines:"221-237",chapter:"虚拟内存",knowledge_point_code:"virtual_memory",difficulty:"进阶",summary:"追踪共享页在写入时的引用计数变化，以及何时可以直接恢复可写权限。",concepts:["Copy-on-Write","页表项","引用计数","写保护异常"],source_excerpt:`void un_wp_page(unsigned long * table_entry)
{
    unsigned long old_page,new_page;

    old_page = 0xfffff000 & *table_entry;
    if (old_page >= LOW_MEM && mem_map[MAP_NR(old_page)]==1) {
        *table_entry |= 2;
        invalidate();
        return;
    }
    if (!(new_page=get_free_page()))
        oom();
    if (old_page >= LOW_MEM)
        mem_map[MAP_NR(old_page)]--;
    *table_entry = new_page | 7;
    invalidate();
    copy_page(old_page,new_page);
}`,source_url:M,attribution:j,experiment:{objective:"用引用计数模型复现共享页第一次写入时的复制行为。",instructions:["运行代码，观察父子进程从共享 page 7 分离到两个物理页。","把初始 refs 改为 1，避免不必要的复制。","增加第二次写入，验证私有页不会再次复制。"],starter_code:`#include <stdio.h>

typedef struct {
    int id;
    int refs;
} page_t;

page_t write_private(page_t *shared, int new_id) {
    if (shared->refs == 1) return *shared;
    shared->refs--;
    page_t copy = {new_id, 1};
    return copy;
}

int main(void) {
    page_t parent_page = {7, 2};
    page_t child_page = write_private(&parent_page, 8);
    printf("parent page=%d refs=%d\\n", parent_page.id, parent_page.refs);
    printf("child page=%d refs=%d\\n", child_page.id, child_page.refs);
    return 0;
}`,stdin:"",expected_output_contains:["parent page=7 refs=1","child page=8 refs=1"]}},{id:"pathname-traversal",title:"路径逐级解析",path:"fs/namei.c",source_lines:"228-269, 303-330",chapter:"文件系统",knowledge_point_code:"directory",difficulty:"进阶",summary:"理解 namei 如何逐段查找目录项，释放旧 inode，并取得下一层 inode。",concepts:["inode","目录项","namei","路径分量"],source_excerpt:`struct m_inode * namei(const char * pathname)
{
    const char * basename;
    int inr,dev,namelen;
    struct m_inode * dir;
    struct buffer_head * bh;
    struct dir_entry * de;

    if (!(dir = dir_namei(pathname,&namelen,&basename)))
        return NULL;
    if (!namelen)
        return dir;
    bh = find_entry(&dir,basename,namelen,&de);
    if (!bh) {
        iput(dir);
        return NULL;
    }
    inr = de->inode;
    dev = dir->i_dev;
    brelse(bh);
    iput(dir);
    dir=iget(dev,inr);
    if (dir) {
        dir->i_atime=CURRENT_TIME;
        dir->i_dirt=1;
    }
    return dir;
}`,source_url:M,attribution:j,experiment:{objective:"把绝对路径拆成目录分量，模拟逐级查找过程。",instructions:["运行初始代码，观察 /usr/bin/sh 的三个查找步骤。","把路径改为 /home/student/report.txt。","尝试处理连续斜杠，避免输出空分量。"],starter_code:`#include <stdio.h>

int main(void) {
    const char path[] = "/usr/bin/sh";
    char component[32];
    int length = 0;
    int step = 0;

    for (int i = 0; ; i++) {
        char c = path[i];
        if (c == '/' || c == '\\0') {
            if (length > 0) {
                component[length] = '\\0';
                printf("step=%d lookup=%s\\n", ++step, component);
                length = 0;
            }
            if (c == '\\0') break;
        } else if (length < 31) {
            component[length++] = c;
        }
    }
    return 0;
}`,stdin:"",expected_output_contains:["step=1 lookup=usr","step=2 lookup=bin","step=3 lookup=sh"]}}],pe=Object.fromEntries(te.map(l=>[l.id,l]));function ve(l,s,u,f){if(s!=="run"||u!==0)return!1;const g=f.replace(/\r\n/g,`
`);return l.experiment.expected_output_contains.every(v=>g.includes(v))}const _e={class:"source-lab-workspace"},me={class:"source-browser"},fe={class:"browser-heading"},he={class:"source-list"},be=["onClick"],ge={class:"source-path"},ye={class:"source-title"},ke={key:0,class:"completed-mark"},xe=["href"],we={class:"editor-panel"},Ce={class:"sandbox-toolbar"},Se={class:"sandbox-title"},Ee={class:"sandbox-actions"},Ne={class:"lang-switch","aria-label":"代码视图"},$e=["disabled"],Te=["disabled"],Re=["disabled"],Ae=["disabled"],Le={key:0,class:"source-viewer"},Ie={key:1,class:"editor-wrap"},Ue={key:0,class:"editor-placeholder"},Me=["disabled"],je={class:"terminal-panel"},Oe={class:"sandbox-toolbar",style:{"border-top":"1px solid var(--border-light)","border-bottom":"none"}},Pe={key:0,class:"sandbox-title"},Ke={key:1,class:"sandbox-title"},We={class:"sandbox-output"},Be={key:0,class:"output-placeholder"},Ge={class:"learning-panel"},Ve={class:"topic-heading"},Fe={class:"topic-chapter"},qe={class:"topic-summary"},ze={class:"learning-block"},De={class:"learning-block"},He={class:"learning-block"},Je={class:"concept-list"},Xe={class:"source-note"},H="mangdehenzhi_sourcelab_progress_v1",Ye=J({__name:"SourceLabPane",setup(l){const s=te,u=s[0],f=h(u?u.id:""),g=h("source"),v=h(""),i=h(""),_=h(!1),b=h(""),y=h(null),L=z();function W(){try{const p=localStorage.getItem(H);if(p){const c=JSON.parse(p);return{completed:Array.isArray(c.completed)?c.completed:[],attempts:c.attempts&&typeof c.attempts=="object"?c.attempts:{}}}}catch{}return{completed:[],attempts:{}}}const w=h(W());function $(){try{localStorage.setItem(H,JSON.stringify(w.value))}catch{}}const m=T(()=>pe[f.value]),A=T(()=>new Set(w.value.completed)),I=T(()=>A.value.has(f.value)),U=T(()=>w.value.attempts[f.value]||0),B=T(()=>w.value.completed.length);function G(p){f.value=p,g.value="source",v.value="",i.value="",y.value=null}function k(p){_.value||(g.value=p,i.value="",y.value=null)}function t(){const p=m.value;if(p)try{navigator.clipboard?.writeText(p.source_excerpt)}catch{}}function d(){const p=m.value;p&&(v.value=p.experiment.starter_code,i.value="",y.value=null)}function se(p){return p<1e3?`${p} ms`:`${(p/1e3).toFixed(1)} s`}async function ne(){const p=m.value;if(_.value||!p||!v.value.trim())return;if(!L.ready){i.value=L.message||"浏览器编译环境未就绪";return}_.value=!0,i.value="",y.value=null,b.value="";const c=n=>{const N={runtime:"正在初始化 WASM 运行时...",toolchain:"正在加载编译工具链...",compile:"正在编译...",run:"正在运行程序..."};b.value=N[n]||n};try{const n=await Z(v.value,p.experiment.stdin,{onProgress:c});y.value=n,w.value.attempts[p.id]=(w.value.attempts[p.id]||0)+1;const N=[];n.stdout&&N.push(n.stdout),n.stderr&&N.push(n.stderr),i.value=N.join(`
`)||"(无输出)",ve(p,n.stage,n.code,n.stdout)?A.value.has(p.id)||(w.value.completed.push(p.id),i.value+=`

 实验通过：输出符合预期！`):n.stage==="run"&&(i.value+=`

 未通过：请对照「实验目标」检查输出。`),$()}catch(n){i.value=String(n?.message||n)}finally{_.value=!1,b.value=""}}function ie(){K(),_.value=!1,b.value="",i.value+=`
[任务已终止]`}return X(()=>{ee()&&K()}),(p,c)=>(o(),a("div",_e,[e("aside",me,[e("div",fe,[c[3]||(c[3]=e("strong",null,"linux-0.11",-1)),e("small",null,"精选源码 · "+r(B.value)+"/"+r(V(s).length)+" 完成",1)]),e("div",he,[(o(!0),a(R,null,O(V(s),n=>(o(),a("button",{key:n.id,type:"button",class:C({active:n.id===f.value}),onClick:N=>G(n.id)},[e("span",ge,r(n.path),1),e("span",ye,r(n.title),1),A.value.has(n.id)?(o(),a("span",ke)):S("",!0)],10,be))),128))]),e("a",{class:"archive-link",href:m.value?.source_url,target:"_blank",rel:"noopener noreferrer"}," kernel.org 历史归档 ↗ ",8,xe)]),e("section",we,[e("div",Ce,[e("span",Se,[oe(r(m.value?.path)+" ",1),e("small",null,"L"+r(m.value?.source_lines),1)]),e("div",Ee,[e("div",Ne,[e("button",{type:"button",class:C({active:g.value==="source"}),disabled:_.value,onClick:c[0]||(c[0]=n=>k("source"))},"原始源码",10,$e),e("button",{type:"button",class:C({active:g.value==="experiment"}),disabled:_.value,onClick:c[1]||(c[1]=n=>k("experiment"))},"可运行实验",10,Te)]),g.value==="source"?(o(),a("button",{key:0,class:"sandbox-btn",onClick:t},"复制")):(o(),a(R,{key:1},[e("button",{class:"sandbox-btn",disabled:_.value,onClick:d},"重置",8,Re),_.value?(o(),a("button",{key:1,class:"sandbox-run-btn stop",onClick:ie},"■ 终止")):(o(),a("button",{key:0,class:"sandbox-run-btn",disabled:!v.value.trim(),onClick:ne},"▶ 编译运行",8,Ae))],64))])]),g.value==="source"?(o(),a("div",Le,[e("pre",null,[e("code",null,r(m.value?.source_excerpt),1)])])):(o(),a("div",Ie,[!v.value&&m.value?(o(),a("div",Ue,[...c[4]||(c[4]=[e("p",null,"点击「重置」载入本实验的起始代码，或在下方直接编写。",-1)])])):S("",!0),P(e("textarea",{"onUpdate:modelValue":c[2]||(c[2]=n=>v.value=n),class:"sandbox-editor",placeholder:"在这里输入 C 代码...",spellcheck:"false",disabled:_.value},null,8,Me),[[F,v.value]])])),e("div",je,[e("div",Oe,[c[5]||(c[5]=e("span",{class:"sandbox-title"}," 运行终端",-1)),y.value?(o(),a("span",Pe," exit "+r(y.value.code)+" · "+r(se(y.value.durationMs)),1)):S("",!0),_.value?(o(),a("span",Ke,r(b.value),1)):S("",!0)]),e("div",We,[e("pre",{class:C(["output-text",{"has-error":y.value&&y.value.code!==0}])},r(i.value),3),!i.value&&!_.value?(o(),a("div",Be," 点击「编译运行」执行实验代码 ")):S("",!0)])])]),e("aside",Ge,[e("div",Ve,[e("span",Fe,r(m.value?.chapter),1),e("strong",null,r(m.value?.title),1),e("small",null,r(m.value?.difficulty),1)]),e("p",qe,r(m.value?.summary),1),e("section",ze,[c[6]||(c[6]=e("h3",null," 实验目标",-1)),e("p",null,r(m.value?.experiment.objective),1)]),e("section",De,[c[7]||(c[7]=e("h3",null," 实践任务",-1)),e("ol",null,[(o(!0),a(R,null,O(m.value?.experiment.instructions||[],(n,N)=>(o(),a("li",{key:N},r(n),1))),128))])]),e("section",He,[c[8]||(c[8]=e("h3",null," 关联概念",-1)),e("div",Je,[(o(!0),a(R,null,O(m.value?.concepts||[],n=>(o(),a("span",{key:n},r(n),1))),128))])]),e("div",{class:C(["record-status",{passed:I.value}])},[e("strong",null,r(I.value?" 实验已通过":"⏳ 尚未通过"),1),e("small",null,r(U.value)+" 次运行记录",1)],2),e("p",Xe,r(m.value?.attribution),1)])]))}}),Qe=Y(Ye,[["__scopeId","data-v-5ea13876"]]),Ze={class:"page-section active"},et={class:"section-header",style:{"text-align":"center"}},tt={class:"workspace-switch","aria-label":"实验工作区"},st={key:0},nt={key:0,class:"compiler-notice",role:"status"},it={class:"sandbox-layout"},ot={class:"sandbox-editor-panel"},at={class:"sandbox-toolbar"},rt={class:"lang-switch","aria-label":"编程语言"},lt=["disabled"],ut=["disabled"],ct={class:"sandbox-actions"},dt=["disabled"],pt=["value"],vt=["disabled"],_t=["placeholder","disabled"],mt={class:"sandbox-info"},ft={class:"sandbox-output-panel"},ht={class:"sandbox-toolbar"},bt={key:0,class:"sandbox-title"},gt={key:1,class:"sandbox-title"},yt=["disabled"],kt={class:"sandbox-output"},xt={key:0,class:"output-placeholder"},wt={key:1,class:"output-placeholder"},Ct=J({__name:"CodeLabView",setup(l){const s=h("playground"),u=h("c"),f=h(`#include <stdio.h>

int main(void) {
    printf("Hello, OS World!\\n");
    return 0;
}
`),g=h(""),v=h(""),i=h(!1),_=h(""),b=h(null),y=h(""),L=[{id:"hello",title:"Hello World",code:`#include <stdio.h>

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
`}],w=T(()=>u.value==="c"?L:W),$=h("hello"),m=z();y.value=m.ready?"":m.message;function A(k){return k<1e3?`${k} ms`:`${(k/1e3).toFixed(1)} s`}function I(k){const t=w.value.find(d=>d.id===k);t&&(f.value=t.code,v.value="",b.value=null)}function U(k){if(i.value)return;u.value=k;const t=w.value[0];t&&($.value=t.id,f.value=t.code),v.value="",b.value=null}async function B(){if(i.value||!f.value.trim())return;if(!m.ready){v.value=y.value||"浏览器编译环境未就绪";return}i.value=!0,v.value="",b.value=null,_.value="";const k=t=>{const d={runtime:"正在初始化 WASM 运行时...",toolchain:"正在加载编译工具链...",compile:"正在编译...",run:"正在运行程序..."};_.value=d[t]||t};try{const t=u.value==="c"?await Z(f.value,g.value,{onProgress:k}):await de(f.value,g.value,{onProgress:k});b.value=t;const d=[];t.stdout&&d.push(t.stdout),t.stderr&&d.push(t.stderr),v.value=d.join(`
`)||"(无输出)"}catch(t){v.value=String(t?.message||t)}finally{i.value=!1,_.value=""}}function G(){K(),i.value=!1,_.value="",v.value+=`
[任务已终止]`}return X(()=>{ee()&&K()}),(k,t)=>(o(),a("div",Ze,[e("div",et,[t[9]||(t[9]=e("div",{class:"section-title"}," 浏览器 C/C++ 实验室",-1)),t[10]||(t[10]=e("div",{class:"section-desc"},"在浏览器内编译运行 C/C++（WASI），无需安装本地工具链",-1)),e("div",tt,[e("button",{type:"button",class:C({active:s.value==="playground"}),onClick:t[0]||(t[0]=d=>s.value="playground")},"自由编程",2),e("button",{type:"button",class:C({active:s.value==="source"}),onClick:t[1]||(t[1]=d=>s.value="source")},"Linux 0.11 源码",2)])]),s.value==="source"?(o(),a("div",st,[ae(Qe)])):(o(),a(R,{key:1},[V(m).ready?S("",!0):(o(),a("div",nt,[t[11]||(t[11]=e("strong",null,"浏览器编译环境尚未就绪",-1)),e("span",null,r(y.value),1),t[12]||(t[12]=e("small",null,"开发模式需在 vite.config 中启用 COOP/COEP 响应头，生产环境需反向代理配置。",-1))])),e("div",it,[e("div",ot,[e("div",at,[e("div",rt,[e("button",{type:"button",class:C({active:u.value==="c"}),disabled:i.value,onClick:t[2]||(t[2]=d=>U("c"))},"C",10,lt),e("button",{type:"button",class:C({active:u.value==="cpp"}),disabled:i.value,onClick:t[3]||(t[3]=d=>U("cpp"))},"C++",10,ut)]),e("div",ct,[P(e("select",{"onUpdate:modelValue":t[4]||(t[4]=d=>$.value=d),class:"example-select","aria-label":"示例代码",disabled:i.value,onChange:t[5]||(t[5]=d=>I($.value))},[(o(!0),a(R,null,O(w.value,d=>(o(),a("option",{key:d.id,value:d.id},r(d.title),9,pt))),128))],40,dt),[[re,$.value]]),e("button",{class:"sandbox-btn",onClick:t[6]||(t[6]=d=>{f.value="",v.value=""})},"清空"),i.value?(o(),a("button",{key:1,class:"sandbox-run-btn stop",onClick:G},"■ 终止")):(o(),a("button",{key:0,class:"sandbox-run-btn",disabled:!f.value.trim(),onClick:B},"▶ 运行",8,vt))])]),P(e("textarea",{"onUpdate:modelValue":t[7]||(t[7]=d=>f.value=d),class:"sandbox-editor",placeholder:u.value==="c"?"在这里输入 C 代码...":"在这里输入 C++ 代码...",spellcheck:"false",disabled:i.value},null,8,_t),[[F,f.value]]),e("div",mt,r(u.value==="c"?"clang · wasm32-wasi · C11":"clang++ · wasm32-wasi · C++17")+" — 单次最长 90s，源码 ≤ 20000 字符 ",1)]),e("div",ft,[e("div",ht,[t[13]||(t[13]=e("span",{class:"sandbox-title"}," 标准输入",-1)),b.value?(o(),a("span",bt,"exit "+r(b.value.code)+" · "+r(A(b.value.durationMs)),1)):S("",!0),i.value?(o(),a("span",gt,r(_.value),1)):S("",!0)]),P(e("textarea",{"onUpdate:modelValue":t[8]||(t[8]=d=>g.value=d),class:"sandbox-editor stdin-editor",placeholder:"可选：程序运行时读取的输入",spellcheck:"false",disabled:i.value,maxlength:"8000"},null,8,yt),[[F,g.value]]),t[14]||(t[14]=e("div",{class:"sandbox-toolbar",style:{"border-top":"1px solid var(--border-light)","border-bottom":"none"}},[e("span",{class:"sandbox-title"}," 运行输出")],-1)),e("div",kt,[e("pre",{class:C(["output-text",{"has-error":b.value&&b.value.code!==0}])},r(v.value),3),!v.value&&!i.value?(o(),a("div",xt," 点击「运行」编译并执行代码，结果将显示在这里 ")):S("",!0),i.value?(o(),a("div",wt,r(_.value||"执行中..."),1)):S("",!0)])])])],64))]))}}),Nt=Y(Ct,[["__scopeId","data-v-5b6653dd"]]);export{Nt as default};
