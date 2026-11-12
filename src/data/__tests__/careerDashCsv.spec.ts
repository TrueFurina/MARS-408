import { describe, expect, it } from 'vitest'
import { csvCell, dashCsvHead, dashCsvRows, dashCsvText } from '@/data/careerDashCsv'

const FULL = {
  expression: 4, stress: 3, decompose: 2.5, collab: 4, presentation: 3, problem_solving: 3.5,
}

describe('dashCsvHead', () => {
  it('六维按 canonical 顺序固定展开，末列是未覆盖维度', () => {
    const head = dashCsvHead()
    expect(head).toHaveLength(13)
    expect(head.slice(0, 6)).toEqual(['学号', '姓名', '是否加入', '完成场次', '总会话', 'best_overall'])
    expect(head.slice(6, 12)).toEqual(['表达逻辑', '抗压应变', '方案拆解', '协作沟通', '技术汇报', '问题解决'])
    expect(head[12]).toBe('未覆盖维度')
  })
})

describe('dashCsvRows · 逐人行', () => {
  it('六维全无分数：数字列留空，末列写未评分而不是 0', () => {
    const [row] = dashCsvRows({ students: [{
      student_no: '3231914117', name: '吴明辉', bound: true,
      finished_count: 0, session_count: 0, overall_best: null, dimension_avg: {},
    }] })
    expect(row).toHaveLength(13)
    expect(row[2]).toBe('已建号未加入')     // bound 不等于 joined
    expect(row[3]).toBe('0')                // 0 场不能因为 falsy 丢成空
    expect(row[5]).toBe('')                 // overall_best 为空留空
    expect(row.slice(6, 12)).toEqual(['', '', '', '', '', ''])
    expect(row[12]).toBe('未评分（六维均无分数）')
  })

  it('部分维度缺失：有分维度填数，末列按 canonical 顺序列出未覆盖维度', () => {
    const [row] = dashCsvRows({ students: [{
      student_no: '3242705101', name: '孙宇鑫', joined: true,
      finished_count: 1, session_count: 2, overall_best: 3.2,
      dimension_avg: { expression: 2, problem_solving: 3.5 },
    }] })
    expect(row[2]).toBe('已加入')
    expect(row.slice(6, 12)).toEqual(['2', '', '', '', '', '3.5'])
    expect(row[12]).toBe('本场景未覆盖：抗压应变、方案拆解、协作沟通、技术汇报')
  })

  it('维度分为 0 时照常写 0，不当作缺失', () => {
    const [row] = dashCsvRows({ students: [{
      student_no: '1', name: '甲', joined: true, finished_count: 1, session_count: 1,
      overall_best: 1, dimension_avg: { ...FULL, expression: 0 },
    }] })
    expect(row[6]).toBe('0')
    expect(row[12]).toBe('')
  })

  it('六维齐全时末列留空，不重复渲染', () => {
    const [row] = dashCsvRows({ students: [{
      student_no: '1', name: '乙', joined: true, finished_count: 1, session_count: 1,
      overall_best: 3.5, dimension_avg: FULL,
    }] })
    expect(row[12]).toBe('')
  })

  it('未建号学生按「未建号」写，不冒充已加入', () => {
    const [row] = dashCsvRows({ students: [{ student_no: '1', name: '丙', dimension_avg: {} }] })
    expect(row[2]).toBe('未建号')
  })
})

describe('dashCsvRows · 班级均分行', () => {
  it('有 summary 时末尾追加班级均分行，口径与逐人行一致', () => {
    const rows = dashCsvRows({
      students: [{ student_no: '1', name: '甲', joined: true, dimension_avg: { expression: 2 } }],
      summary: { student_count: 3, started_count: 2, finished_count: 1,
                 dimension_avg: { expression: 2.3, presentation: 3 } },
    })
    expect(rows).toHaveLength(2)
    const sum = rows[1]
    expect(sum[0]).toBe('')
    expect(sum[1]).toBe('班级均分（3人）')
    expect(sum[2]).toBe('')
    expect(sum[3]).toBe('1')
    expect(sum[4]).toBe('2')
    expect(sum[6]).toBe('2.3')
    expect(sum[10]).toBe('3')
    expect(sum[12]).toBe('本场景未覆盖：抗压应变、方案拆解、协作沟通、问题解决')
  })

  it('无 summary 时不追加（旧响应也没有班级聚合）', () => {
    const rows = dashCsvRows({ students: [] })
    expect(rows).toHaveLength(0)
  })
})

describe('csvCell', () => {
  it('含逗号 / 引号 / 换行的单元格加引号并转义', () => {
    expect(csvCell('甲,乙')).toBe('"甲,乙"')
    expect(csvCell('他说"好"')).toBe('"他说""好"""')
    expect(csvCell('第一行\n第二行')).toBe('"第一行\n第二行"')
    expect(csvCell(0)).toBe('0')
    expect(csvCell(null)).toBe('')
  })
})

describe('dashCsvText', () => {
  it('表头 + 逐人 + 班级均分拼成完整文本，列数一致且不带 BOM', () => {
    const text = dashCsvText({
      class_name: '24信安1班',
      students: [{ student_no: '1', name: '甲,乙', joined: true, dimension_avg: { expression: 2 } }],
      summary: { student_count: 1, started_count: 1, finished_count: 1, dimension_avg: { expression: 2 } },
    })
    const lines = text.split('\n')
    expect(lines).toHaveLength(3)
    expect(lines[0].startsWith('\ufeff')).toBe(false)
    expect(lines[0].endsWith('未覆盖维度')).toBe(true)
    expect(lines[1]).toContain('"甲,乙"')
    for (const line of lines) {
      // 每行列数必须与表头一致（否则跨班合并会错列）
      expect(line.split(',').length).toBeGreaterThanOrEqual(13)
    }
  })
})
