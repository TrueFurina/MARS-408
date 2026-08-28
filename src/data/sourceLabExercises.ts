/**
 * Linux 0.11 源码导学习题数据
 * 移植自 OS_course（trocedge）backend/services/source_lab_service.py
 * Linux 0.11 (C) 1991 Linus Torvalds，摘自 kernel.org 历史归档
 */

export const SOURCE_ARCHIVE_URL =
  'https://mirrors.edge.kernel.org/pub/linux/kernel/Historic/old-versions/linux-0.11.tar.gz'
export const SOURCE_ATTRIBUTION = 'Linux 0.11 (C) 1991 Linus Torvalds，摘自 kernel.org 历史归档'

export interface SourceLabExperiment {
  objective: string
  instructions: string[]
  starter_code: string
  stdin: string
  expected_output_contains: string[]
}

export interface SourceLabExercise {
  id: string
  title: string
  path: string
  source_lines: string
  chapter: string
  knowledge_point_code: string
  difficulty: '入门' | '进阶'
  summary: string
  concepts: string[]
  source_excerpt: string
  source_url: string
  attribution: string
  experiment: SourceLabExperiment
}

export const SOURCE_LAB_EXERCISES: SourceLabExercise[] = [
  {
    id: 'scheduler-counter',
    title: '计数器调度选择',
    path: 'kernel/sched.c',
    source_lines: '122-141',
    chapter: '进程调度',
    knowledge_point_code: 'cpu_scheduling',
    difficulty: '入门',
    summary: '观察 Linux 0.11 如何选择 counter 最大的可运行任务，并在时间片耗尽后按 priority 重算。',
    concepts: ['TASK_RUNNING', 'counter', 'priority', '时间片'],
    source_excerpt: `/* this is the scheduler proper: */
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
switch_to(next);`,
    source_url: SOURCE_ARCHIVE_URL,
    attribution: SOURCE_ATTRIBUTION,
    experiment: {
      objective: '用用户态结构体复现调度器的核心选择规则。',
      instructions: [
        '运行初始代码，确认 counter 最大的任务首先被选中。',
        '把所有任务的 counter 改为 0，补充重算逻辑并观察 priority 的作用。',
        '尝试增加一个非 TASK_RUNNING 状态的任务，确认它不会被选择。',
      ],
      starter_code: `#include <stdio.h>

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
}`,
      stdin: '',
      expected_output_contains: ['selected pid=2', 'counter=6'],
    },
  },
  {
    id: 'fork-inheritance',
    title: 'fork 状态继承',
    path: 'kernel/fork.c',
    source_lines: '77-91, 120-132',
    chapter: '进程创建',
    knowledge_point_code: 'process_concept',
    difficulty: '入门',
    summary: '区分子进程从父进程复制的字段，以及创建时必须重置的运行状态。',
    concepts: ['task_struct', 'copy_process', '父子进程', '资源引用计数'],
    source_excerpt: `p = (struct task_struct *) get_free_page();
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
return last_pid;`,
    source_url: SOURCE_ARCHIVE_URL,
    attribution: SOURCE_ATTRIBUTION,
    experiment: {
      objective: '模拟结构体复制后对子进程身份、计数器和累计时间的重置。',
      instructions: [
        '比较 parent 与 child 的字段，找出继承和重置的差异。',
        '删除 child.signal 的清零语句，观察错误继承。',
        '增加一个 open_files 字段，模拟 fork 后共享打开文件表。',
      ],
      starter_code: `#include <stdio.h>

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
}`,
      stdin: '',
      expected_output_contains: ['child pid=43', 'father=42', 'counter=5', 'signal=0'],
    },
  },
  {
    id: 'copy-on-write',
    title: '写时复制页',
    path: 'mm/memory.c',
    source_lines: '221-237',
    chapter: '虚拟内存',
    knowledge_point_code: 'virtual_memory',
    difficulty: '进阶',
    summary: '追踪共享页在写入时的引用计数变化，以及何时可以直接恢复可写权限。',
    concepts: ['Copy-on-Write', '页表项', '引用计数', '写保护异常'],
    source_excerpt: `void un_wp_page(unsigned long * table_entry)
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
}`,
    source_url: SOURCE_ARCHIVE_URL,
    attribution: SOURCE_ATTRIBUTION,
    experiment: {
      objective: '用引用计数模型复现共享页第一次写入时的复制行为。',
      instructions: [
        '运行代码，观察父子进程从共享 page 7 分离到两个物理页。',
        '把初始 refs 改为 1，避免不必要的复制。',
        '增加第二次写入，验证私有页不会再次复制。',
      ],
      starter_code: `#include <stdio.h>

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
}`,
      stdin: '',
      expected_output_contains: ['parent page=7 refs=1', 'child page=8 refs=1'],
    },
  },
  {
    id: 'pathname-traversal',
    title: '路径逐级解析',
    path: 'fs/namei.c',
    source_lines: '228-269, 303-330',
    chapter: '文件系统',
    knowledge_point_code: 'directory',
    difficulty: '进阶',
    summary: '理解 namei 如何逐段查找目录项，释放旧 inode，并取得下一层 inode。',
    concepts: ['inode', '目录项', 'namei', '路径分量'],
    source_excerpt: `struct m_inode * namei(const char * pathname)
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
}`,
    source_url: SOURCE_ARCHIVE_URL,
    attribution: SOURCE_ATTRIBUTION,
    experiment: {
      objective: '把绝对路径拆成目录分量，模拟逐级查找过程。',
      instructions: [
        '运行初始代码，观察 /usr/bin/sh 的三个查找步骤。',
        '把路径改为 /home/student/report.txt。',
        '尝试处理连续斜杠，避免输出空分量。',
      ],
      starter_code: `#include <stdio.h>

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
}`,
      stdin: '',
      expected_output_contains: ['step=1 lookup=usr', 'step=2 lookup=bin', 'step=3 lookup=sh'],
    },
  },
]

export const SOURCE_LAB_EXERCISES_BY_ID: Record<string, SourceLabExercise> = Object.fromEntries(
  SOURCE_LAB_EXERCISES.map(e => [e.id, e]),
)

/** 判定实验是否通过：运行阶段 + 退出码 0 + 所有期望输出都出现在 stdout */
export function evaluateSourceLabPass(exercise: SourceLabExercise, stage: string, exitCode: number, stdout: string): boolean {
  if (stage !== 'run' || exitCode !== 0) return false
  const normalized = stdout.replace(/\r\n/g, '\n')
  return exercise.experiment.expected_output_contains.every(marker => normalized.includes(marker))
}
