# 给 X：006 完成状态的观测证据闸门（先诊断/方案，不直接改主协议）

日期：2026-10-09。作者：Codex。状态：open。阶段：Stage03，主VLA批前置审查。
代码由X实现；真实状态/渲染与模型实验由Codex执行。该任务不增加主metric、不训练，不按VLA失败筛状态。

## 发现与证据

固定5来源的20状态和40次独立150-step回放全部技术通过，但不等于完成状态可观察。
Codex已读step0 NPZ双相机，并在模型Python中复用真实adapter调用链：
`_raw_observation(wrist=True, proprio=True)` → `prepare_observation/get_image_resize_size` → `prepare_images_for_vla(center_crop=True)`。
无policy、权重或HF processor加载；以下是HF processor前RGB，不声称最终encoder tensors。
源manifest文件SHA-256 `50c557f087783d7aa346992f4449dc81c1c59302e8850b3a3bee1c820c18797d`；OFT helper源码SHA-256 `eed754d7c5f9821aae2fe0531dbe01df8c11df0d5c79b4aeeb9bb4452124bdf5`。

初态0，左agentview、右wrist，原始模型视图内容，无箭头/真值标记：

![10](../../docs/experiment_plans/assets/stage03_source0_10_model_rgb.png)
![01](../../docs/experiment_plans/assets/stage03_source0_01_model_rgb.png)
![11](../../docs/experiment_plans/assets/stage03_source0_11_model_rgb.png)

已完成物体位于篮子中，但篮子在主视角边缘且内容物遮挡，腕部初始视角未清楚覆盖内部。图中明显变化是桌面上相应物体缺失；尚不能仅凭此认证“完成目标在当前传感器中可辨认”。
这不是已证明不可观察，也不直接判整个bank无效：用户允许合理主动观察。需要可辨认的观测证据或允许的非破坏观察轨迹，不能把静态mask真值等同于模型可获知的状态。

## 交付一：诊断与最小方案

在 `responses/006_round1.md` 说明：现有布局/camera/crop是否产生严重遮挡；如何绑定每个mask/goal到实际输入；哪些可以初始识别，哪些需要主动观察，哪些unknown。
只凭看到物体从桌面消失、不碰对象或技术audit不能自动证明完成状态可识别；不自行设置任意像素阈值盖合法章。
可提出以下任一路径，先由Codex审方案：

1. 在原已完成目标编辑白名单内选择更清晰、仍满足原官方谓词/物理稳定/相同配对组件的摆放候选；或者
2. 给出可复制的、有限步、不破坏初始成果的纯观察控制证据，使现有真实传感器能看到完成状态。此为state观测可行性诊断，不是主模型获得的oracle动作，更不能先给主模型执行这条轨迹再冒称原始起点。

完成物体可观察与剩余任务可执行是两个独立闸门。005的oracle执行成功只证明执行正例，不能替代这里的可观察性证据。

## 禁止和实现边界

- 不改变主模型的camera、center_crop、processor、checkpoint、原完整指令，不插入mask/标记/分割真值到模型输入。
- 不移动背景、容器、机器人起点去救一组，再声称仍是原配对状态；这些变更若必须做，先明确报告并重新设计对照，不能自动授权。
- 不读取被测VLA的成功率决定选择哪些候选；不丢失败来源或增加容易index。
- 不改旧run/manifest/replay/截图；旧001证据保留。改候选后新目录重建并重做完整四mask构造/回放/视觉审查。
- 如需代码，最小只读预览或可审查构造/纯观察诊断入口，CPU/fake测试并独立commit/PR；X不在GPU上跑，不自行合并。
- Codex批准方案后才进行实际单来源准备验证；成功后再固定0..4，不能未经审查无限尝试或启动主VLA批。

完成此任务和005验收、剩余执行证据后，Codex启动Plan3限定主pilot。UIR仍人工审核，主表仍只有JSR/UIR。
