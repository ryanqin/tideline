# DESIGN — 产品设计决策

> 本文件固化**产品层**的关键拍板。技术实现见 [ARCHITECTURE.md](ARCHITECTURE.md)。

---

## 1. Hackathon 硬约束(2026-04-16 核实自 Kaggle 官方)

| 约束 | 要求 |
|---|---|
| 方向 | 必须是 **health / education / climate** 之一 |
| 场景 | 必须体现至少一项:**低带宽 / 离线可用 / 隐私优先 / 基础设施缺失地区** |
| 评审维度 | Vision / Technical Execution / Impact / Reproducibility(四维) |
| 权重偏向 | 真实问题 + 可演示功能 + 清晰用例 |

Kaggle 原话举例:
> offline educational tools for rural classrooms, privacy-preserving medical diagnostic assistants, decentralized energy solutions

---

## 2. 选题(2026-04-16 收敛)

### **本地实时翻译工具 + 被动涌现的语言学习**

命中点:
- **education** 方向 ✓
- **offline** + **privacy** + **low-bandwidth** 同时命中 ✓(翻译场景天然需要三者)
- 真实用户画像清晰:出国工作 / 留学 / 移民家庭 / 语言学习者

---

## 3. 产品宗旨(2026-04-17 用户拍板)

> **这个 agent 首先是一个实时本地翻译工具。学习是被动涌现的副产品——只有当翻译内容积累到一定程度、出现重复或模式时,才浮现出可学习的素材。**

这是**设计原则**,不是实现细节。所有功能决策需要对齐这一条。

### 落地规则

- **默认 UI/交互 = 翻译器**,不要给每次查词绑定"学习动作"
  - ✗ 弹建卡确认
  - ✗ 强推 SRS
  - ✗ 每次翻译后跳转"学习路径"
- **每次翻译都写入 `drawers`**(episodic 沉淀层),绝大多数 drawer **永远停在这一层**不升级
- **只有跨过阈值**才晋级到 `candidates`,再由用户点头才成为 `cards`(进 SRS)
  - 阈值三类:重复频次 / 语义聚类 / 用户显式信号
- **背景"守夜人"扫描**做静默聚类与候选生成,**不 push 通知**
  - 等用户主动问"最近怎么样"才 surface

### Demo 叙事线

> **"90% 时间它就是个翻译器,7% 轻触,2% 主动收获,1% 背景自主"**

评审印象点:**"agent 知道何时不说话"**——这是对"智能体"而不是"功能堆叠"的审美表达。

---

## 4. 为什么是 Gemma 4(而不是其他模型)

| 约束 | 为什么 Gemma 4 满足 |
|---|---|
| 无需 post-training(我不会也没算力) | E2B/E4B 开箱即用 |
| 本地可跑、省成本 | 手机 / Raspberry Pi 级硬件即可 |
| Agent 框架必备能力 | **Native function calling**(官方定位 agentic workflows) |
| 多模态输入 | text + image + native audio |
| 长上下文 | 128K |
| 推理能力 | 内置 reasoning mode(step-by-step) |
| 多语言 | 35+ 语言开箱,140+ 预训练 |

---

## 5. 输入优先级(2026-04-17 确认)

```
 📷 图片      ← 最高优先级(菜单 / 标牌 / 文档)
   ↓
 🎤 语音      ← 次优先级(对话 / 实时翻译)
   ↓
 ⌨ 文本      ← 兜底(主动查词)
```

**为什么这个顺序**:翻译场景里,用户最常遇到的是**"看到一个看不懂的东西"**——图片是第一反应;"听到"次之;"主动输入"只在前两者不便时才发生。

---

## 6. 目标平台

### Android **唯一**(iOS 暂不做)

| 平台 | 默认模型 | 场景 |
|---|---|---|
| Android | **E2B** | 中档机 24-30 t/s,兼容性好 |
| Android | E4B | 性能高挡位,多模态+复杂推理时切换 |

iOS 不做的理由:时间预算不够,且 MediaPipe / LiteRT-LM 在 Android 链路更成熟。

---

## 7. 评审四维对标

| 评审维度 | 本项目打点 |
|---|---|
| **Vision** | "agent 知道何时不说话" 的克制美学 + 翻译→学习的无缝渐进 |
| **Technical Execution** | 六层 agent 框架 + Runtime 抽象 + Memory 分层 + temporal KG |
| **Impact** | 语言学习者的真实痛点;离线场景覆盖基础设施缺失地区 |
| **Reproducibility** | **Agent Core 纯 Python,`pip install .` 即可跑**;Android 是可选 shell |

**Reproducibility 是隐藏加分项**:很多 hackathon 项目评审跑不起来就 0 分。我们的 Core-Android 解耦保证评审**不需要 Android 设备**也能验证核心 agent。

---

## 8. 核心架构原则:Core 与 Android **彻底解耦**

> **(2026-04-17 用户拍板,极重要)**

### Why

> 真正的学习目标是 **agent 框架**,hackathon 只是载体。如果 agent 代码和 Android 代码拧在一起,会有 40% 时间耗在 Kotlin / UI / MediaPipe 配置上,**偏离学习目标**;且将来 agent 无法搬到其他项目复用。

### How to apply

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│   Agent Core (Python)  ←──── HTTP/JSON ────→  Clients  │
│                                                        │
│   "不知道自己跑在哪"              ├─ CLI (Python)      │
│                                   ├─ Android shell     │
│   通过抽象接口解耦:                └─ Web playground   │
│     - ModelRuntime                                     │
│       (LlamaCpp / MediaPipe / Mock)                   │
│     - InputSource                                      │
│       (CLI / HTTP / Android)                          │
│                                                        │
└────────────────────────────────────────────────────────┘
```

- Core 和 client 是**对称关系**,不存在"主 client"
- 同一套 agent 逻辑,CLI 和手机跑完全一样
- Android 只负责:**UI + 相机/麦克风捕获 + 本地 E4B runtime + HTTP 客户端**
- 评审可选 `pip install .` + CLI demo,**不需要 Android 设备**

### 时间预算保护

```
 Week 1-2: 100% Python core        ← agent 框架黄金学习期
 Week 3:   开始碰 Android shell    ← 有完整可用 core 之后才碰 Kotlin
 Week 4:   打磨 + demo 录制        ← 不再动架构
```

如果 Week 3 发现 Android 超预期,**果断砍 Android,只交 CLI + core** 也能 reproducibility 满分。

---

## 9. 决策变更记录

| 日期 | 决定 | 备注 |
|---|---|---|
| 2026-04-16 | 选定 Gemma 4 Good Hackathon 作为载体 | 新建 repo |
| 2026-04-16 | 选题:翻译器 + 被动涌现学习 | 命中三项场景约束 |
| 2026-04-17 | 产品宗旨拍板:"翻译器优先,学习是副产品" | Demo 叙事线 |
| 2026-04-17 | Android 唯一平台,默认 E2B | iOS 砍掉 |
| 2026-04-17 | Core 与 Android 彻底解耦(三层架构) | 保护 agent 学习时间 |
| 2026-04-20 | 设计文档入库 | 本次 commit |
