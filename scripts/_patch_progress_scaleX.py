#!/usr/bin/env python3
# CRLF-safe, line-based patcher: convert progress-bar `transition: width` -> `transform: scaleX()`.
# Run from repo root:  python scripts/_patch_progress_scaleX.py
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEW_CSS = "width: 100%; transform-origin: left; transition: transform var(--duration-slow) var(--ease-standard);"

# Each file -> list of ops.
# op forms:
#   ("replace", old, new)        -> line-based substring replace (all occurrences in a line)
#   ("drop_contains", substr)    -> drop any line containing substr
SPEC = {
    "src/views/CourseExplorerView.vue": [
        ("replace", "transition: width 0.5s ease;", NEW_CSS),
        ("replace", "width: (densityFor(s.key) / maxDensity * 100) + '%'",
         "width: '100%', transform: 'scaleX(' + (densityFor(s.key) / maxDensity) + ')', transformOrigin: 'left'"),
    ],
    "src/views/CareerTrainingView.vue": [
        ("replace", "transition: width .5s;", NEW_CSS),
        ("replace", "width: ((row.score || 0) / 5 * 100) + '%'",
         "width: '100%', transform: 'scaleX(' + ((row.score || 0) / 5) + ')', transformOrigin: 'left'"),
    ],
    "src/components/GOMARLPanel.vue": [
        ("replace", "transition: width 0.3s ease;", NEW_CSS),
        ("replace", "width: Math.min(weight * 50, 100) + '%'",
         "width: '100%', transform: 'scaleX(' + (Math.min(weight * 50, 100) / 100) + ')', transformOrigin: 'left'"),
    ],
    "src/views/EngineView.vue": [
        ("replace", "transition: width 0.3s ease;", NEW_CSS),
        ("replace", "width: Math.min(100, (tb.tokens / Math.max(tb.capacity, 1)) * 100) + '%'",
         "width: '100%', transform: 'scaleX(' + (Math.min(100, (tb.tokens / Math.max(tb.capacity, 1)) * 100) / 100) + ')', transformOrigin: 'left'"),
    ],
    "src/components/AchievementPanel.vue": [
        ("replace", "transition: width 0.4s ease;", NEW_CSS),
        ("replace", "width: ach.progress + '%'",
         "width: '100%', transform: 'scaleX(' + (ach.progress / 100) + ')', transformOrigin: 'left'"),
    ],
    "src/components/LangGraphFlow.vue": [
        ("replace", "transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);", NEW_CSS),
        ("replace", "width: `${(completedNodes.length / nodeLabels.length) * 100}%`",
         "width: '100%', transform: `scaleX(${completedNodes.length / nodeLabels.length})`, transformOrigin: 'left'"),
    ],
    "src/views/LiteracyAssessmentView.vue": [
        ("replace", "transition: width .3s;", NEW_CSS),
        ("replace", "transition: width .5s;", NEW_CSS),
        ("replace", "width: (result.dim_scores[d] || 0) + '%', background:",
         "width: '100%', transform: 'scaleX(' + ((result.dim_scores[d] || 0) / 100) + ')', transformOrigin: 'left', background:"),
        ("replace", "width: (report.post.dims[d] || 0) + '%', background:",
         "width: '100%', transform: 'scaleX(' + ((report.post.dims[d] || 0) / 100) + ')', transformOrigin: 'left', background:"),
        ("replace", "width: (answeredCount / questions.length * 100) + '%'",
         "width: '100%', transform: 'scaleX(' + (answeredCount / questions.length) + ')', transformOrigin: 'left'"),
        # tokenize hardcoded success/danger hex (redline: no raw hex)
        ("replace", "(report.post.total! - report.pre.total!) >= 0 ? '#22c55e' : '#ef4444'",
         "(report.post.total! - report.pre.total!) >= 0 ? 'var(--accent-success)' : 'var(--accent-danger)'"),
    ],
    "src/views/ProfileView.vue": [
        ("replace", "transition:width 0.8s ease;", NEW_CSS),  # appears twice (502, 521)
        ("replace", "width: trait.value + '%', background:",
         "width: '100%', transform: 'scaleX(' + (trait.value / 100) + ')', transformOrigin: 'left', background:"),
        ("replace", "width: (m.pct ?? 0) + '%'",
         "width: '100%', transform: 'scaleX(' + ((m.pct ?? 0) / 100) + ')', transformOrigin: 'left'"),
    ],
    "src/views/WrongQuestionsView.vue": [
        ("replace", "transition: width 0.5s;", NEW_CSS),
        ("replace", "width: stats.total ? (s.count / stats.total * 100) + '%' : '0%'",
         "width: '100%', transform: 'scaleX(' + (stats.total ? (s.count / stats.total) : 0) + ')', transformOrigin: 'left'"),
        ("replace", "width: stats.total ? (s.mastered / stats.total * 100) + '%' : '0%'",
         "width: '100%', transform: 'scaleX(' + (stats.total ? (s.mastered / stats.total) : 0) + ')', transformOrigin: 'left'"),
    ],
    "src/views/TeacherView.vue": [
        ("replace", "transition:width 0.5s ease;", NEW_CSS),
        ("replace", "width: Math.min(100, bar.value) + '%', background:",
         "width: '100%', transform: 'scaleX(' + (Math.min(100, bar.value) / 100) + ')', transformOrigin: 'left', background:"),
    ],
    "src/views/BenchmarkView.vue": [
        # CSS: drop text-centering/padding/min-width (bar is now empty), swap to scaleX
        ("replace", "transition: width 0.1s linear; min-width: 60px;",
         "width: 100%; transform-origin: left; transition: transform var(--duration-slow) var(--ease-standard);"),
        ("replace", "display: flex; align-items: center; padding: 0 var(--space-3); ", ""),
        # inline width -> scaleX
        ("replace", "width: ((summary?.neuralAccuracy ?? 0) * 100 * animProgress) + '%'",
         "width: '100%', transform: 'scaleX(' + ((summary?.neuralAccuracy ?? 0) * animProgress) + ')', transformOrigin: 'left'"),
        ("replace", "width: ((summary?.votingAccuracy ?? 0) * 100 * animProgress) + '%'",
         "width: '100%', transform: 'scaleX(' + ((summary?.votingAccuracy ?? 0) * animProgress) + ')', transformOrigin: 'left'"),
        # drop redundant inner label (external .contra-count already shows the %)
        ("drop_contains", '<span class="contra-bar-text">'),
        ("drop_contains", ".contra-bar-text {"),
        ("drop_contains", ".contra-bar-text-zero {"),
    ],
    "src/views/LearningPathView.vue": [
        ("replace",
         "width: pct+'%', height:'100%', background:'var(--gradient-accent)', borderRadius:'var(--radius-full)', transition:'width 0.6s ease'",
         "width:'100%', height:'100%', background:'var(--gradient-accent)', borderRadius:'var(--radius-full)', transform:'scaleX(' + (pct/100) + ')', transformOrigin:'left', transition:'transform 0.6s ease'"),
    ],
    "src/views/ResourceView.vue": [
        ("replace", "width: progressPct + '%',",
         "width: '100%', transform: 'scaleX(' + (progressPct / 100) + ')', transformOrigin: 'left',"),
        ("replace", "transition: 'width 0.4s ease',", "transition: 'transform 0.4s ease',"),
    ],
}


def patch_file(relpath, ops):
    path = os.path.join(REPO, relpath)
    with open(path, "rb") as f:
        data = f.read()
    text = data.decode("utf-8")
    lines = text.splitlines(keepends=True)
    out = []
    dropped = 0
    for line in lines:
        drop = False
        for op in ops:
            if op[0] == "drop_contains" and op[1] in line:
                drop = True
                break
        if drop:
            dropped += 1
            continue
        new_line = line
        for op in ops:
            if op[0] == "replace":
                _, old, new = op
                if old in new_line:
                    new_line = new_line.replace(old, new)
        out.append(new_line)
    result = "".join(out)
    if result != text:
        with open(path, "wb") as f:
            f.write(result.encode("utf-8"))
    # report misses
    # (re-scan final text for any operation whose `old` still present for replace ops)
    final = "".join(out)
    for op in ops:
        if op[0] == "replace":
            if op[1] in final:
                print(f"  [MISS] {relpath}: still contains -> {op[1][:60]}")
    print(f"  patched {relpath}  (dropped {dropped} line(s))")


def main():
    for relpath, ops in SPEC.items():
        print(f"-> {relpath}")
        patch_file(relpath, ops)
    print("done.")


if __name__ == "__main__":
    main()
