"""Broader validation of the scene-TYPE feature on a diverse dataset.

Beyond the original 4-type probe (food/transit), this stresses the two halves
across MANY domains plus two adversarial pairs that share surface features:
  - 书店 vs 图书馆 (both full of books)
  - 药店 vs 超市 (both retail shelves)

Two checks, both with E4B under proper chat framing:
  1. LABELING — each scene's 3 varied gists should get the same (or close)
     scene_type label, and different scene TYPES must not collapse together.
  2. NAMING (B6) — the production build_scene_prompt over (label, words) should
     give a warm, place-recognizable name across every domain, not just the
     food/warm ones the seed showed.

Run: TIDELINE_GEMMA_PATH=models/gemma-4-E4B-it-Q4_K_M.gguf TIDELINE_GEMMA_GPU_LAYERS=0 \
     PYTHONPATH=core/src python3 scripts/scene_type_validation.py
"""
import sys

sys.path.insert(0, "core/src")

from tideline.intelligence import episodic_title
from tideline.runtimes.llama_cpp import LlamaCppRuntime

# Each scene type: 3 varied gists (different photos / objects, like real
# per-photo gists) + the foreign words met there (for B6 naming).
SCENES = {
    "拉面店": {
        "gists": ["深夜拉面店里发着暖光的购票机", "另一家拉面馆墙上的菜单价目表",
                  "拉面店柜台前排队等位的客人"],
        "words": ["ラーメン", "餃子", "替玉"],
    },
    "车站": {
        "gists": ["车站检票口上方的蓝色出口指示牌", "地铁站台柱子上的站名牌",
                  "换乘通道墙上指向各线路的方向牌"],
        "words": ["切符", "出口", "改札"],
    },
    "咖啡馆": {
        "gists": ["街角咖啡馆露天座上冒着热气的咖啡", "咖啡店吧台后的手写饮品菜单",
                  "靠窗座位上一杯拉了花的拿铁"],
        "words": ["コーヒー", "カフェラテ", "お代わり"],
    },
    "书店": {
        "gists": ["书店里成排顶到天花板的书架", "书店收银台旁堆着的新书",
                  "书店角落安静的试读区"],
        "words": ["本", "雑誌", "文庫"],
    },
    "图书馆": {  # adversarial vs 书店 — both full of books
        "gists": ["图书馆借还书的自助机器", "图书馆安静的阅览长桌",
                  "图书馆墙上的分类索引牌"],
        "words": ["図書館", "貸出", "閲覧"],
    },
    "药店": {
        "gists": ["药店货架上排列的感冒药", "药妆店里的护肤品专区",
                  "药店收银处贴的处方说明"],
        "words": ["薬", "風邪薬", "処方箋"],
    },
    "超市": {  # adversarial vs 药店 — both retail shelves
        "gists": ["超市生鲜区码放整齐的蔬菜", "超市货架上成排的零食",
                  "超市收银台前排队的购物车"],
        "words": ["野菜", "お惣菜", "レジ"],
    },
    "医院": {
        "gists": ["医院挂号处上方的指示牌", "医院走廊两侧的科室门牌",
                  "医院药房的取药窗口"],
        "words": ["受付", "内科", "診察"],
    },
    "公园": {
        "gists": ["公园里樱花树下的长椅", "公园中央喷泉的广场",
                  "公园入口的导览地图牌"],
        "words": ["公園", "桜", "噴水"],
    },
    "电影院": {
        "gists": ["电影院大厅的自助售票机", "电影院贴满海报的走廊",
                  "电影院检票口的入场指示"],
        "words": ["映画", "チケット", "上映"],
    },
}

LABEL_PROMPT = (
    "下面是一句拍照场景的描述。请用 2 到 4 个汉字给出这是【哪一类地方或场景】,"
    "只要类别本身(例如「拉面店」「车站」「咖啡馆」「书店」),"
    "不要描述具体的物体或细节。\n描述：{gist}\n类别："
)


def chat(rt, system, prompt, max_tokens=16):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    out = rt._llm.create_chat_completion(messages=msgs, max_tokens=max_tokens, temperature=0.3)
    return out["choices"][0]["message"]["content"].strip()


def main() -> None:
    rt = LlamaCppRuntime()

    print("=== 1. LABELING (3 varied gists per type) ===")
    labels: dict[str, list[str]] = {}
    for truth, data in SCENES.items():
        got = []
        for g in data["gists"]:
            raw = chat(rt, None, LABEL_PROMPT.format(gist=g))
            lab = (raw.splitlines() or [""])[0].strip().strip("「」\"' 。.：:")
            got.append(lab)
        labels[truth] = got
        uniq = len(set(got))
        flag = "" if uniq == 1 else f"  ⚠ {uniq} distinct"
        print(f"  {truth:6} -> {got}{flag}")

    print("\n--- cross-type collisions (a label two TYPES share) ---")
    leaked = False
    keys = list(labels)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            overlap = set(labels[keys[i]]) & set(labels[keys[j]])
            if overlap:
                leaked = True
                print(f"  ⚠ {keys[i]} & {keys[j]} share {overlap}")
    if not leaked:
        print("  clean — no label shared across different scene types")

    print("\n=== 2. B6 NAMING (production build_scene_prompt over label + words) ===")
    native = "Chinese"
    for label, data in SCENES.items():
        items = [{"term": w, "context": ""} for w in data["words"]]
        prompt = episodic_title.build_scene_prompt(label, items, native)
        raw = chat(rt, episodic_title.SCENE_SYSTEM_PROMPT, prompt, max_tokens=24)
        name = episodic_title.parse_response(raw)
        print(f"  {label:6} -> 美名 {name!r}")


if __name__ == "__main__":
    main()
