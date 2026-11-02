# 033｜正式改为九个LIBERO-10复合任务，移除LIBERO-90

日期：2026-11-02。状态：open；用户已明确批准范围。实现X，审查/部署Codex，真实制备与模型评测仍由用户启动。[正式计划](../../docs/experiment_plans/2026-11-02_libero10_nine_compound_tasks.md)与本任务的033_nine_task_scope.json共同给出准确名单和A/B映射。

## 1. 优先级与取消事项

本任务覆盖旧031的未来四个90任务补齐安排：停止frypan_stove9、cabinet_close_top_bowl的未执行补建/补测，不再以其修好为前置。四个90退出新默认任务清单、计划分母、当前主报告和未来标准导出；旧源码/原始数据/分数/视频/失败证据保留为legacy。不得把取消写成“物理已修好/评测完成”，不得删除历史交流或热改旧运行目录。

032评分简化继续有效，但当前population改为九个LIBERO-10；不要先为旧6+4计划做一轮完整交付再重写九任务。可同PR集中交付032+033，或明确依赖的两个PR，不以串行审查拖延。旧报表兼容仅用于读历史，不能让已取消90任务继续进入新默认计划。

## 2. 源码与实施范围

权威实现库No1dry/LIBERO-Remain。已审031快照ac1301779cf6ae4c34ebc80c20936a4f7a4953be（PR #12；R2实现18059cb），此前013 v2支撑修复c6dc98de必须保留。main仍有未合并实现，不要假设只拉main就含完整headless，不要求自动合并历史PR。X先fetch最新main读本任务，再明确分支parent与复用代码。

复用既有catalog、selected_A_only构造、正式adapter回放、scoped planning/workflow、原OFT worker、视频与离线评分。针对新任务扩展确有必要的能力，不重构全库、不加VLM/selector/FINISH或训练。

新显式九任务版本由官方完整任务名绑定，默认task_id 0,1,2,3,4,6,7,8,9；id5单最终目标不纳入。新接口只接受libero_10，拒绝把90错标为10或回退90归一化。旧reader可保留原6+4定义，不要求破坏旧接口。新README/runbook/默认示例必须标注九任务，不得仍导向旧90补建。

## 3. 新三个任务的语义，不能误实现

### id3 bowl_drawer_close

官方KITCHEN_SCENE4_put_the_black_bowl_in_the_bottom_drawer_of_the_cabinet_and_close_it。A=In(akita_black_bowl_1, white_cabinet_1_bottom_region)，B=Close(white_cabinet_1_bottom_region)。10为物已入、下抽屉仍Open，模型只剩关闭。00采用官方原始已Open的初态，物在外。不能按官方goal中Close先书写就把A/B反过来，也不能为掩盖依赖把对象放柜顶/改为90任务。

### id8 two_pots

沿用已有key。官方KITCHEN_SCENE8_put_both_moka_pots_on_the_stove。A=On(moka_pot_1, flat_stove_1_cook_region)，B=On(moka_pot_2, flat_stove_1_cook_region)。顺序在来源生成前固定，不按模型表现交换壶。完整官方目标还含Turnon(flat_stove_1)，且官方init已满足；把它表示为invariant而不是第三个待办。

新版本的00/10 mask只覆盖active A/B；初态00为[false,false]+invariant真，10为[true,false]+invariant真。保存全部官方谓词、明确active/invariant字段与映射，整体成功与native check_success核对。不得删Turnon或故意关炉凑全false；不能把它当普通三位mask而生成01/11/8种状态。10若关闭炉子是保持条件破坏，须保留原因；00仍按官方最终成功信号，不新增过程罚分。

### id9 mug_microwave_close

官方KITCHEN_SCENE6_put_the_yellow_and_white_mug_in_the_microwave_and_close_it。A=In(white_yellow_mug_1, microwave_1_heating_region)，B=Close(microwave_1)。10为杯已入、微波炉仍Open；00官方初态微波炉已Open、杯在外。A/B不反转，不加入额外开门子目标。

以上三项均保留原完整指令和官方BDDL。不能继续因EXCLUDED_FAMILIES或旧全false假设拒绝它们；需要的是针对依赖/不变量的必要扩展，不是降低真实初态正确性标准。

## 4. 来源准备与结果复用

