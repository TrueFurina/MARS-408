import{a as C,o as T,b as a,g as e,F as f,h as b,f as p,t as c,m as P,v as S,i as N,r as u,j as o,q as k,e as D}from"./vue-vendor-DQUnlWCz.js";import{a as y,c as V}from"./index-Dj-4vXEs.js";import"./markdown-DF8BFOMs.js";import"./marked-D6LFbU2s.js";import"./highlight-Cl8noXzz.js";const E={class:"page-section active"},K={class:"section-header",style:{"text-align":"center"}},$={key:0,class:"memory-mini-strip",style:{display:"flex",gap:"8px","flex-wrap":"wrap","margin-bottom":"12px","font-size":"12px"}},B={class:"sandbox-layout"},F={class:"sandbox-editor-panel"},M={class:"sandbox-toolbar"},j={class:"sandbox-actions"},z=["disabled"],H={key:0,class:"sandbox-examples"},I=["onClick","onKeydown"],O={class:"example-name"},q={class:"sandbox-output-panel"},A={class:"sandbox-toolbar"},G={key:0,class:"sandbox-status running"},L={key:0,class:"output-text"},R={key:1,class:"error-text"},U={key:2,class:"output-placeholder"},J={key:3,class:"output-placeholder"},Q=C({__name:"SandboxView",setup(W){const m=u(null);T(async()=>{try{const r=await y.get("/memory/overview");r?.status==="ok"&&(m.value=r)}catch{}});const i=u(`# 网络编程示例：TCP 客户端
# 在沙箱中模拟运行，不会发起真实连接
import socket

def tcp_client():
    """模拟 TCP 客户端"""
    sock = _net_simulate("192.168.1.100", 80)
    print("[模拟] 发送 HTTP GET 请求...")
    print("[模拟] 接收响应: HTTP/1.1 200 OK")
    return True

tcp_client()
print("TCP 客户端运行完成")
`),d=u(""),n=u(""),l=u(!1),v=u(!1),h=[{name:"TCP 客户端",code:`# TCP 客户端示例
import socket

def scan_port(host, port):
    """模拟端口扫描"""
    print(f"[扫描] 检查 {host}:{port}...")

    # 模拟 TCP 连接
    _net_simulate(host, port)
    print(f"[结果] 端口 {port} 开放")

scan_port("192.168.1.1", 80)
print("扫描完成")`},{name:"子网计算",code:`# 子网计算示例
import ipaddress

def calc_subnet(ip_str, prefix):
    net = ipaddress.IPv4Network(f"{ip_str}/{prefix}", strict=False)
    print(f"网络地址: {net.network_address}")
    print(f"广播地址: {net.broadcast_address}")
    print(f"子网掩码: {net.netmask}")
    print(f"可用主机: {net.num_addresses - 2}")
    hosts = list(net.hosts())
    print(f"主机范围: {hosts[0]} ~ {hosts[-1]}")

calc_subnet("192.168.1.0", 24)`},{name:"DNS 解析模拟",code:`# DNS 解析模拟
import random

def dns_lookup(domain):
    """模拟 DNS 解析"""
    print(f"[DNS] 查询 {domain}...")
    # 模拟 DNS 响应
    fake_ip = f"10.0.{random.randint(0,255)}.{random.randint(1,254)}"
    print(f"[DNS] {domain} -> {fake_ip}")
    return fake_ip

dns_lookup("www.example.com")
dns_lookup("mail.example.com")`}];async function g(){if(!(l.value||!i.value.trim())){l.value=!0,d.value="",n.value="";try{const r=await y.post("/sandbox/run",{code:i.value,language:"python",timeout:5});d.value=r.output||"",n.value=r.error||""}catch{n.value="无法连接到后端沙箱服务"}finally{l.value=!1}}}function _(r){i.value=r,d.value="",n.value="",v.value=!1}function w(){i.value="",d.value="",n.value=""}return(r,t)=>(o(),a("div",E,[e("div",K,[t[3]||(t[3]=e("div",{class:"section-title"}," 网络编程沙箱",-1)),t[4]||(t[4]=e("div",{class:"section-desc"},"在线运行网络编程代码，学习 Socket 编程、子网计算等",-1)),m.value?.weak_points?.length?(o(),a("div",$,[t[2]||(t[2]=e("span",{style:{padding:"3px 10px","border-radius":"12px",background:"var(--accent-primary-10)",color:"var(--accent-primary)"}}," 记忆薄弱点:",-1)),(o(!0),a(f,null,b(m.value.weak_points.slice(0,6),s=>(o(),a("span",{key:s,style:{padding:"3px 10px","border-radius":"12px",background:"rgba(239,68,68,0.12)",color:"var(--accent-danger)"}},c(s),1))),128))])):p("",!0)]),e("div",B,[e("div",F,[e("div",M,[t[5]||(t[5]=e("span",{class:"sandbox-title"}," Python 代码",-1)),e("div",j,[e("button",{class:"sandbox-btn",onClick:t[0]||(t[0]=s=>v.value=!v.value)}," 示例"),e("button",{class:"sandbox-btn",onClick:w}," 清空"),e("button",{class:"sandbox-run-btn",disabled:l.value||!i.value.trim(),onClick:g},c(l.value?"⏳ 运行中...":"▶ 运行"),9,z)])]),v.value?(o(),a("div",H,[(o(),a(f,null,b(h,s=>e("div",{key:s.name,class:"sandbox-example-item",role:"button",tabindex:"0",onClick:x=>_(s.code),onKeydown:[k(x=>_(s.code),["enter"]),k(D(x=>_(s.code),["prevent"]),["space"])]},[e("span",O,c(s.name),1),t[6]||(t[6]=e("span",{class:"example-arrow"},"→",-1))],40,I)),64))])):p("",!0),P(e("textarea",{"onUpdate:modelValue":t[1]||(t[1]=s=>i.value=s),class:"sandbox-editor",placeholder:"在这里输入 Python 代码...",spellcheck:"false"},null,512),[[S,i.value]]),t[7]||(t[7]=e("div",{class:"sandbox-info"}," 可用模块: socket, struct, ipaddress, hashlib, json, math, random ",-1))]),e("div",q,[e("div",A,[t[8]||(t[8]=e("span",{class:"sandbox-title"}," 输出",-1)),l.value?(o(),a("span",G,"运行中...")):p("",!0)]),e("div",{class:N(["sandbox-output",{"has-error":n.value}])},[d.value?(o(),a("pre",L,c(d.value),1)):p("",!0),n.value?(o(),a("pre",R,c(n.value),1)):p("",!0),!d.value&&!n.value&&!l.value?(o(),a("div",U," 点击「运行」执行代码，结果将显示在这里 ")):p("",!0),l.value?(o(),a("div",J,[...t[9]||(t[9]=[e("div",{class:"loading-spinner",style:{width:"24px",height:"24px",margin:"0 auto"}},null,-1)])])):p("",!0)],2)])])]))}}),se=V(Q,[["__scopeId","data-v-d461458a"]]);export{se as default};
