# ============================================================
# API — 聊天（/api/chat/*）
# ============================================================

import json as json_mod
import logging
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from shared.sse_guard import sse_disconnect_guard

from db.llm_provider import LLMProvider, LLMUnavailable
from shared.errors import DomainError, LLMUnavailableError, ValidationError
from utils.safety import filter_sensitive
from shared.content_safety import audit_output  # P1-7：统一输出内容安全审核
from models import ChatSendRequest, ChatSendResponse
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from shared.prompt_guard import sanitize_user_input  # F-015：轻量提示注入防护

logger = logging.getLogger("netlearn.chat")
# F-011：聊天/对话端点统一鉴权（get_current_user）+ 每用户 LLM 配额（429）
router = APIRouter(
    prefix="/chat", tags=["chat"],
    dependencies=[Depends(require_llm_quota)],
)


@router.post("/send", response_model=ChatSendResponse)
async def chat_send(req: ChatSendRequest, user: dict = Depends(get_current_user)):
    """通用聊天接口，支持对话历史（双通道回退）"""
    llm = LLMProvider()

    # F-015：对用户输入（含对话历史片段）做轻量句法级净化，防提示注入
    history_text = ""
    for h in (req.history or []):
        if "role" in h and "content" in h:
            role_label = "学生" if h["role"] == "user" else "助教"
            history_text += f"{role_label}: {sanitize_user_input(h['content'])}\n"
    user_message = sanitize_user_input(req.message)
    if not user_message or not user_message.strip():
        raise ValidationError("消息不能为空")

    # 追问指代识别：检测 "那/这个/它/呢/…" 短追问，自动拼接上一问题
    _anaphora = re.search(r'^(那|这|它|他|她|呢|哦|嗯|好|然后|还有)\s*\W*$|^(what|how|why|then|and)\b',
                          user_message.strip(), re.IGNORECASE)
    if _anaphora and req.history:
        last_user = None
        for h in reversed(req.history):
            if h.get("role") == "user":
                last_user = h.get("content", "")
                break
        if last_user:
            user_message = f"(接上一问: {last_user}) {user_message.strip()}"

    user_prompt = f"对话历史:\n{history_text}\n当前问题: {user_message}" if history_text else user_message

    # L1/L2/L3 三层学情记忆注入（低侵入：memory_service.build_memory_context 组装）
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        if user_id:
            from services.memory_service import build_memory_context
            memory_ctx = build_memory_context(user_id, session_id=None, max_episodes=6)
            if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
                user_prompt = (
                    f"【学生历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_ctx}\n\n"
                    f"{user_prompt}"
                )
    except Exception as _me:
        logger.debug(f"聊天记忆注入失败(降级): {_me}")

    try:
        reply = await llm.text_completion(
            "你是计算机网络学习助教。给出清晰、有条理的回答，适当使用要点和示例。语气鼓励且专业。回答控制在 300 字以内。",
            user_prompt,
            temperature=0.7,
        )
    except LLMUnavailable as e:
        raise LLMUnavailableError(detail=str(e))
    except Exception as e:
        logger.error(f"chat_send LLM 调用失败: {e}", exc_info=True)
        raise LLMUnavailableError(detail=f"LLM 调用失败，请稍后重试或在设置页切换通道: {e}")

    if reply:
        # P1-7：统一输出内容安全审核（敏感词 + 讯飞合规 + 幻觉检查）
        reply, _ = await audit_output(reply, "chat/send")

        # P1-4: fire-and-forget 行为画像回写（不阻塞响应）
        try:
            import asyncio
            from agents.behavior_tracker import BehaviorEvent, update_profile_from_behavior
            dwell_ms = min(len(user_message) * 200, 300_000)
            asyncio.create_task(update_profile_from_behavior(
                user.get("user_id", ""),
                [BehaviorEvent(
                    user_id=user.get("user_id", ""),
                    event_type="dwell",
                    topic=user_message[:200],
                    duration_ms=dwell_ms,
                )],
            ))
        except Exception as _be:
            logger.debug(f"行为画像回写跳过: {_be}")

        return ChatSendResponse(response=reply)
    raise LLMUnavailableError(detail="LLM 响应超时，请稍后重试或在设置页切换 LLM 通道")


# ── 工具执行器（内联实现，不依赖外部模块） ──

