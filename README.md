# The Gemma 4 Good Hackathon

> **Kaggle Gemma 4 Good Hackathon** 参赛项目。
> 截止日期:**2026-05-18** · 奖池:$200K · 评审维度:Vision / Technical Execution / Impact / Reproducibility

## 项目定位

**双目标叠加**:
1. **真目标**:借 hackathon 落地一个通用的 **agent 框架**(核心学习目标)
2. **载体目标**:做一个符合 hackathon 约束的产品——**本地实时翻译工具 + 被动涌现学习**

方向命中 hackathon 的硬约束:**education** 方向 + **offline / privacy / low-bandwidth** 场景要素。

## 一句话产品宗旨

> 这个 agent **首先是一个实时本地翻译工具**。学习是**被动涌现**的副产品——只有当翻译内容积累到一定程度、出现重复或模式时,才浮现出可学习的素材。

**90% 翻译器 · 7% 轻触 · 2% 主动收获 · 1% 背景自主**

评审印象点:"agent 知道何时不说话"。

## 仓库结构

```
The-Gemma-4-Good-Hackathon/
├── README.md          ← 本文件,项目导览
├── DESIGN.md          ← 产品设计决策(选题/宗旨/约束对齐)
├── ARCHITECTURE.md    ← 技术架构(六层 agent 框架/三层解耦/技术栈)
├── .gitignore
├── core/              ← Python agent 主体(75% 时间投入)
├── cli/               ← Python CLI 客户端(开发调试用)
├── android/           ← Kotlin shell(20% 时间;仅 UI + 相机/麦 + 本地 runtime + HTTP client)
├── bench/             ← 评估脚本 + 性能测试
├── demo/              ← Demo 视频 / 演示脚本 / 评审材料
└── docs/              ← 扩展文档
```

## 时间分配基线

```
 Week 1-2  ████████████  Python Agent Core(agent 黄金学习期)
 Week 3    ████          Android shell + 集成
 Week 4    ████          打磨 + demo 录制 + 提交
```

## 当前状态

- [x] 选题敲定(2026-04-16)
- [x] 产品宗旨敲定(2026-04-17)
- [x] Agent 框架六层设计敲定(2026-04-17)
- [x] 三层解耦架构敲定(2026-04-17)
- [x] 设计文档入库(2026-04-20)
- [ ] Agent Core 骨架搭建
- [ ] Runtime 抽象(MockRuntime → LlamaCppRuntime → MediaPipeRuntime)
- [ ] Memory 分层实现(drawers → candidates → cards)
- [ ] 翻译主循环打通
- [ ] Android shell fork(从 Google AI Edge Gallery)
- [ ] 端到端集成
- [ ] Demo 素材
- [ ] 提交

## 关键参考

- **Gemma 4 能力**:128K context · native function calling · reasoning mode · text+image+audio 多模态 · 35+ 语言开箱 · 边缘部署(手机 / Pi 级)
- **Android 脚手架**:fork [Google AI Edge Gallery](https://github.com/google-ai-edge/gallery)(Kotlin,含 Function Calling Guide)
- **Agent 框架借鉴**:`openclaw/` · `hermes-agent/` · `claw-code-main/`(均在 `../` 同级目录)

详见 [DESIGN.md](DESIGN.md) 和 [ARCHITECTURE.md](ARCHITECTURE.md)。
