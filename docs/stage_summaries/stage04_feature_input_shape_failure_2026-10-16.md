# Stage04：首次真实特征导出被7/8维证据合同错误阻塞

2026-10-16。用户启动冻结2cb1428的04_features，模型已加载（model_loads=1），导出status=error/completed=false、cache_path=null，exit2/tee0，无完整cache/cache.json；不可进入训练。错误为unexpected OFT proprio/pixel tensor shape。原forward可能已返回，未有可靠成功forward计数，不能报0或1261次已完成，也不是模型能力失败率。

已确认根因是finish/schema.py:97把proprio限定为7，而实际固定LIBERO-OFT由3位置+3旋转+2手指构成8维；官方projector=8及checkpoint dataset_statistics的libero10统计向量8均佐证。已有真实观测pos3/quat4/gripper2。两相机fused像素12通道不是当前rank4/5检查的异常原因；动作输出维才是7，chunk仍8×7。

[给X的R8最小修复要求](../../collaboration/reviews/008_round8.md)只修输入证据合同与真实形状fake/往返测试，不更改、截断、补零或reshape实际模型输入，不改预处理/网络/权重/动作/标签/指标。Codex与独立审查只读源码/config、NumPy合成测试，没有追加真实模型或native作业。[精简证据](evidence/stage04_feature_input_shape_2026-10-16.json)记录实际代码SHA与4格复现。

首次源config诊断错误地从基础config.json查询libero_10_no_noops，得到查询KeyError；随后只读正确dataset_statistics.json，实际四个LIBERO域的proprio统计均8。这个查询错误不是项目新增故障，不与用户导出错误混淆。

## 原成功审计不受影响

1313帧真实audit已完成并只读验收，内部audit SHA44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457；已知1261/unknown52、train23正/val2正（同demo_38）保持。**不重新跑audit，不重新采集/标注，不改split**。修复部署后新feature out/log显式引用原成功audit，由用户仅重导出feature。

原失败report服务器路径stage04_finish_2cb1428/results/run01/features/feature_export.json，SHA c0db3c91c5b9c507292c2348fa1bdf11e8f5e12d77f9d981fb10161443190d8b；log位于logs/run01/04_features.log，SHA8b5d82683cb0abcadc9f7d93fcb3383f4a3306c122815e5bba1178d0ef5c9313。两份已下载本地项目reports/stage04_feature_shape_failure_2026-10-16/evidence/且与服务器SHA一致；partial不删除或复用成成功缓存。

当前没有finish head、parity、normal校准或新eval结果；30条模型rollout预算未消耗，feature forward费用另计。R7模型兼容与成功数据审计结论保留，不能把feature采集器错误算模型差或数据不足。

下一步X交R8修复→Codex验收/新部署并复核原audit→用户新feature输出→完整cache复核后小头训练。此前一次有限native诊断授权不扩展到自动VLA作业；角色仍不变。008/Stage04未closed，精确待删=[]。总结/审查/证据/STATUS/运行说明提交并按README本地来源commit与SHA归档，无删除。