def _execute_tool(name: str, arguments: str) -> str:
    """执行工具调用，返回结果字符串"""
    import json as _json
    import random as _random
    try:
        args = _json.loads(arguments) if arguments else {}
    except _json.JSONDecodeError:
        return f"参数解析失败: {arguments}"

    if name == "simulate_tcp_handshake":
        src = args.get("src_ip", "192.168.1.100")
        dst = args.get("dst_ip", "218.75.100.50")
        syn_lost = args.get("syn_lost", False)
        syn_ack_lost = args.get("syn_ack_lost", False)
        lines = [
            f"TCP 三次握手模拟: {src} → {dst}",
            "",
            "Step 1: CLOSED → SYN_SENT",
            f"  {src} ──[SYN, seq={_random.randint(1000,9999)}]──→ {dst}",
        ]
        if syn_lost:
            lines.append("  ❌ SYN 丢包！客户端等待超时后重传...")
            lines.append(f"  {src} ──[SYN, seq={_random.randint(1000,9999)}]──→ {dst} (重传)")
        lines.append("")
        lines.append("Step 2: SYN_RCVD")
        lines.append(f"  {dst} ──[SYN+ACK, seq={_random.randint(1000,9999)}, ack={_random.randint(1000,9999)}]──→ {src}")
        if syn_ack_lost:
            lines.append("  ❌ SYN+ACK 丢包！服务端等待超时后重传...")
            lines.append(f"  {dst} ──[SYN+ACK, seq={_random.randint(1000,9999)}, ack={_random.randint(1000,9999)}]──→ {src} (重传)")
        lines.append("")
        lines.append("Step 3: ESTABLISHED")
        lines.append(f"  {src} ──[ACK, seq={_random.randint(1000,9999)}, ack={_random.randint(1000,9999)}]──→ {dst}")
        lines.append("")
        lines.append("✅ 连接建立完成")
        return "\n".join(lines)

    if name == "calculate_subnet":
        ip = args.get("ip", "192.168.1.0")
        mask = args.get("mask", "24")
        # 简化的子网计算（含 LLM 可能产生畸形参数时的防御）
        try:
            if mask.isdigit():
                cidr = int(mask)
                if not (0 <= cidr <= 32):
                    return f"子网掩码无效: /{cidr}（应在 0-32 之间）"
                mask_int = (0xFFFFFFFF << (32 - cidr)) & 0xFFFFFFFF
                mask_str = ".".join(str((mask_int >> (24 - i * 8)) & 0xFF) for i in range(4))
            else:
                mask_str = mask
                cidr = sum(bin(int(x)).count("1") for x in mask.split("."))
            parts = [int(x) for x in ip.split(".")]
            if len(parts) != 4:
                return f"IP 地址格式无效: {ip}"
            ip_int = (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]
        except (ValueError, IndexError) as e:
            return f"参数解析失败: {e}"
        mask_int = sum(bin(int(x)).count("1") for x in mask_str.split("."))
        net_int = ip_int & (0xFFFFFFFF << (32 - mask_int))
        bcast_int = net_int | ((1 << (32 - mask_int)) - 1)
        net = ".".join(str((net_int >> (24 - i * 8)) & 0xFF) for i in range(4))
        bcast = ".".join(str((bcast_int >> (24 - i * 8)) & 0xFF) for i in range(4))
        first = ".".join(str(((net_int + 1) >> (24 - i * 8)) & 0xFF) for i in range(4))
        last = ".".join(str(((bcast_int - 1) >> (24 - i * 8)) & 0xFF) for i in range(4))
        total = 2 ** (32 - mask_int) - 2
        return (
            f"子网计算: {ip}/{mask_str}\n\n"
            f"网络地址: {net}\n"
            f"广播地址: {bcast}\n"
            f"可用主机: {first} ~ {last}\n"
            f"主机数量: {total}\n"
            f"子网掩码: {mask_str}"
        )

    if name == "calculate_crc":
        # 循环32-P0：CRC 校验计算（408 数据链路层高频考点）
        data = str(args.get("data", ""))
        poly = str(args.get("poly", "10011"))  # 默认 CRC-4（G(x)=x^4+x+1）
        try:
            if not all(c in "01" for c in data) or not data:
                return "数据必须是二进制串（如 11010011101100）"
            if not all(c in "01" for c in poly) or len(poly) < 2:
                return f"生成多项式无效: {poly}（二进制串，如 10011）"
            # 校验位长度 = poly 长度 - 1
            r = len(poly) - 1
            dividend = data + "0" * r
            # 模 2 除法（异或）
            p = int(poly, 2)
            p_len = len(poly)
            rem = int(dividend[:p_len], 2)
            for i in range(p_len, len(dividend)):
                rem = ((rem << 1) | int(dividend[i])) & ((1 << p_len) - 1)
                if (rem >> (p_len - 1)) & 1:
                    rem ^= p
            # 处理最后一步后的剩余位
            rem_bits = bin(rem)[2:].zfill(r)
            # 完整余数
            div_int = int(dividend, 2)
            poly_int = int(poly, 2)
            poly_bits = len(dividend) - len(poly) + 1
            rem2 = 0
            for i in range(poly_bits):
                bit = (div_int >> (len(dividend) - 1 - i)) & 1
                rem2 = (rem2 << 1) | bit
                if (rem2 >> (len(poly) - 1)) & 1:
                    rem2 ^= poly_int
            rem2 &= (1 << r) - 1
            crc = bin(rem2)[2:].zfill(r)
            return (
                f"CRC 校验计算: 数据={data}, 多项式={poly}(G(x)=x^{r}+…)\n\n"
                f"1. 数据后补 {r} 个 0: {data + '0' * r}\n"
                f"2. 模 2 除法余数(CRC 校验位): {crc}\n"
                f"3. 发送帧: {data + crc}\n"
                f"4. 接收端用同一多项式整除，余数为 0 则无差错"
            )
        except Exception as e:
            return f"CRC 计算失败: {e}"

    if name == "translate_page_address":
        # 循环32-P0：页表地址转换（408 OS 内存管理高频考点）
        try:
            logical = int(args.get("logical", 0))
            page_size_kb = int(args.get("page_size_kb", 4))
            page_bits = int(args.get("page_bits", 0))  # 页号占位数（可选）
            page_size = page_size_kb * 1024
            offset_bits = page_size.bit_length() - 1
            page_no = logical // page_size
            offset = logical % page_size
            if page_bits:
                # 给出页号位数时反推逻辑地址结构
                return (
                    f"页式地址转换: 逻辑地址={logical}\n\n"
                    f"1. 页大小={page_size_kb}KB → 页内偏移 {offset_bits} 位\n"
                    f"2. 页号 = 逻辑地址 / 页大小 = {page_no}\n"
                    f"3. 页内偏移 = 逻辑地址 % 页大小 = {offset}\n"
                    f"4. 逻辑地址结构: 页号({page_bits}位) + 页内偏移({offset_bits}位)\n"
                    f"   页号部分 = {logical >> offset_bits}, 偏移部分 = {logical & ((1 << offset_bits) - 1)}"
                )
            return (
                f"页式地址转换: 逻辑地址={logical}\n\n"
                f"1. 页大小={page_size_kb}KB ({page_size} B)\n"
                f"2. 页号 = {page_no}\n"
                f"3. 页内偏移 = {offset}\n"
                f"4. 通过页表查询页号 {page_no} 对应的物理页框号，物理地址 = 页框号×页大小 + 偏移"
            )
        except Exception as e:
            return f"地址转换失败: {e}"

    if name == "calculate_ip_checksum":
        # 循环33-P0：IP 首部校验和计算（408 计网运输/网络层高频考点）
        try:
            hex_str = str(args.get("hex", "")).strip()
            if not hex_str:
                return "请提供 IP 首部十六进制串（如 4500 003c 1c46 4000 4006 b1e6 c0a8 0001 c0a8 00c7，校验和字段置 0）"
            # 去空格，转字节
            cleaned = hex_str.replace(" ", "").replace("0x", "")
            if len(cleaned) % 4 != 0:
                return f"十六进制串长度必须为 4 的倍数（16 位字），当前 {len(cleaned)} 位"
            words = [int(cleaned[i:i+4], 16) for i in range(0, len(cleaned), 4)]
            total = sum(words)
            # 回卷进位
            while total > 0xFFFF:
                total = (total & 0xFFFF) + (total >> 16)
            checksum = (~total) & 0xFFFF
            return (
                f"IP 首部校验和计算:\n\n"
                f"1. 16 位字列表: {[hex(w) for w in words]}\n"
                f"2. 求和: 0x{sum(words):X}\n"
                f"3. 回卷进位: 0x{total:X}\n"
                f"4. 取反得校验和: 0x{checksum:04X}（校验和字段应填此值）"
            )
        except Exception as e:
            return f"校验和计算失败: {e}"

    if name == "calculate_scheduling":
        # 循环33-P0：进程调度时间计算（408 OS 进程管理高频考点）
        try:
            raw = str(args.get("arrivals", ""))
            # 格式: "P1:0,P2:1,P3:2"（进程:到达时间），默认服务时间=1
            quantum = int(args.get("quantum", 1))
            if not raw:
                return "请提供进程到达时间（如 P1:0,P2:1,P3:2）"
            procs = []
            for item in raw.split(","):
                item = item.strip()
                if ":" in item:
                    name, arrive = item.split(":")
                    procs.append({"name": name.strip(), "arrival": int(arrive), "service": 1})
                else:
                    procs.append({"name": item, "arrival": 0, "service": 1})
            # FCFS 完成时间/周转/带权周转
            time_elapsed = 0
            rows = []
            total_turn = total_weighted = 0
            for p in sorted(procs, key=lambda x: x["arrival"]):
                start = max(time_elapsed, p["arrival"])
                finish = start + p["service"]
                turn = finish - p["arrival"]
                weighted = turn / p["service"]
                total_turn += turn
                total_weighted += weighted
                rows.append((p["name"], start, finish, turn, round(weighted, 2)))
                time_elapsed = finish
            out = ["FCFS 调度时间计算（服务时间均=1）:", "", "进程  开始  完成  周转  带权周转"]
            for name, start, finish, turn, w in rows:
                out.append(f"{name:5s} {start:4d} {finish:4d} {turn:4d}   {w}")
            out.append("")
            out.append(f"平均周转时间: {total_turn / len(rows):.2f}")
            out.append(f"平均带权周转时间: {total_weighted / len(rows):.2f}")
            return "\n".join(out)
        except Exception as e:
            return f"调度计算失败: {e}"

    if name == "dijkstra_shortest_path":
        # 循环34-P0：Dijkstra 最短路径（408 数据结构图论高频考点）
        try:
            nodes = str(args.get("nodes", ""))
            edges = str(args.get("edges", ""))
            start = str(args.get("start", "")).strip()
            if not nodes or not edges or not start:
                return "请提供节点/边/起点，如 nodes=A,B,C,D edges=A-B:1,B-C:2,A-D:4,C-D:1 start=A"
            node_list = [n.strip() for n in nodes.split(",") if n.strip()]
            if start not in node_list:
                return f"起点 {start} 不在节点列表 {node_list} 中"
            # 建图（无向）
            graph = {n: {} for n in node_list}
            for e in edges.split(","):
                e = e.strip()
                if "-" not in e or ":" not in e:
                    continue
                pair, w = e.split(":")
                u, v = pair.split("-")
                u, v, w = u.strip(), v.strip(), float(w)
                if u in graph and v in graph:
                    graph[u][v] = w
                    graph[v][u] = w
            # Dijkstra
            import heapq
            dist = {n: float("inf") for n in node_list}
            dist[start] = 0
            prev = {}
            pq = [(0, start)]
            while pq:
                d, u = heapq.heappop(pq)
                if d > dist[u]:
                    continue
                for v, w in graph[u].items():
                    nd = d + w
                    if nd < dist[v]:
                        dist[v] = nd
                        prev[v] = u
                        heapq.heappush(pq, (nd, v))
            # 输出
            lines = [f"Dijkstra 最短路径（起点 {start}）:", ""]
            for n in node_list:
                if dist[n] == float("inf"):
                    lines.append(f"  {n}: 不可达")
                    continue
                # 回溯路径
                path = [n]
                cur = n
                while cur in prev:
                    cur = prev[cur]
                    path.insert(0, cur)
                lines.append(f"  {n}: 距离={dist[n]:g}  路径={'→'.join(path)}")
            return "\n".join(lines)
        except Exception as e:
            return f"Dijkstra 计算失败: {e}"

    if name == "huffman_encode":
        # 循环34-P0：哈夫曼编码（408 数据结构树/编码高频考点）
        try:
            raw = str(args.get("weights", ""))
            if not raw:
                return "请提供字符及权重，如 A:45,B:13,C:12,D:16,E:9,F:5"
            items = []
            for item in raw.split(","):
                item = item.strip()
                if ":" not in item:
                    continue
                ch, w = item.split(":")
                items.append([ch.strip(), float(w), "", ""])  # [字符, 权重, 编码, 父]
            if len(items) < 2:
                return "至少需要 2 个字符才能构建哈夫曼树"
            import heapq
            heap = [[w, i, ch] for i, (ch, w, _, _) in enumerate(items)]
            heapq.heapify(heap)
            code = {ch: "" for ch, *_ in items}
            # 用节点合并构建（保存左右子树，_collect_chars 才能递归收集字符）
            # 节点结构: [权重, 字符或None, 左子树, 右子树]
            nodes = [[w, ch, None, None] for ch, w, _, _ in items]
            while len(nodes) > 1:
                nodes.sort(key=lambda x: x[0])
                n1, n2 = nodes.pop(0), nodes.pop(0)
                # 左 0 右 1（合并时立即标记子树字符的编码位）
                for ch in _collect_chars(n1):
                    code[ch] = "0" + code[ch]
                for ch in _collect_chars(n2):
                    code[ch] = "1" + code[ch]
                nodes.append([n1[0] + n2[0], None, n1, n2])
            lines = ["哈夫曼编码:", "", "字符  权重  编码"]
            total_bits = 0
            total_w = 0
            for ch, w, _, _ in items:
                lines.append(f"  {ch:2s}  {w:g}   {code.get(ch, '')}")
                total_bits += w * len(code.get(ch, ""))
                total_w += w
            lines.append("")
            lines.append(f"WPL（带权路径长度）= {total_bits:g}")
            lines.append(f"平均码长 = {total_bits / total_w:.3f} 位/字符")
            return "\n".join(lines)
        except Exception as e:
            return f"哈夫曼编码失败: {e}"

    if name == "kmp_match":
        # 循环6：KMP 模式匹配（408 数据结构字符串匹配高频考点）
        try:
            text = str(args.get("text", ""))
            pattern = str(args.get("pattern", ""))
            if not text or not pattern:
                return "请提供文本与模式串（如 text=ABABDABACDABABCABAB pattern=ABABCABAB）"
            # 构造 next 数组
            m = len(pattern)
            nxt = [0] * m
            j = 0
            for i in range(1, m):
                while j > 0 and pattern[i] != pattern[j]:
                    j = nxt[j - 1]
                if pattern[i] == pattern[j]:
                    j += 1
                nxt[i] = j
            # KMP 匹配
            positions = []
            j = 0
            for i in range(len(text)):
                while j > 0 and text[i] != pattern[j]:
                    j = nxt[j - 1]
                if text[i] == pattern[j]:
                    j += 1
                if j == m:
                    positions.append(i - m + 1)
                    j = nxt[j - 1]
            lines = [
                f"KMP 模式匹配: 文本长度={len(text)}, 模式长度={m}",
                f"next 数组: {nxt}",
                f"匹配位置: {positions if positions else '无匹配'}",
                f"匹配次数: {len(positions)}",
                f"时间复杂度: O({len(text)}+{m})（朴素算法最坏 O({len(text)}*{m})）",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"KMP 匹配失败: {e}"

    if name == "calculate_cache_mapping":
        # 循环6：Cache 映射计算（408 计组存储系统高频考点）
        try:
            cache_kb = int(args.get("cache_kb", 64))
            block_b = int(args.get("block_b", 64))
            addr_bits = int(args.get("addr_bits", 32))
            mapping = str(args.get("mapping", "direct")).strip().lower()
            ways = int(args.get("ways", 2)) if mapping in ("set", "set-associative") else 0
            # 计算
            cache_lines = cache_kb * 1024 // block_b
            offset_bits = block_b.bit_length() - 1
            index_bits = (cache_lines.bit_length() - 1) if mapping == "direct" else (cache_lines // max(ways, 1)).bit_length() - 1
            tag_bits = addr_bits - offset_bits - index_bits
            lines = [
                f"Cache 映射计算（{mapping} 映射）:",
                f"Cache 容量={cache_kb}KB, 块大小={block_b}B",
                f"Cache 行数 = {cache_kb}*1024/{block_b} = {cache_lines} 行",
                f"地址位数 = {addr_bits} 位",
                f"块内偏移位数 = log2({block_b}) = {offset_bits} 位",
                f"索引位数 = {index_bits} 位（{'直接映射' if mapping == 'direct' else f'{ways} 路组相联'}）",
                f"标记(Tag)位数 = {addr_bits}-{offset_bits}-{index_bits} = {tag_bits} 位",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Cache 计算失败: {e}"

    if name == "calculate_ip_fragmentation":
        # 循环6：IP 分片计算（408 计网网络层高频考点）
        try:
            total = int(args.get("total", 4000))
            mtu = int(args.get("mtu", 1500))
            header = int(args.get("header", 20))
            if total <= header or mtu <= header:
                return f"数据长度或 MTU 过小（总长={total}, MTU={mtu}, 首部={header}）"
            data = total - header
            max_data = (mtu - header) // 8 * 8  # 8 字节对齐
            if max_data <= 0:
                return "MTU 过小无法分片"
            fragments = []
            offset = 0
            remaining = data
            while remaining > 0:
                frag_data = min(max_data, remaining)
                mf = 1 if remaining > frag_data else 0
                fragments.append({
                    "frag_data": frag_data,
                    "offset": offset,
                    "mf": mf,
                })
                offset += frag_data // 8
                remaining -= frag_data
            lines = [
                f"IP 分片计算: 总长={total}B, MTU={mtu}B, 首部={header}B",
                f"数据总长 = {total}-{header} = {data}B",
                f"每片最大数据 = ({mtu}-{header})/8*8 = {max_data}B",
                "",
                "分片结果:",
            ]
            for i, f in enumerate(fragments):
                frag_total = header + f["frag_data"]
                lines.append(
                    f"  片{i+1}: 数据{f['frag_data']}B + 首部{header}B = {frag_total}B, "
                    f"偏移={f['offset']}(={f['offset']*8}B), MF={'1' if f['mf'] else '0'}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"IP 分片计算失败: {e}"

    if name == "hash_conflict_resolve":
        # 循环6：哈希冲突处理（408 数据结构查找高频考点）
        try:
            keys_raw = str(args.get("keys", ""))
            table_size = int(args.get("size", 11))
            method = str(args.get("method", "linear")).strip().lower()
            if not keys_raw:
                return "请提供关键字序列（如 47,7,29,11,16,92,22,8,3）"
            keys = [int(k.strip()) for k in keys_raw.split(",") if k.strip()]
            # 开放定址：线性探测 / 二次探测
            table = [None] * table_size
            stats = []
            for k in keys:
                base = k % table_size
                pos = base
                probe = 0
                while table[pos] is not None:
                    probe += 1
                    if method == "linear":
                        pos = (base + probe) % table_size
                    elif method == "quadratic":
                        pos = (base + probe * probe) % table_size
                    else:
                        pos = (base + probe) % table_size
                    if probe > table_size:
                        break
                table[pos] = k
                stats.append((k, base, pos, probe))
            lines = [
                f"哈希表（{method}探测）: 表长={table_size}, 关键字={keys}",
                "散列过程:",
            ]
            for k, base, pos, probe in stats:
                lines.append(f"  {k}: H={k}%{table_size}={base}, 存放位置={pos}, 冲突次数={probe}")
            lines.append("")
            lines.append(f"最终哈希表: {table}")
            # 查找成功平均比较次数（ASL）
            total_comp = sum(1 + s[3] for s in stats)
            lines.append(f"ASL成功 = {sum(1 + s[3] for s in stats)}/{len(stats)} = {total_comp/len(stats):.2f}")
            return "\n".join(lines)
        except Exception as e:
            return f"哈希冲突计算失败: {e}"

    if name == "bankers_algorithm":
        # 任务4：银行家算法（408 死锁避免高频考点）
        try:
            available = str(args.get("available", ""))          # "3,3,2"
            allocation = str(args.get("allocation", ""))        # "0,1,0;2,0,0;3,0,2;2,1,1;0,0,2"
            max_need = str(args.get("max", ""))                 # "7,5,3;3,2,2;9,0,2;2,2,2;4,3,3"
            if not available or not allocation or not max_need:
                return "请提供可用资源/分配矩阵/最大需求矩阵（如 available=3,3,2 allocation=0,1,0;2,0,0 max=7,5,3;3,2,2）"
            avail = [int(x) for x in available.split(",")]
            alloc = [[int(x) for x in row.split(",")] for row in allocation.split(";")]
            mx = [[int(x) for x in row.split(",")] for row in max_need.split(";")]
            n = len(alloc)
            m = len(avail)
            # 计算需求矩阵 Need = Max - Allocation
            need = [[mx[i][j] - alloc[i][j] for j in range(m)] for i in range(n)]
            work = avail[:]
            finish = [False] * n
            safe_seq = []
            # 安全序列检测
            progress = True
            while progress and not all(finish):
                progress = False
                for i in range(n):
                    if not finish[i] and all(need[i][j] <= work[j] for j in range(m)):
                        work = [work[j] + alloc[i][j] for j in range(m)]
                        finish[i] = True
                        safe_seq.append(f"P{i}")
                        progress = True
            lines = [
                f"银行家算法（{n} 进程 × {m} 资源）:",
                "需求矩阵 Need = Max - Allocation:",
            ]
            for i in range(n):
                lines.append(f"  P{i}: Need={need[i]}, Allocation={alloc[i]}, Max={mx[i]}")
            if all(finish):
                lines.append("")
                lines.append(f"✅ 系统处于安全状态")
                lines.append(f"安全序列: {' → '.join(safe_seq)}")
            else:
                lines.append("")
                lines.append(f"❌ 系统处于不安全状态（无法找到完整安全序列，已执行到: {', '.join(safe_seq)}）")
            return "\n".join(lines)
        except Exception as e:
            return f"银行家算法计算失败: {e}"

    if name == "page_replacement_simulate":
        # 任务4：页面置换模拟（408 OS 内存管理高频考点）
        try:
            pages = str(args.get("pages", ""))     # "7,0,1,2,0,3,0,4,2,3,0,3,2"
            frames = int(args.get("frames", 3))
            algo = str(args.get("algo", "fifo")).strip().lower()
            if not pages:
                return "请提供页号序列（如 pages=7,0,1,2,0,3,0,4,2,3,0,3,2 frames=3 algo=fifo）"
            seq = [int(x) for x in pages.split(",")]
            # FIFO / LRU 模拟
            mem = []
            faults = 0
            steps = []
            for idx, p in enumerate(seq):
                hit = p in mem
                if hit and algo == "lru":
                    # LRU 命中：把该页移到末尾（最近使用）
                    mem.remove(p)
                    mem.append(p)
                elif not hit:
                    faults += 1
                    if len(mem) < frames:
                        mem.append(p)
                    else:
                        # mem[0] 为最久未使用（LRU/FIFO 均淘汰队首）
                        mem.pop(0)
                        mem.append(p)
                steps.append(f"  访问 {p}: {'✅命中' if hit else '❌缺页'}  内存={mem}")
            fault_rate = faults / len(seq) * 100
            lines = [
                f"页面置换模拟（{algo.upper()}, {frames} 帧）:",
                f"页号序列: {seq}（{len(seq)} 次访问）",
                "",
            ]
            lines.extend(steps)
            lines.append("")
            lines.append(f"缺页次数: {faults}, 缺页率: {faults}/{len(seq)} = {fault_rate:.1f}%")
            return "\n".join(lines)
        except Exception as e:
            return f"页面置换模拟失败: {e}"

    if name == "topological_sort":
        # 拓扑排序（408 图论高频考点）
        try:
            edges_raw = str(args.get("edges", ""))   # "A,B;B,C;A,C;D,C"
            if not edges_raw:
                return "请提供有向边列表（如 edges=A,B;B,C;A,C;D,C）"
            edges = [e.strip() for e in edges_raw.split(";") if e.strip()]
            # 建图（字符串顶点）
            adj: dict = {}
            indeg: dict = {}
            for e in edges:
                parts = [p.strip() for p in e.split(",")]
                if len(parts) != 2:
                    continue
                u, v = parts[0], parts[1]
                adj.setdefault(u, []).append(v)
                indeg.setdefault(u, 0)
                indeg[v] = indeg.get(v, 0) + 1
            # Kahn 算法
            from collections import deque
            q = deque([n for n in indeg if indeg[n] == 0])
            order = []
            while q:
                u = q.popleft()
                order.append(u)
                for v in adj.get(u, []):
                    indeg[v] -= 1
                    if indeg[v] == 0:
                        q.append(v)
            lines = [
                f"拓扑排序（Kahn 算法）: 顶点={sorted(indeg.keys())}, 边={edges}",
                f"拓扑序列: {' → '.join(order) if order else '无'}",
            ]
            if len(order) == len(indeg):
                lines.append("✅ 有向无环图（DAG），存在拓扑排序")
            else:
                lines.append(f"❌ 存在环！已完成 {len(order)}/{len(indeg)} 个顶点，图中含环路")
            return "\n".join(lines)
        except Exception as e:
            return f"拓扑排序失败: {e}"

    if name == "critical_path":
        # 关键路径（408 图论 AOE 网高频考点）
        try:
            activities = str(args.get("activities", ""))   # "1,2,3;2,3,4;2,4,2;3,5,5;4,5,7"（start,end,weight）
            if not activities:
                return "请提供活动列表（start,end,weight 分号分隔，如 1,2,3;2,3,4;2,4,2;3,5,5;4,5,7）"
            acts = []
            for a in activities.split(";"):
                p = [x.strip() for x in a.split(",")]
                if len(p) == 3:
                    acts.append((int(p[0]), int(p[1]), int(p[2])))
            if not acts:
                return "活动格式无效（需 start,end,weight）"
            # 顶点集合
            nodes = set()
            for s, e, _ in acts:
                nodes.add(s); nodes.add(e)
            # 拓扑排序求最早发生时间
            indeg = {n: 0 for n in nodes}
            adj = {n: [] for n in nodes}
            for s, e, w in acts:
                adj[s].append((e, w)); indeg[e] += 1
            from collections import deque
            q = deque([n for n in nodes if indeg[n] == 0])
            ve = {n: 0 for n in nodes}
            topo = []
            while q:
                u = q.popleft(); topo.append(u)
                for v, w in adj[u]:
                    ve[v] = max(ve[v], ve[u] + w)
                    indeg[v] -= 1
                    if indeg[v] == 0:
                        q.append(v)
            # 逆拓扑求最迟发生时间
            vl = {n: ve.get(max(nodes, key=lambda x: ve.get(x, 0)), 0) for n in nodes}
            end_time = max(ve.values()) if ve else 0
            for n in nodes:
                vl[n] = end_time
            for u in reversed(topo):
                for v, w in adj[u]:
                    vl[u] = min(vl[u], vl[v] - w)
            # 关键活动：ve == vl
            critical = [(s, e) for s, e, w in acts if ve[s] == vl[s] and ve[e] == vl[e]]
            lines = [
                f"关键路径（AOE 网）: 顶点={sorted(nodes)}, 活动={len(acts)}",
                f"最早发生时间 ve: {dict(sorted(ve.items()))}",
                f"最迟发生时间 vl: {dict(sorted(vl.items()))}",
                f"总工期: {end_time}",
                f"关键活动: {critical if critical else '无'}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"关键路径计算失败: {e}"

    if name == "pipeline_speedup":
        # 流水线加速比（408 计组流水线高频考点）
        try:
            stages = int(args.get("stages", 5))
            tasks = int(args.get("tasks", 100))
            t = float(args.get("cycle_time", 1))
            if stages <= 0 or tasks <= 0:
                return "段数/任务数需为正整数"
            # 流水线总时间 = (k + n - 1) * Δt；非流水线 = n * k * Δt
            pipe_time = (stages + tasks - 1) * t
            non_pipe = tasks * stages * t
            speedup = non_pipe / pipe_time
            lines = [
                f"流水线加速比计算: {stages} 段流水线, {tasks} 个任务, 周期 {t}",
                f"非流水线总时间 = {tasks} × {stages} × {t} = {non_pipe:g}",
                f"流水线总时间 = ({stages} + {tasks} - 1) × {t} = {pipe_time:g}",
                f"加速比 S = {non_pipe:g} / {pipe_time:g} = {speedup:.3f}",
                f"理想最大加速比 = 段数 = {stages}",
                f"吞吐率 = {tasks} / {pipe_time:g} = {tasks / pipe_time:.3f} 任务/时间单位",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"流水线加速比计算失败: {e}"

    return f"未知工具: {name}"


def _collect_chars(node: list) -> list:
    """收集哈夫曼节点子树包含的所有字符（节点结构 [权重, 字符或None, 左, 右]）"""
    chars = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur[1] is not None:
            chars.append(cur[1])
        if len(cur) > 2:
            if cur[2]:
                stack.append(cur[2])
            if cur[3]:
                stack.append(cur[3])
    return chars


# ── 工具定义（模块级常量，避免每次请求重复创建） ──

_TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "simulate_tcp_handshake",
            "description": "模拟 TCP 三次握手过程。用户要求演示三次握手、SYN攻击、连接建立时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "src_ip": {"type": "string", "description": "源 IP 地址，默认 192.168.1.100"},
                    "dst_ip": {"type": "string", "description": "目的 IP 地址，默认 218.75.100.50"},
                    "syn_lost": {"type": "boolean", "description": "是否模拟 SYN 丢包"},
                    "syn_ack_lost": {"type": "boolean", "description": "是否模拟 SYN+ACK 丢包"},
                },
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_subnet",
            "description": "计算子网信息。用户要求计算网络地址、广播地址、可用主机范围时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "IP 地址，如 192.168.1.0"},
                    "mask": {"type": "string", "description": "子网掩码，支持 CIDR (24) 或点分十进制 (255.255.255.0)"},
                },
                "required": ["ip", "mask"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_crc",
            "description": "计算 CRC 循环冗余校验。用户要求计算 CRC 校验位、发送帧、差错检测时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "待发送的数据二进制串，如 11010011101100"},
                    "poly": {"type": "string", "description": "生成多项式二进制串，如 10011（默认 CRC-4）"},
                },
                "required": ["data"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "translate_page_address",
            "description": "页式存储地址转换。用户要求计算页号、页内偏移、逻辑地址结构、物理地址时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "logical": {"type": "integer", "description": "逻辑地址（十进制）"},
                    "page_size_kb": {"type": "integer", "description": "页大小（KB），默认 4"},
                    "page_bits": {"type": "integer", "description": "页号占位数（可选，用于反推逻辑地址结构）"},
                },
                "required": ["logical"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_ip_checksum",
            "description": "计算 IP 首部校验和。用户要求计算校验和、IP 首部检测时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "hex": {"type": "string", "description": "IP 首部十六进制串（校验和字段置 0），如 4500 003c 1c46 4000 4006 0000 c0a8 0001 c0a8 00c7"},
                },
                "required": ["hex"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_scheduling",
            "description": "计算进程调度时间（FCFS 周转时间/带权周转）。用户要求计算调度时间、周转时间时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "arrivals": {"type": "string", "description": "进程及到达时间，如 P1:0,P2:1,P3:2"},
                    "quantum": {"type": "integer", "description": "时间片（预留，当前 FCFS 模式）"},
                },
                "required": ["arrivals"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dijkstra_shortest_path",
            "description": "计算 Dijkstra 最短路径。用户要求计算最短路径、单源最短距离、路径规划时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nodes": {"type": "string", "description": "节点列表，逗号分隔，如 A,B,C,D"},
                    "edges": {"type": "string", "description": "边及权重，逗号分隔，如 A-B:1,B-C:2,A-D:4"},
                    "start": {"type": "string", "description": "起点，如 A"},
                },
                "required": ["nodes", "edges", "start"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "huffman_encode",
            "description": "构建哈夫曼树并计算编码。用户要求计算哈夫曼编码、WPL、平均码长时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "weights": {"type": "string", "description": "字符及权重，逗号分隔，如 A:45,B:13,C:12,D:16,E:9,F:5"},
                },
                "required": ["weights"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kmp_match",
            "description": "KMP 模式匹配。用户要求计算 next 数组、字符串匹配位置、匹配次数时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "文本串，如 ABABDABACDABABCABAB"},
                    "pattern": {"type": "string", "description": "模式串，如 ABABCABAB"},
                },
                "required": ["text", "pattern"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_cache_mapping",
            "description": "计算 Cache 映射（直接/组相联）。用户要求计算 Cache 行数、索引位数、Tag 位数、地址结构时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cache_kb": {"type": "integer", "description": "Cache 容量（KB），默认 64"},
                    "block_b": {"type": "integer", "description": "块大小（B），默认 64"},
                    "addr_bits": {"type": "integer", "description": "地址位数，默认 32"},
                    "mapping": {"type": "string", "description": "映射方式：direct（直接）/ set（组相联）"},
                    "ways": {"type": "integer", "description": "组相联路数（set 时有效）"},
                },
                "required": ["cache_kb", "block_b", "addr_bits"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_ip_fragmentation",
            "description": "计算 IP 分片。用户要求计算分片数量、每片偏移量、MF 标志时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "total": {"type": "integer", "description": "IP 数据报总长度（含首部），如 4000"},
                    "mtu": {"type": "integer", "description": "MTU 值，如 1500"},
                    "header": {"type": "integer", "description": "IP 首部长度，默认 20"},
                },
                "required": ["total", "mtu"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hash_conflict_resolve",
            "description": "计算哈希冲突处理。用户要求计算散列过程、冲突次数、ASL、哈希表结果时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "关键字序列，逗号分隔，如 47,7,29,11,16,92,22,8,3"},
                    "size": {"type": "integer", "description": "哈希表长度，默认 11"},
                    "method": {"type": "string", "description": "冲突处理：linear（线性探测）/ quadratic（二次探测）"},
                },
                "required": ["keys", "size"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bankers_algorithm",
            "description": "银行家算法死锁避免。用户要求判断系统是否安全、计算安全序列、Need 矩阵时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "available": {"type": "string", "description": "可用资源向量，逗号分隔，如 3,3,2"},
                    "allocation": {"type": "string", "description": "已分配矩阵，分号分隔行、逗号分隔列，如 0,1,0;2,0,0;3,0,2"},
                    "max": {"type": "string", "description": "最大需求矩阵，如 7,5,3;3,2,2;9,0,2"},
                },
                "required": ["available", "allocation", "max"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "page_replacement_simulate",
            "description": "页面置换算法模拟（FIFO/LRU）。用户要求计算缺页次数、缺页率、内存状态变化时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pages": {"type": "string", "description": "页号访问序列，逗号分隔，如 7,0,1,2,0,3,0,4,2,3,0,3,2"},
                    "frames": {"type": "integer", "description": "内存帧数，默认 3"},
                    "algo": {"type": "string", "description": "置换算法：fifo（先进先出）/ lru（最近最久未使用）"},
                },
                "required": ["pages", "frames"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "topological_sort",
            "description": "拓扑排序（Kahn 算法）。用户要求计算拓扑序列、判断有向图是否有环、DAG 排序时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "edges": {"type": "string", "description": "有向边列表，分号分隔、逗号分隔顶点，如 A,B;B,C;A,C;D,C"},
                },
                "required": ["edges"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "critical_path",
            "description": "关键路径（AOE 网）。用户要求计算总工期、最早/最迟发生时间、关键活动时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "activities": {"type": "string", "description": "活动列表 start,end,weight 分号分隔，如 1,2,3;2,3,4;2,4,2;3,5,5;4,5,7"},
                },
                "required": ["activities"],
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pipeline_speedup",
            "description": "流水线加速比计算。用户要求计算流水线加速比、吞吐率、理想最大加速比时应调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "stages": {"type": "integer", "description": "流水线段数，如 5"},
                    "tasks": {"type": "integer", "description": "任务数，如 100"},
                    "cycle_time": {"type": "number", "description": "时钟周期，默认 1"},
                },
                "required": ["stages", "tasks"],
            }
        }
    },
]


