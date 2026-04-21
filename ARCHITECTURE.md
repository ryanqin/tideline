# ARCHITECTURE — 技术架构

> 产品决策见 [DESIGN.md](DESIGN.md)。本文件聚焦**技术实现骨架**。

---

## 1. 三层部署架构(最高层)

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│    ┌──────────────┐                                        │
│    │ Agent Core   │  ←───── HTTP/JSON ─────┐               │
│    │ (Python)     │                        │               │
│    │              │                        ├── CLI         │
│    │  六层框架    │                        │   (dev/debug) │
│    │  内生        │                        │               │
│    └──────────────┘                        ├── Android     │
│         ↑                                  │   shell       │
│         │                                  │   (生产)      │
│    ┌────┴─────────────┐                    │               │
│    │ ModelRuntime 接口 │                   └── Web play    │
│    │  ├ LlamaCpp      │                      (评审备用)    │
│    │  ├ MediaPipe     │                                    │
│    │  └ Mock          │                                    │
│    └──────────────────┘                                    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**两个关键抽象接口**:
- `ModelRuntime` — 多 runtime 挂载(llama.cpp / MediaPipe / Mock for testing)
- `InputSource` — 输入源多态(CLI stdin / HTTP request / Android 捕获)

---

## 2. Agent 框架六层(核心学习目标)

```
┌──────────────────────────────────────────────────────────┐
│  L6  Rules-as-Data (v2)                                  │
│      阈值规则写 rules/*.md,hot-reload                    │
├──────────────────────────────────────────────────────────┤
│  L5  Delivery / Events 双通道                            │
│      Delivery → 用户可见输出                             │
│      Events   → Inspector View / 调试流                  │
├──────────────────────────────────────────────────────────┤
│  L4  Memory Tools(memory-as-tools)                       │
│      agent 通过 add_drawer/promote_candidate 显式决定记什么│
│      不走 harness 预注入                                 │
├──────────────────────────────────────────────────────────┤
│  L3  Orchestrator                                        │
│      turn-based loop + token 预算节流                    │
│      ToolPermissionContext(deny_names / deny_prefixes)   │
├──────────────────────────────────────────────────────────┤
│  L2  Tool System                                         │
│      capability-indexed registry(按能力类索引,非 plugin id)│
├──────────────────────────────────────────────────────────┤
│  L1  Runtime Abstraction                                 │
│      ModelRuntime 接口(5-8 方法上限)                    │
│      provider fallback chain                             │
└──────────────────────────────────────────────────────────┘
```

**为什么是六层**:每一层都有**明确的职责边界**,且可以独立测试 / 替换 / 讲解——方便讲给评审看清楚"框架感"。

---

## 3. Memory 分层(L0-L3)

```
┌────────────────────────────────────────────────────┐
│ L0  身份                                           │
│     不变的用户画像(母语 / 学习目标语言 / 水平)   │
├────────────────────────────────────────────────────┤
│ L1  公告栏(critical facts)                       │
│     ~170 tokens 自动注入每次 prompt                │
│     存:当前学习中的 candidates / 最近异常模式     │
├────────────────────────────────────────────────────┤
│ L2  Session 工作记忆                               │
│     本次对话内的短期上下文                         │
├────────────────────────────────────────────────────┤
│ L3  图书馆(长期记忆)                             │
│   ┌──────────────┐   ┌─────────────────┐           │
│   │ drawers      │→→→│ candidates      │           │
│   │ verbatim     │   │ 聚类/阈值通过的 │           │
│   │ 99% 留在此层 │   └────────┬────────┘           │
│   └──────────────┘            ↓ 用户点头            │
│                      ┌─────────────────┐           │
│                      │ cards (SRS)     │           │
│                      │ 进复习曲线      │           │
│                      └─────────────────┘           │
└────────────────────────────────────────────────────┘
```

**SRS 只服务已晋级 cards**——`drawers` / `candidates` 不进复习系统,保证大多数沉淀对用户**完全静默**。

---

## 4. 数据层技术栈

| 组件 | 用途 |
|---|---|
| **ChromaDB** | 存 verbatim drawers,语义搜索底座 |
| **SQLite** | 结构化表:drawers / candidates / cards / rooms / sessions |
| **Temporal KG** | 带 `valid_from / valid_to` 的三元组(时序知识图谱) |
| **SentencePiece** | Gemma 真 tokenizer(**不用 word-split 估算**) |

---

## 5. 三大借鉴(站在巨人肩膀上)

### 从 **OpenClaw** 借
- ✓ **Capability-indexed tool registry**:工具按**能力类**索引(如 `search` / `translate`),而不是 plugin id
- ✓ **Delivery vs Events 双通道**:用户输出和调试流分开

