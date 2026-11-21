# Semantier Thinking — 渐进式思辨技能

[English README](README.md)

**源码版本：** 0.1.2  
**技能标识：** `semantier/semantier/semantier-thinking`  
**Hermes 安装名称：** `semantier--semantier-thinking`  
**著作权：** Semantier Technology，详见 [LICENSE](LICENSE)。

这是面向认知、决策、论证与写作的通用思辨技能。它不是“永远质疑”的聊天机器人，也不要求每次都进行冗长的审计；其目标是协助形成**证据可查、推断有据、价值前提清楚且可以随新证据修正**的判断。

## 中文与中英混合支持

- 默认使用用户当前请求的语言回答：**中文提问 → 中文回答；英文提问 → 英文回答**。明确指定输出语言时，以该要求为准。
- 中文问题引用英文文献、报告或数据时，**正文用中文，原始引文、来源位置、数字、日期与专有名称原样保留**；不得把翻译后的话冒充原文。
- 输入中英混排时，根据用户真正提出问题或下达指令的语言确定默认输出语言，而不是被英文材料“带跑”。
- 解释重要概念时采用自然中文；有必要时第一次给出英文术语，例如**假设（assumption）**、**推断（inference）**、**论证担保（warrant）**、**反证（counterevidence）**、**可证伪条件（falsification condition）**。
- 中英表达的同一任务应维持相同的任务路由、审计深度、证据门槛与停止条件。翻译不应自动放宽事实和伦理标准。

语言细则与术语表见 [中文／多语言参考](references/language-and-terminology.md)。

## 能力与选择方式

主编排 Skill 按用户真正需要交付的结果选择**一个主导任务**：

| 任务 | 核心问题 |
| --- | --- |
| 认知与查证 | 这是真的吗？证据能支持到什么程度？ |
| 决策推理 | 在约束、风险与价值取舍下应该如何行动？ |
| 论证与写作 | 如何在不夸大证据的情况下形成合理主张并交付文本？ |

**伦理推理**（权利、义务、公平和价值冲突）、**组织思维**（激励、权力、群体偏差、反馈机制）仅在相关问题确实影响结论时按需加载。

| 深度 | 意义 |
| --- | --- |
| L0 | 直接完成，无需形式化审计 |
| L1 | 轻量检查一个关键前提或推断 |
| L2 | 结构化分析证据、假设、替代解释与不确定性 |
| L3 | 深度审计重要依据、强反例、后果和改判条件 |

**Deliver（交付）**与**Coach（引导练习）**是独立于深度的模式。Coach 通常每轮只问一个真正有辨别力的问题；用户希望直接得到成果时，不强制进行教学。发现新证据后，可升级或降低审计深度，避免重复工作。

若研究或执行中途出现足以改变归因的质疑，可按需使用[归因与修订流程](references/diagnostic-revision.md)：区分原始结果与解释，选择一项有辨别力的检查，将机械修复交回原专业能力，再根据返回证据修订结论。它不替代普通调试，不改写历史结果，也不自动晋升元学习方法。

## 使用示例

- “团队用 AI 后产出上升，但同时加强了培训。我们可以声称 AI 造成了提升吗？”
- “两个方案都可行，但预算是硬约束。比较总成本、风险和可逆性。”
- “审计这份英文报告的主张与来源，用中文写出审查意见；保留英文引文。”
- “请帮我练习思辨：先问我一个能改变结论的关键问题。”
- “这项组织政策虽然合法，但会侵害员工知情权吗？是否存在激励扭曲？”

## 目录、运行和测试

- [SKILL.md](SKILL.md)：供模型加载的简短主入口与硬性边界。
- [深度路由](references/depth-routing.md)：渐进计划、升级、降级与停止。
- [认知查证](references/critical-inquiry.md)、[决策推理](references/decision-reasoning.md)、[论证写作](references/argument-writing.md)：三个主任务。
- [伦理推理](references/ethical-reasoning.md)、[组织思维](references/organizational-reasoning.md)：两个专项方法。
- [证据交接](references/evidence-handoff.md)：跨模块保留证据状态、假设、反证与未知。
- [评测说明](evals/README.md)：英文／中文／混合语言用例、可选模型对照及 FOLIO。

从 `semantier-skills` 仓库根目录执行确定性测试：

```sh
python3 -m unittest discover -s skills/semantier-thinking/evals -p 'test_*.py' -v
```

此命令检验源码契约、场景覆盖、评测适配器及输入输出格式，**不是实际模型推理效果测试**。真正的语言一致性、Coach 行为、推断准确率与跨语言稳定性仍需通过已授权模型驱动器取得观察结果；没有运行模型不得宣称性能提升。

## 官方市场发布状态

此 GitHub 目录是**技能源码**，不代表已经签名上架。计划中的 Semantier Official Catalog 为 `https://assets.semantier.cn/skills/v1/catalog.json`，正式发布尚需生产密钥准入、完整文件清单、不可变 OSS 包、有效签名、HTTPS 读回与原生 Windows 安装验收。

旧 `marketplace/index.json` 属于插件目录，不应将这里的 Skill 当作 Plugin 发布。Hermes 安全扫描、用户显式授权和来源锁定不因“官方”名称而放宽。
