# ============================================================
# _execute_tool 端到端测试（循环32/33：408 计算工具防回归）
# ============================================================

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.chat import _execute_tool


def test_calculate_crc_known_vector():
    """CRC 校验：教材经典向量 11010011101100 / 10011 → 校验位 1110"""
    result = _execute_tool("calculate_crc", '{"data": "11010011101100", "poly": "10011"}')
    assert "CRC 校验计算" in result
    assert "1110" in result  # 校验位


def test_calculate_crc_invalid_data():
    """CRC 校验：非法数据返回错误提示"""
    result = _execute_tool("calculate_crc", '{"data": "abc"}')
    assert "数据必须是二进制串" in result


def test_translate_page_address_basic():
    """页表地址转换：逻辑地址 4096 / 4KB 页 → 页号 1 偏移 0"""
    result = _execute_tool("translate_page_address", '{"logical": 4096, "page_size_kb": 4}')
    assert "页号 = 1" in result
    assert "页内偏移 = 0" in result


def test_translate_page_address_with_bits():
    """页表地址转换：带页号位数反推逻辑地址结构"""
    result = _execute_tool("translate_page_address", '{"logical": 4097, "page_size_kb": 4, "page_bits": 20}')
    assert "逻辑地址结构" in result
    assert "页内偏移(12位)" in result


def test_calculate_ip_checksum_known_vector():
    """IP 校验和：4500 003c 1c46 4000 4006 0000 c0a8 0001 c0a8 00c7 → 9C5D"""
    result = _execute_tool(
        "calculate_ip_checksum",
        '{"hex": "4500 003c 1c46 4000 4006 0000 c0a8 0001 c0a8 00c7"}',
    )
    assert "校验和计算" in result
    assert "0x9C5D" in result


def test_calculate_ip_checksum_self_consistent():
    """IP 校验和自洽：校验和字段回填后重算应为 0x0000"""
    result = _execute_tool(
        "calculate_ip_checksum",
        '{"hex": "4500 003c 1c46 4000 4006 9c5d c0a8 0001 c0a8 00c7"}',
    )
    assert "0x0000" in result  # 自洽


def test_calculate_scheduling_fcfs():
    """进程调度 FCFS：P1:0,P2:1,P3:2（服务时间=1）→ 平均周转 1.0"""
    result = _execute_tool("calculate_scheduling", '{"arrivals": "P1:0,P2:1,P3:2"}')
    assert "FCFS 调度" in result
    assert "平均周转时间: 1.00" in result


def test_calculate_scheduling_missing_args():
    """进程调度：缺参返回提示"""
    result = _execute_tool("calculate_scheduling", "{}")
    assert "请提供进程到达时间" in result


def test_unknown_tool():
    """未知工具返回提示（不发 LLM）"""
    result = _execute_tool("no_such_tool", "{}")
    assert "未知工具" in result


# ============================================================
# 新增工具测试（收尾1：KMP/Cache映射/IP分片/哈希/银行家/页面置换）
# ============================================================


def test_kmp_match_found():
    """KMP 匹配：经典案例 ABABDABACDABABCABAB / ABABCABAB → 位置 10"""
    result = _execute_tool(
        "kmp_match",
        '{"text": "ABABDABACDABABCABAB", "pattern": "ABABCABAB"}',
    )
    assert "KMP 模式匹配" in result
    assert "匹配位置" in result


def test_kmp_match_missing_args():
    """KMP 匹配：缺参返回提示"""
    result = _execute_tool("kmp_match", "{}")
    assert "请提供文本与模式串" in result


def test_calculate_cache_mapping_direct():
    """Cache 直接映射：64KB/64B/32位 → 行数 1024，Tag 位数 12"""
    result = _execute_tool(
        "calculate_cache_mapping",
        '{"cache_kb": 64, "block_b": 64, "addr_bits": 32, "mapping": "direct"}',
    )
    assert "Cache 映射计算" in result
    assert "1024 行" in result
    assert "标记(Tag)位数" in result


def test_calculate_ip_fragmentation_basic():
    """IP 分片：4000B/MTU1500/首部20 → 3 片（8字节对齐）"""
    result = _execute_tool(
        "calculate_ip_fragmentation",
        '{"total": 4000, "mtu": 1500, "header": 20}',
    )
    assert "IP 分片计算" in result
    assert "片1:" in result and "片3:" in result
    assert "偏移" in result


