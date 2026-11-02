# 031 R2：制备续跑修复软件验收

日期：2026-11-02；裁决：**accepted（软件范围）**，R1提出的P2已关闭，031研究/物理补齐事项仍开放。

审查[PR #12](https://github.com/No1dry/LIBERO-Remain/pull/12)源码ac1301779cf6ae4c34ebc80c20936a4f7a4953be；修复实现18059cb12abdd505144e36c87b521faeba897de9。未自动合并。

## 核查与证据

- 唯一生产改动在selected_preparation.py：首次由原库存只读验收ready、operations=[]的来源，依赖失效后也被标记并保留历史，不再通过普通continue隐式进入native。
- 被标记来源每次continue只做文件重验；--allow-failed-retry不能绕过该保护。恢复原证据可重新ready；新物理尝试须使用新output，旧记录保留。
- 既有首次缺来源、显式失败重试、build-only→replay路径语义未改。评测代码和分数未改。
- Codex独立运行tests/test_selected_preparation.py与tests/test_selected_producers.py：42 passed、0 skip（0.67秒）。本地JUnit SHA256：1a242ff84362470fb3072d5dd6a0d8c83a47b2311c7780a9a861244349aacb0c。
- 另一独立代码核查将未修改的R1 fake复现脚本用于R2：ready且operations=[]→依赖丢失→missing、invalidated=True、native_calls=[]。未发现本范围明确新错误，不要求扩大回归或新增GPU检查。

## 部署与边界

制备修正版另目录部署，绝不热改a23a8116评测目录。首批80条及后续20条00仍用同一冻结a23评测源码；已完成旧80条10不重跑。

本裁决不代表frypan_stove9、cabinet_close_top_bowl物理证据已通过，不代表两任务模型成功；真实制备与后续评测仍由用户亲自启动。首批00已完成80/80，结果与待定项见[阶段结果](../../docs/stage_summaries/2026-11-02_task031_normal00_eighty_results.md)。

无需X再次返修。本轮没有自主启动真实仿真、回放、eval或训练；没有合并PR、修改旧分数或删除交流文件。精确待删清单=[]。