### 从 **Hermes** 借(最关键,和我们产品宗旨最契合)
- ✓ **Memory-as-tools**:agent 自己决定记什么,用 `add_drawer` 等工具显式操作
  - *Why 匹配*:产品宗旨要求"静默沉淀",agent 必须有**主动**的记忆权
- ✓ **Skills / rules as markdown data**:阈值规则写 `rules/*.md`,支持 hot-reload
- ✓ **Provider fallback chain**:单一入口按优先级尝试多 runtime

### 从 **Claw-code** 借
- ✓ **Turn-based loop + token 预算节流**:比简单 `max_turns` 更精细
- ✓ **ToolPermissionContext**:`deny_names` / `deny_prefixes` 作为无状态谓词
  - *Why*:测试模式和 demo 模式切换友好(禁危险工具,白盒调试)

### 借鉴范围的**具体代码**
| 原项目文件 | 借用策略 |
|---|---|
| `mempalace/knowledge_graph.py` | 几乎原样 |
| `mempalace/searcher.py` | 改造 |
| `mempalace/layers.py` | 改造 |
| `mempalace/palace_graph.py` | 参考 |
| AAAK / conversation mining CLI | **不借** |

---

## 6. 主动避开的坑(踩过别人踩过的雷)

| 坑 | 本项目的防范 |
|---|---|
| Hermes 594KB 单文件 | **强制 <500 行/文件**,CI 检查 |
| OpenClaw 40+ provider hooks | **ModelRuntime 接口 5-8 方法上限** |
| OpenClaw 5 层 retry in orchestrator | **Retry 下沉到 runtime 层** |
| Claw-code word-split token 估算 | 用 **Gemma sentencepiece 真 tokenizer** |

---

## 7. 仓库结构详解

```
The-Gemma-4-Good-Hackathon/
│
├── core/                      ← Python Agent 主体(75% 时间)
│   ├── src/gemma_agent/
│   │   ├── runtime/           ← L1: ModelRuntime + impls
│   │   │   ├── base.py        ← 接口定义
│   │   │   ├── llama_cpp.py
│   │   │   ├── mediapipe.py
│   │   │   └── mock.py        ← 测试用
│   │   ├── tools/             ← L2: capability-indexed registry
│   │   │   ├── registry.py
│   │   │   ├── memory_tools.py  ← L4 的具体工具实现
│   │   │   └── translate.py
│   │   ├── orchestrator/      ← L3: turn-based loop
│   │   ├── memory/            ← Memory 分层 + ChromaDB + SQLite
│   │   ├── rules/             ← L6: hot-reload 的 markdown rules
│   │   └── delivery_events.py ← L5: 双通道
│   ├── server.py              ← HTTP server
│   ├── pyproject.toml
│   └── tests/
│
├── cli/                       ← Python CLI 客户端
│   └── gemma_cli.py
│
├── android/                   ← Kotlin shell(20% 时间)
│   ├── app/                   ← fork 自 Google AI Edge Gallery
│   └── README.md
│
├── bench/                     ← 性能 / 正确性评估
│   ├── translate_accuracy/
│   ├── latency/
│   └── memory_footprint/
│
├── demo/                      ← 评审材料
│   ├── video_script.md
│   ├── recording/
│   └── judge_run.sh           ← 一键让评审跑起来
│
└── docs/                      ← 扩展文档
    ├── api.md
    ├── deployment.md
    └── borrowings_notes.md    ← 详细的三大借鉴对照
```

---

## 8. 启动顺序(Week 1 第一天要做的事)

```
 1. 在 core/ 初始化 Python 包(pyproject.toml)
 2. 先写 MockRuntime(不依赖任何模型,返回固定字符串)
 3. 先写 ToolRegistry 的骨架(一个 translate 工具,mock 实现)
 4. 打通 Orchestrator 最小 loop:输入 → tool 选择 → tool 调用 → 输出
 5. 写 CLI 客户端:能 echo 输入并走 mock pipeline
 6. 此时**还没接真模型**,但整个 agent 骨架能跑
 7. 再换 LlamaCppRuntime,接真 Gemma E4B 权重

关键原则:**Runtime 是最后一步,不是第一步**。
先把框架搭对,再换"引擎"。
```

---

## 9. 不做的事(Non-Goals)

- ✗ Post-training / fine-tuning Gemma
- ✗ iOS 支持
- ✗ 多用户 / 账号系统
- ✗ 云端 sync(和"离线优先"原则冲突)
- ✗ Web 前端(除非时间富余,仅作评审备用)
- ✗ 第三方翻译 API(违反离线原则,**所有翻译走本地 Gemma**)