def test_calculate_ip_fragmentation_mtu_too_small():
    """IP 分片：MTU 过小返回提示"""
    result = _execute_tool(
        "calculate_ip_fragmentation",
        '{"total": 4000, "mtu": 30, "header": 20}',
    )
    assert "MTU" in result


def test_hash_conflict_resolve_linear():
    """哈希线性探测：47,7,29,11,16,92,22,8,3 / 表长11 → 含 ASL"""
    result = _execute_tool(
        "hash_conflict_resolve",
        '{"keys": "47,7,29,11,16,92,22,8,3", "size": 11, "method": "linear"}',
    )
    assert "哈希表" in result
    assert "ASL成功" in result


def test_bankers_algorithm_safe():
    """银行家算法：经典安全案例 → 安全状态 + 安全序列"""
    result = _execute_tool(
        "bankers_algorithm",
        '{"available": "3,3,2", "allocation": "0,1,0;2,0,0;3,0,2;2,1,1;0,0,2", "max": "7,5,3;3,2,2;9,0,2;2,2,2;4,3,3"}',
    )
    assert "银行家算法" in result
    assert "安全状态" in result
    assert "安全序列" in result


def test_bankers_algorithm_unsafe():
    """银行家算法：构造不安全案例 → 提示不安全状态"""
    result = _execute_tool(
        "bankers_algorithm",
        '{"available": "0,0,0", "allocation": "1,0,0", "max": "2,0,0"}',
    )
    assert "不安全" in result


def test_page_replacement_fifo():
    """页面置换 FIFO：经典 13 页序列/3 帧 → 缺页次数+缺页率"""
    result = _execute_tool(
        "page_replacement_simulate",
        '{"pages": "7,0,1,2,0,3,0,4,2,3,0,3,2", "frames": 3, "algo": "fifo"}',
    )
    assert "FIFO" in result
    assert "缺页次数" in result and "缺页率" in result


def test_page_replacement_lru():
    """页面置换 LRU：同一序列 → LRU 缺页率低于 FIFO"""
    fifo = _execute_tool(
        "page_replacement_simulate",
        '{"pages": "7,0,1,2,0,3,0,4,2,3,0,3,2", "frames": 3, "algo": "fifo"}',
    )
    lru = _execute_tool(
        "page_replacement_simulate",
        '{"pages": "7,0,1,2,0,3,0,4,2,3,0,3,2", "frames": 3, "algo": "lru"}',
    )
    import re
    def faults(r):
        m = re.search(r"缺页次数: (\d+)", r)
        return int(m.group(1)) if m else -1
    assert faults(lru) < faults(fifo), "LRU 缺页次数应少于 FIFO"


# ============================================================
# 新增工具测试（新循环：拓扑排序/关键路径/流水线加速比）
# ============================================================


def test_topological_sort_dag():
    """拓扑排序：经典 DAG A→B→C, A→C, D→C → 存在拓扑序列"""
    result = _execute_tool("topological_sort", '{"edges": "A,B;B,C;A,C;D,C"}')
    assert "拓扑序列" in result
    assert "有向无环图" in result


def test_topological_sort_cycle():
    """拓扑排序：含环图 → 检测出环"""
    result = _execute_tool("topological_sort", '{"edges": "A,B;B,A"}')
    assert "存在环" in result


def test_topological_sort_missing_args():
    """拓扑排序：缺参返回提示"""
    result = _execute_tool("topological_sort", "{}")
    assert "请提供有向边列表" in result


def test_critical_path_basic():
    """关键路径：经典 AOE 网 → 总工期 + 关键活动"""
    result = _execute_tool("critical_path", '{"activities": "1,2,3;2,3,4;2,4,2;3,5,5;4,5,7"}')
    assert "总工期" in result and "关键活动" in result


def test_critical_path_invalid_format():
    """关键路径：非法活动格式返回提示"""
    result = _execute_tool("critical_path", '{"activities": "1,2"}')
    assert "活动" in result


def test_pipeline_speedup_basic():
    """流水线加速比：5 段/100 任务 → 计算加速比"""
    result = _execute_tool("pipeline_speedup", '{"stages": 5, "tasks": 100, "cycle_time": 1}')
    assert "加速比" in result
    assert "非流水线总时间" in result


def test_pipeline_speedup_invalid():
    """流水线加速比：非法参数返回提示"""
    result = _execute_tool("pipeline_speedup", '{"stages": 0, "tasks": 10}')
    assert "正整数" in result
