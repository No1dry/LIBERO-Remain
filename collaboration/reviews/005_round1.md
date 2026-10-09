# Codex Review：PR #3，004/005实现与006诊断文档

日期：2026-10-10。审查HEAD `04508dc0b0c48bf10e33c69ed3d3e830df793aaf`，基准main `4a02c78c0b945c2df2f0748614fecdd1c5127f55`。
004独立实现7318c4b；005实现7c47c12。PR：https://github.com/No1dry/LIBERO-Remain/pull/3。

## 裁决

004/005代码功能accepted，未发现阻塞问题；006非阻塞诊断原则认可。X可在无新增未审源码的前提下合并PR #3并登记main SHA。当前实验冻结04508dc，不等待合并，不在运行中pull或改源码。
这是代码/运行合同验收，不是Stage03科学阶段关闭、UIR标注完成或benchmark发布。

## 独立验证

- macOS Python3.12.7：1231 passed / 12 skipped，96.39秒；11项未安装固定仿真源码、1项本机缺imageio_ffmpeg。
- Linux服务器实际simulation Python3.10.21、禁CUDA的完整测试：1243 passed / 0 skipped，45.84秒，含固定源码检查和CPU编码。
- 首轮Linux命令未创建reports父目录，pytest basetemp初始化错误；修正执行命令后全通过。这是Codex启动方式问题，不是X代码失败；没有因此跑VLA或改实现。
- 真实001 dry-plan：主15条（10/01/11各5），not_selected00共5；诊断10条（10/01各5），完整source20；indices0..4无替换。主7450/诊断6700策略步，一次model load、15/10 reset。
- 源manifest SHA50c557f0…8797d，content hash c3f15ec7…13cbb；replay SHAee4902bf…5ef46，与已冻结001相同。静态实际配置ready，seed7/chunk8、同SOG10/center_crop；主原/有效指令逐条相等。
- 源码核对：源完整验证后选择、不改源指令或完整目标；oracle仅policy调用边界覆盖；技术暂停保留expected/missing且success=False继续；真实reset step0与query/action区间绑定；无需额外reset/render/step/predict。metrics/env/adapter/解码/RNG不改，默认all无evidence仍兼容。
- 004有效metadata版本选择与shadowed诊断不导入重模型、不声称模块字节身份，历史raw不重写。

## 实跑状态（与软件测试分开）

用户授权后，在独立目录 `/HUBU-AI096/zp/ICML/LIBERO-Remain-stage03-pilot-04508dc` 复用旧runtime、模型配置与原001。主批于北京时间2026-10-10 00:14:42启动，00:25:22结束，639.72秒/exit0。
15/15完整、invalid/runtime/missing均0，技术stop_reason=null。Code04508dc、原指令模式、原场景/camera/crop保持；model loads1、每episode独立seed/reset，不因真值成功停车。

| mask | JSR | 完整/视频 | UIR |
|---|---|---|---|
| 10 | 2/5 | 5/5 | 未人工标注=N/A |
| 01 | 5/5 | 5/5 | 未人工标注=N/A |
| 11 | 5/5 | 5/5 | 未人工标注=N/A |

独立read_run已验证全15条源/选择/模式/actual step0/query身份；原metrics逐case从trace重算一致；15段MP4实际解码帧数匹配n_steps+1（10/01各670步/671帧，11各150步/151帧）。model实际metadata.numpy1.24.4、mujoco2.3.7正常。
10来源0/3预算内成功，来源1/4窗口内未全部满足；来源2首次全满足在663步，超过H520，不作为预算内成功。15条初始成果preservation均true，不能把这批10失败称为“破坏了旧成果”。尚未确定动作目标/必要性或内部原因，不预设每个10都失败。

固定10条oracle剩余指令诊断随后另目录启动，driver PID3683999；不挑失败来源、不改状态，不混入主JSR/UIR。诊断成功是执行正证据，不是性能上界或因果证明；这份review不提前写诊断成绩。
主输出reports/stage03_primary_001；诊断reports/stage03_oracle_001；命令/PID/时间/退出记录execute_logs/stage03_partial。UIR仍待结合实际crop、可用信息和query机会完整审核；必要观察/试抓不自动判错，未完成目标执行失败不直接UIR，疑义unknown。

## 下一步操作与执行者

Codex：监测/核验诊断全10条，备份主/诊断原始产物，审查代表视频与UIR证据；不自动扩大任务、模型、seed或训练，结束后形成阶段裁决。
X：按代码accepted授权合并PR #3、记录main SHA，无新增未审实现；当前运行代码不随分支移动。原始实验/场景/UIR标签不改，不自行跑GPU或关闭科学阶段。
