# Agent Consultation Workflow

Use this workflow when we want a repeatable second opinion from both local agent CLIs:

- `agy` as the Gemini-side advisor.
- `reasonix` as the DeepSeek-side advisor.

The helper script is:

```powershell
.\tools\consult-agents.ps1 `
  -Question "下一步 passivity enforcement 怎么改进最合理？" `
  -ContextFile docs\sparam-large-port-idem-benchmark.md `
  -ExtraContext "关注 Test16.s91p；只分析，不要改代码。" `
  -AgySkipPermissions
```

Outputs are written to `runs-agent-consult\<timestamp>\`:

- `prompt.md`: the exact prompt sent to both agents.
- `agy-gemini.md`: `agy` output.
- `reasonix-deepseek.md`: `reasonix` output.
- `git-status-before.txt` and `git-status-after.txt`: guardrail to detect accidental edits.

`runs-agent-consult` is covered by the existing `runs-*` ignore rule, so raw consultation transcripts stay out of git unless we intentionally summarize them into docs.

## Recommended Prompt Shape

Keep the question concrete and bounded:

```text
背景：当前 Test16.s91p sparse residue QP 能把 max_sigma 从 1.027606 降到 1.0095，
但 4096 active variables、32 samples、更多 iterations、local refinement 都没有突破。

问题：
1. 当前算法卡住的根因是什么？
2. 按性价比排序的 3 个改进方案是什么？
3. 下一步最小实现版本该改哪些函数？
4. 哪些方向不要继续浪费时间？
```

The prompt should explicitly say `只分析，不要修改任何文件`. The script also records git status before and after the run, but it does not automatically revert changes.

## Notes

- `agy` is expected at `C:\Users\z3312\AppData\Local\agy\bin\agy.exe`. Override with `-AgyPath` if it moves.
- `reasonix` is expected on `PATH`. Override with `-ReasonixCommand` if needed.
- `-AgySkipPermissions` makes `agy` non-interactive for file-reading/tool use. Use it only for analysis prompts that explicitly forbid edits.
- For quick prompt validation without spending model time, use `-SkipAgy -SkipReasonix`; it still writes `prompt.md` and status files.