- 每任务官方init index0..9，policy seed7，原SOG10 revision638918f3d1c2e43a39a8a20772bdb8b91835e4b7、libero_10_no_noops、输入/裁剪/proprio/非量化、chunk8/H520不变。所有来源先固定，不挑通过或成功者，不换index填分。
- 旧六任务00/10各60条直接引用原工件和来源证据。旧00来源是a23八任务run中的六项；旧10为013离线派生与原执行raw的同六项。保留原每轨迹model/code/protocol/source/endpoint身份，不改原batch hash、task_id或原manifest伪装成九任务run。
- 支持新九任务显式reuse清单/计划：120条只读复用，60条新任务可执行。新模型默认population仅new-three，禁止意外将reuse变成待跑项。来源缺失/不兼容单列，不默默重跑；不因全局harness SHA变了强制重跑六任务。若确有影响解释的事实差异，一次具体列出，不能把所有旧证据作废。
- 新三任务只准备实际需要00/10。00复用官方固定index的settled base与实际初始观测，无额外150步hold/回放门槛；10扩展selected-A-only流程，只完成A、保持B未完成及invariant/开门约束，并用正式adapter做已有约定的独立恢复/回放验证。沿用实际需要的既定物理阈值/次数，不增加新验证阶段，不构造01/11银行。
- task3/9目标区域随关节运动，构造须按实际打开容器region放置并验证native In、Open；不只设predicate布尔或把对象固定世界坐标后冒称在抽屉内。保留真实状态、观测对应、明显非法穿透/速度和真实10检查，这些防止错初态/假任务；不得以无关掉桌检测UNKNOWN拒绝官方00。
- 所有新物理操作新目录、来源级失败隔离与账本；保持031 R2的失效ready只读continue保护，明确retry，不覆盖旧证据。构造通过和独立回放通过分别记录。用户才启动native，X/Codex只做CPU-fake与文件检查。

## 5. 终点、评分和正式分母

正式00=90、10=90；各复用60、补30，新增模型共60。暂不扩seed/01/11/FINISH、不增加预算外probe。可让新批第一条作为正式episode正常保存继续，无需额外模型smoke。状态制备步数单独记账，不冒充模型步数。

032的00官方主SR和table_drop诊断降级落到新九任务报告；00官方SR与10官方目标达成率可以同口径比，10合规SR另列，不将两种指标之差当同指标变化。任务8的官方成功必须保留Turnon；10保持A与invariant。错抓/错放对象角色来自任务目标/容器，不把门、柜子、两个壶误标干扰物。

新三任务00采用native成功即结束或H，不额外要求释放几何证书/连续5观测；旧六任务只提取已有官方成功事实，不重新执行，其旧终点如实披露。00混合终点下不汇总全轨迹路径作效率结论。新三任务10沿用已约定目标+释放连续确认终点，不因新增任务悄改该终点；若旧几何测量确实不支持新容器，仅一次给出明确错误及必要替代建议，不擅改阈值或真值。

新分母90与旧计划100严格分开；旧60/90报告覆盖66.67%不是成功率。未开始的新30不能记作模型0%失败。主表按官方task_id顺序，百分比和n/N；成功条件下TCP长度与覆盖按既定口径保留，不新增主metric。不可验证/未知/技术/未执行如实列明。视频仍用已有双相机帧，不额外推进物理/模型。

## 6. 精简测试与交付

受影响CPU/fake即可：9项准确名单排除id5/90；A/B不误映射BDDL书写序；两壶invariant完整且00并非全官方谓词false；容器10物入且门开；完整官方成功与active+invariant相符；旧六120复用不触发native/model、新60准确；90/100分母不混；032按事件类型降掉桌而不删除其他违规；失败/中断不覆盖旧工件、模型看不到mask/谓词/接触真值。复用已有测试，不以全库、多平台或GPU测例为交付门槛。

交独立PR与collaboration/responses/033_round1.md：实现SHA、改动范围、实际CPU/fake结果、可复制来源盘点/只补新三任务制备/评测/汇总CLI与配置模板、新旧结果复用方式、未完成事项。CLI flags必须真实存在，Codex部署后补准确服务器路径和常用python命令；不让用户填hash/手改路径。

源实现验收后，对外No1dry/LIBERO-Remain-Eval须从同一版本导出九任务清单/必要代码与runbook，X交同步内容清单/可复用导出方式，不先人工维护第二套实现作为本轮开跑前置。此刻不能说Eval库已更新。方法库仅同步范围/链接，不复制实现。

本任务是完整目标，不追加MVP阶段或逐项人工视频放行。只保留能防本轮错范围、错初态、真值泄漏、错计分和数据覆盖的检查。旧031代码与历史结果不删除、不自动merge、不运行真实实验或训练。
