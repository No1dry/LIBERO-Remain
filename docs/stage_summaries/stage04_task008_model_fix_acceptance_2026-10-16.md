# Stage04：008 R6示范模型受限兼容验收与部署

2026-10-16。[R7软件裁决](../../collaboration/reviews/008_round7.md)accepted，无进一步返修；008/Stage04未closed。X只改代码，Codex本轮只CPU/fake与纯文件准备/部署；前次有限native诊断授权没有被扩大，用户仍亲自启动真实audit/标签/VLA/训练。

## 固定交付与独立测试

PR #5已测试实现b26497959839f79d2d5f2790c2da95d949347102；最终冻结2cb1428f312175968ac42449994c219e94e9ab14（tree ad11cec8a6cec508969c11b84efef61bf1f64581），其后只有STATUS/response文档。250源码逐Git blob及SHA核验；旧工作区不动。

仅finish/demo_model.py、environment.py、data.py变更。固定来源+唯一已核额外geom+完整残余布局/匿名项+mesh和相机/引用绑定；保留原HDF/XML/碰撞体，不改eval/source001，不改label/hold/网络/阈值/指标。物理等价声明仍false。最终动态证据随audit身份进cache/head，不进policy输入。

本地全套1766 passed/12既有可选skip（55.56秒）；新增78 passed（3.24秒）；并行独立87/135 passed；服务器22个FINISH文件535 passed/0 skipped（70.51秒）。本地12 skip为11个可选catalog源码检查+1个imageio_ffmpeg缺失，无新增skip。测试始于2026-10-15、部署归档跨至16日，项目reports目录仍保留启动日名称。

## 实际文件准备与新目录

- 源码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-2cb1428`。
- 会话/配置/结果根：`/HUBU-AI096/zp/ICML/stage04_finish_2cb1428`。
- 250源码+9冻结部署文件核验，沿用同一runtime/venv、HDF/init/BDDL、OFT checkpoint/patch/crop/seed/chunk；服务器曾短暂拒绝，用户恢复后部署成功。
- 真HDF纯文件register-data：50/50 XML、4450/4450引用（100%）、87唯一路径，errors0、resolved；仍非ready/labels0。
- 额外纯文件核验实际三源SHA、profile、原XML真实50成员、processed仅资源变换、link7 mesh完整suffix/SHA；真实旧layout JSON重放与生产baseline hash一致，唯一插入过滤副本保留7匿名项。没有为核验再编译/创建native环境，不把回放当实际新guard物理通过。
- 预定真实audit仍同一1313采样帧（train1115/validation198），没有增采、下载或独立预检。尚未创建新audit结果目录。

核心hash：源码tar b45f36a3c5210edad158ced3babf01dec7ba54cfc200b3d966543acdb0afffe2；部署tar 4be8a4abce00c354c422e888eb522ca7ed6fa8d515cb98b6e57a1fff6ed0ee62；配置manifest45f4b6f33fc7f23414589f8acb2f806e1beb237c9255390a691c6bda9a0cff6f；原OFT runtime仍75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720。scan语义SHA44d7a1c4cddb523fbda475bb16d4d28d3f8ab326790685977eb1ebacfed11f07，来源registry语义f8706e9018e618566f53165b50b8e21e6347c089a500cbe3bc21c0930ff8edfe，数据分组与资产未变。

服务器JUnit、registry、registration、完整XML scan、02_registry和02b来源核验日志共6文件已下载项目reports/stage04_task008_model_fix_2026-10-15/evidence/，逐SHA与服务器一致，deployment_receipt.json完整记录。本地JUnit/源码/配置清单和纯文件核验脚本同目录。服务器JUnit SHA96ec41d3b06f30609a6c808fa8204cad2f42cf118b140c9930c1e4319a11af68；来源核验日志SHA8e3fcb7a0a5f424bca345e12f8b5ad417838e0cf6f4310003eb0bd61939c8a0c。

## 后续与不能声称

[新会话完整命令](../experiment_plans/stage04_task008_model_server_runbook_2026-10-16.md)。用户仅重跑原audit，新out/log；Codex读实际标签/unknown、帧/来源覆盖、最终变体与重绑证据，充分才进入feature/训练。不自动串联。

本轮软件/实际文件通过不保证1313帧恢复/release/K4/正负类充分，不声称新native模型验证已完成；没有真实新labels/feature/head/parity/calibration/eval或视频。head原生模型与eval模型域差异、历史作者资产字节/跨域物理祖源未证明仍须披露，不能把未来失败全部归于remaining重判定。默认模型30rollout预算未消耗。

解除R6合并暂停，X可保持已审实现及最新协议/Plan4/STATUS/R1..R7与历史证据合并PR并登记，Codex不代合并。旧38/4f/b596/9ddd/089及全部失败/诊断保留，007/008及Stage04未closed，精确待删=[]。验收/总结/命令/STATUS发布后本地按来源commit及SHA核验归档，无删除。
