export const meta = {
  name: 'tideline-seed-enrich',
  description: '为 Tideline seed.py 补真实情景/来源数据,让涌现闭环 web UI 发光(只产候选,不写文件)',
  phases: [
    { title: '盘点', detail: '读 web UI + seed.py,列出 UI 想要但 seed 缺的情景/来源字段' },
    { title: '生成', detail: '每个情景并行造真实情景/来源候选' },
    { title: '校验', detail: '对抗式检查:这条数据能驱动相册/片刻 UI 发光吗' },
  ],
}

const REPO = '/Users/hualiangqin/VSCodeWorkspace/personal/tideline'

const GAP_SCHEMA = {
  type: 'object',
  properties: {
    ui_consumes: {
      type: 'array', items: { type: 'string' },
      description: 'web UI(app.py/episodic_title/relatedness)实际渲染或依赖的字段/信号'
    },
    seed_provides: {
      type: 'array', items: { type: 'string' },
      description: 'seed.py 当前产出的字段'
    },
    gaps: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          field: { type: 'string' },
          why: { type: 'string', description: '为什么 UI 需要它 / 缺了 UI 哪里黯淡' },
        },
        required: ['field', 'why'],
      },
    },
  },
  required: ['ui_consumes', 'seed_provides', 'gaps'],
}

const SCENARIO_SCHEMA = {
  type: 'object',
  properties: {
    scenario_name: { type: 'string' },
    enriched: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          original: { type: 'string' },
          translated: { type: 'string' },
          context_sentence: { type: 'string', description: '该词出现的真实情景原句(目标语境)' },
          source_hint: { type: 'string', description: '来源:菜单/歌词/会议纪要/文档章节等具体出处' },
        },
        required: ['original', 'translated', 'context_sentence', 'source_hint'],
      },
    },
  },
  required: ['scenario_name', 'enriched'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    scenario_name: { type: 'string' },
    glows: { type: 'boolean', description: '这批数据能否让 episodic 片刻+主题相册真正发光' },
    weak_entries: { type: 'array', items: { type: 'string' }, description: '太干巴/像占位符的条目' },
    fix: { type: 'string', description: '一句话:要更亮该怎么改' },
  },
  required: ['scenario_name', 'glows', 'fix'],
}

phase('盘点')
const gap = await agent(
  `你在 Tideline 仓库 ${REPO}。读这几个文件:\n` +
  `- core/src/tideline/seed.py (当前 seed 数据生成器)\n` +
  `- core/src/tideline/web/app.py (web UI 后端)\n` +
  `- core/src/tideline/intelligence/episodic_title.py\n` +
  `- core/src/tideline/intelligence/relatedness.py\n` +
  `目标:涌现闭环的 web UI 有 episodic「片刻」标题和主题「相册」。` +
  `搞清楚 UI 渲染/推理时实际依赖哪些字段或信号,而 seed.py 现在只产 (original,target_lang,translated,source_lang,created_at)。` +
  `列出 UI 想要但 seed 缺的东西(尤其「真实情景上下文」和「来源出处」这类能让相册发光的素材)。只读不改。`,
  { phase: '盘点', schema: GAP_SCHEMA }
)

log(`盘点完成:发现 ${gap.gaps.length} 个缺口字段`)

const SCENARIOS = [
  'Tokyo trip — menu hunting',
  'French cooking — recipe reading',
  'Latin music — lyric translation',
  'Beijing meetings — business Mandarin',
  'German tech docs — software reading',
  'Polyglot crossings — same concept, different originals',
]

const GAP_SUMMARY = JSON.stringify(gap.gaps)

const results = await pipeline(
  SCENARIOS,
  (name) => agent(
    `Tideline seed 情景「${name}」需要补真实情景/来源数据。` +
    `已知 UI 缺口:${GAP_SUMMARY}。` +
    `读 ${REPO}/core/src/tideline/seed.py 里这个情景现有的词对,` +
    `为其中代表性的若干词对(至少 6 条,覆盖 frequent/occasional/rare)各补一个:` +
    `(1) context_sentence——该词真实出现的情景原句;(2) source_hint——具体出处。` +
    `要像真实生活片段,不要占位符。`,
    { label: `生成:${name.slice(0, 14)}`, phase: '生成', schema: SCENARIO_SCHEMA }
  ),
  (draft, name) => agent(
    `对抗式校验情景「${name}」的这批补充数据:${JSON.stringify(draft.enriched)}。` +
    `站在「这能让 episodic 片刻标题 + 主题相册 UI 发光吗」的角度挑刺:` +
    `哪些 context_sentence 干巴像填表?哪些 source_hint 太泛?默认严格,宁可标 weak。`,
    { label: `校验:${name.slice(0, 14)}`, phase: '校验', schema: VERDICT_SCHEMA }
  ).then(v => ({ ...draft, verdict: v }))
)

const ok = results.filter(Boolean)
const glowing = ok.filter(r => r.verdict.glows)

return {
  gap,
  scenarios_total: SCENARIOS.length,
  scenarios_glowing: glowing.length,
  results: ok.map(r => ({
    scenario: r.scenario_name,
    sample_count: r.enriched.length,
    glows: r.verdict.glows,
    weak: r.verdict.weak_entries || [],
    fix: r.verdict.fix,
    enriched: r.enriched,
  })),
}
