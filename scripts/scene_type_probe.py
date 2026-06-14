"""Probe: can E4B turn a per-photo SCENE gist into a stable scene-TYPE label?

The user wants themes to be a KIND of scene clustered across outings (all
ramen-shop captures -> one "ramen" theme), not one occasion. Real gists are
per-photo descriptions ("the ticket machine glowing in the ramen alley"), too
varied to group by text. So the proposed mechanism is: the model emits a short
scene-TYPE label at capture (engineering groups by the label; the model only
categorizes = garnish). This probe checks the load-bearing risk BEFORE building
(the 续14 discipline): do same-type gists across varied wording get the SAME
label, and do different types stay apart? If labels drift badly, the mechanism
won't cluster across visits and we rethink.

Run: TIDELINE_GEMMA_PATH=models/gemma-4-E4B-it-Q4_K_M.gguf TIDELINE_GEMMA_GPU_LAYERS=0 \
     PYTHONPATH=core/src python3 scripts/scene_type_probe.py
"""
import sys

sys.path.insert(0, "core/src")

from tideline.runtimes.llama_cpp import LlamaCppRuntime

# 4 scene types x 3 "visits", each worded differently (a different photo /
# object / day), mirroring how real gists vary within one kind of place.
SCENES = {
    "ramen": [
        "深夜拉面横丁里发着暖光的购票机",
        "另一家拉面店墙上贴的菜单价目表",
        "拉面馆柜台前排着队等位的客人",
    ],
    "izakaya": [
        "居酒屋矮桌上摊开的一张手写纸菜单",
        "小酒馆黑板上用粉笔写的当日推荐",
        "居酒屋里刚端上桌的一串串烤鸡肉",
    ],
    "station": [
        "车站检票口上方那块蓝色的出口指示牌",
        "地铁站台柱子上蓝底白字的站名牌",
        "换乘通道墙上指向各条线路的方向牌",
    ],
    "cafe": [
        "清晨街角咖啡馆露天座上那杯冒着热气的咖啡",
        "咖啡店吧台后挂着的一块手写饮品菜单",
        "靠窗座位上一杯拉了花的拿铁",
    ],
}

PROMPT = (
    "下面是一句拍照场景的描述。请用 2 到 4 个汉字给出这是【哪一类地方或场景】,"
    "只要类别本身(例如「拉面店」「车站」「咖啡馆」「居酒屋」),"
    "不要描述具体的物体或细节。\n"
    "描述：{gist}\n"
    "类别："
)


def _chat(rt: LlamaCppRuntime, prompt: str) -> str:
    # Proper chat framing (the GGUF's jinja template) instead of raw text
    # completion — an instruct model needs the turn markers, or it returns
    # empty / runs away (the raw-completion flakiness this probe first hit).
    # The on-device litertlm path is a real Conversation, so it frames like
    # this too.
    out = rt._llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16,
        temperature=0.3,
    )
    return out["choices"][0]["message"]["content"]


def main() -> None:
    rt = LlamaCppRuntime()
    results: dict[str, list[str]] = {}
    for scene_type, gists in SCENES.items():
        labels = []
        for g in gists:
            raw = _chat(rt, PROMPT.format(gist=g))
            lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
            label = (lines[0] if lines else "").strip("「」\"' 。.：:")
            labels.append(label)
            print(f"  [{scene_type:8}] {g}\n             raw={raw!r}\n             -> {label!r}")
        results[scene_type] = labels
        print()

    print("=== same-type consistency (do a type's 3 visits agree?) ===")
    for scene_type, labels in results.items():
        uniq = set(labels)
        print(f"  {scene_type:8} {labels}  ->  {len(uniq)} distinct")

    print("\n=== cross-type separation (any label shared across types?) ===")
    all_labels = {st: set(ls) for st, ls in results.items()}
    leaked = False
    types = list(all_labels)
    for i in range(len(types)):
        for j in range(i + 1, len(types)):
            overlap = all_labels[types[i]] & all_labels[types[j]]
            if overlap:
                leaked = True
                print(f"  ⚠ {types[i]} & {types[j]} share {overlap}")
    if not leaked:
        print("  clean — no label shared across different scene types")


if __name__ == "__main__":
    main()
