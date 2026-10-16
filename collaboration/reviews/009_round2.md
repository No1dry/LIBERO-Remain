# Codex：009 Round 2——真实292步诊断验收与010新需求

2026-10-16。**用户真实诊断accepted，009授权的最小诊断范围完成/closed；Stage04未closed。** PR #6已审代码可由X合并并保留本结果/010文档，Codex不代merge；未合并前仍保留全部相关交流。本轮无额外物理步、NN或训练。

## 完整性和预算

- 用户292/292原动作完成（100%）、293/293旧truth逐bit匹配、37/37原query观测hash匹配（100%），无first_mismatch/错误/清理异常，exit0/tee0。
- manifest882条逐SHA/大小验证；连manifest共883原始文件、57,650,960 bytes完整本地备份。static+293帧共294 typed NPZ验证dtype/shape/content hash；294份只读before=after，hooks已恢复。
- action期7300次mj_step=292×25，time约4.0→18.6秒，推进14.6秒；recorder只588 stateSize+588 getState，无时间推进。初始化2次mj_step1/12 forward单列，Python入口计数不冒充全部C内部调用。
- VLA/head/processor均0；没有step293、没有step292 query、没有FINISH/hold/W150/init37。source plan/model XML/7源码SHA均与冻结2c6dc4c相符。Codex只读文件及NumPy分析，无native/NN。

## 关键发现：球界过松的具体分离证书

第280步两目标入篮，旧truth仍release=None，番茄无grasp/contact，旧sphere=-23.432829mm、pinch=+14.681542mm。最小球对为tomato_sauce_1_g5（box,id110）与gripper0_hand_collision（mesh,id74）。掌部mesh虽沿xy展开，119.06mm球界向各方向膨胀，导致球重叠。

用已保存的compiled collision box/mesh及world geom pose作线性轴投影：
- 全部24个番茄geom的最高z=0.6059793995932582m；
- 全部5个hand geom最低z=0.6207082402955947m；
- 故两个collision集合world-z间隙下界0.014728840702336488m，保守向下报≥14.72mm；汤罐相应≥90.69mm。
- 225个target-hand mask组合均兼容、显式pair/exclude为空，margin/gap0；29个既有contact中目标-hand对0。不是通过关碰撞制造无接触。

这是保守分离下界，不是精确最短距离，也不是已恢复原全部隐状态的证明。公式用box旋转半尺寸投影、mesh编译顶点的线性投影覆盖凸包；与固定[2.3.7 collision support](https://github.com/google-deepmind/mujoco/blob/2.3.7/src/engine/engine_collision_convex.c)一致。原query/truth均匹配的新重放侧录支持该帧球包络过保守；不能泛化所有unknown或直接翻旧label/阈值。

## 新授权和决策

原release None、旧calibrated=false/threshold=null与分数不改，009没有认证280后FINISH/W150。用户现已明确“同意版本化修订”：发布[010](../tasks/010_versioned_release_and_calibration.md)，用更紧保守证书补充测量，校准按first-hit及tau时机可判定证据；保留旧版、不重训，另采5条新版校准，累计模型预算35。不是009返修，也不是悄改旧实验。

X现在实现010独立代码/CPU-fake/PR，Codex审查部署，用户再启动新的5条。当前没有新运行命令，不重跑009、不直接normal_active或Remain。具体几何限制、鲁棒tau、版本读写/旧头合同、2×2敏感性与预算在010一次说明，不为风格反复返修。

[长期结果/授权总结](../../docs/stage_summaries/stage04_task009_result_and_revision_2026-10-16.md)／[机器证据](../../docs/stage_summaries/evidence/stage04_task009_result_2026-10-16.json)。原始工件完整备份来源与SHA核对；原shadow视频/input树未因此全量复制。所有旧数据/脏工作区保留，010 open、Stage04未closed，精确待删=[]。