@router.post("/stream")
async def chat_stream(req: ChatSendRequest, request: Request, user: dict = Depends(get_current_user)):
    """流式聊天接口，SSE 格式输出。agent_mode 时支持工具调用。

    统一使用 LLMProvider.stream_chat()（含三通道运行级回退），
    不再手动拼接 httpx 请求，避免讯飞鉴权/端点差异导致的空响应。
    """
    from prompts import AGENT_PROMPT, CHAT_PROMPT

    llm = LLMProvider()

    has_thinking = req.thinking_mode or req.agent_mode
    tools_def = _TOOLS_DEF if req.agent_mode else None

    def build_messages(extra_user_msg=None):
        msgs = [{"role": "system", "content": AGENT_PROMPT if req.agent_mode else CHAT_PROMPT}]
        for h in (req.history or []):
            if "role" in h and "content" in h:
                # F-015：对话历史片段同样视为不可信，做净化
                msgs.append({"role": h["role"], "content": sanitize_user_input(h["content"])})
        msgs.append({"role": "user", "content": sanitize_user_input(extra_user_msg or req.message)})
        return msgs

    async def event_stream():
        finished = False
        collected_tool_calls = {}
        full_content = ""
        current_messages = build_messages()
        finish = None
        active_tools = tools_def  # 工具定义仅首轮使用，避免 nonlocal 作用域问题

        while not finished:
            try:
                async for raw in llm.stream_chat(
                    current_messages, temperature=0.7, tools=active_tools, thinking=has_thinking
                ):
                    payload = raw.strip()
                    if payload == "[DONE]":
                        continue
                    try:
                        chunk = json_mod.loads(payload)
                    except json_mod.JSONDecodeError:
                        continue
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    finish = choices[0].get("finish_reason")

                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        yield f"data: {json_mod.dumps({'type': 'reasoning', 'content': reasoning})}\n\n"

                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in collected_tool_calls:
                                collected_tool_calls[idx] = {"id": tc.get("id", ""), "name": "", "arguments": ""}
                            if tc.get("id"):
                                collected_tool_calls[idx]["id"] = tc["id"]
                            if tc["function"].get("name"):
                                collected_tool_calls[idx]["name"] = tc["function"]["name"]
                            if tc["function"].get("arguments"):
                                collected_tool_calls[idx]["arguments"] += tc["function"]["arguments"]

                    content = delta.get("content", "")
                    if content:
                        full_content += content
                        safe_content, _ = filter_sensitive(content)
                        yield f"data: {json_mod.dumps({'type': 'content', 'content': safe_content})}\n\n"
            except LLMUnavailable as e:
                logger.error("流式 LLM 通道全部不可用: %s", e)
                yield f"data: {json_mod.dumps({'type': 'error', 'content': 'LLM 服务暂时不可用，请稍后重试或切换通道'})}\n\n"
                yield "data: [DONE]\n\n"
                return
            except Exception as e:
                logger.error("流式 LLM 调用失败: %s", e, exc_info=True)
                yield f"data: {json_mod.dumps({'type': 'error', 'content': '请求处理失败，请稍后重试'})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # 工具调用循环：执行工具后将结果回传给模型进行下一轮
            if collected_tool_calls and finish == "tool_calls":
                tools_result_messages = []
                for idx in sorted(collected_tool_calls.keys()):
                    tc = collected_tool_calls[idx]
                    yield f"data: {json_mod.dumps({'type': 'tool_call', 'name': tc['name'], 'arguments': tc['arguments']})}\n\n"
                    result = _execute_tool(tc["name"], tc["arguments"])

                    yield f"data: {json_mod.dumps({'type': 'tool_result', 'name': tc['name'], 'result': result})}\n\n"

                    call_id = tc.get("id") or f"call_{idx}"
                    tools_result_messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}]
                    })
                    tools_result_messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result
                    })

                current_messages = current_messages + tools_result_messages
                collected_tool_calls = {}
                full_content = ""
                finished = False
                active_tools = None  # 第二轮不再带工具，避免死循环
            else:
                finished = True

        # P1-7：流式输出最终聚合内容安全审核（讯飞合规 + 幻觉检查）
        # 注：per-chunk filter_sensitive 已实时过滤敏感词；
        # 此处对完整文本补充 check_compliance + check_hallucination
        if full_content:
            _, _final_notes = await audit_output(full_content, "chat/stream")
            if _final_notes:
                yield f"data: {json_mod.dumps({'type': 'safety_alert', 'content': '; '.join(_final_notes)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_disconnect_guard(request, event_stream()), media_type="text/event-stream")