"""Atomic capability bench for Tideline.

Built on the principle: rather than measure whether the model can complete
a multi-step task, measure each atomic LLM operation's reliability
independently. Composed tasks fail at the weakest link, so knowing each
atom's success rate tells us **where engineering effort should go**.

Two tiers:

- **Tier A** (translation-engine atoms): operations on which the basic
  product depends. A1 word-translation, A2 sentence-translation,
  A3 source-language inference, A5 output discipline, A6 term extraction
  from snippets. A4 (tool-call correctness) is covered by the agent bench
  suite, which exercises the full Agent loop with RecordingRegistry.

- **Tier B** (intelligence atoms): operations used by future background
  intelligence layers (clustering, summarization, ambiguity flagging).
  Zero-shot — no tools implemented yet, we just send the prompt directly
  and check whether the model can answer reliably. Numbers here tell us
  which Tier B features will work and which need different decomposition.

The bench output is a per-atom success-rate table — exactly the priority
map for "what to build next" vs "what needs engineering workarounds."
"""
