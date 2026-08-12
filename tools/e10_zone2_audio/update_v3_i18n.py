"""Replace the obsolete sparse Zone 2 dialogue keys with Owner V3 copy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "i18n.js"

LINES = {
    "e10.zone2.shot02.line01": ("Oh? Don't be afraid. I won't hurt you.", "咦？別怕，我不會傷害你。"),
    "e10.zone2.shot02.line02": ("...Shui, look. It isn't trying to attack us. It's trembling.", "……水靈，你看。牠不是想攻擊，牠是在發抖。"),
    "e10.zone2.shot03.line01": ("Wait! Don't go any farther!", "等等！別再往前了！"),
    "e10.zone2.shot03.line02": ("What happened?", "發生什麼事了？"),
    "e10.zone2.shot03.line03": ("The slimes have been fleeing outward for days... I've never seen them this afraid.", "這幾天史萊姆一直往外逃……以前從沒看過牠們這麼害怕。"),
    "e10.zone2.shot03.line04": ("Is it because of those swarms?", "是因為那些蜂群嗎？"),
    "e10.zone2.shot03.line05": ("Not just that. The swarms keep growing too... It's as if something drove them all out.", "不只。蜂群也越來越多……像是有什麼東西，把牠們全都趕了出來。"),
    "e10.zone2.shot04.line01": ("Is that... a hive?", "那是……蜂巢？"),
    "e10.zone2.shot04.line02": ("Yes. It seems the trouble began in that cave.", "嗯。異常好像就是從那個洞穴開始的。"),
    "e10.zone2.shot04.line03": ("It wasn't like this before. The honeycomb spread there only recently.", "那裡以前不是這個樣子。蜂巢是最近才突然擴散出來的。"),
    "e10.zone2.shot04.line04": ("So whatever is affecting the slimes and the swarms could be connected to that place...", "所以史萊姆和蜂群的異常，都可能跟那裡有關……"),
    "e10.zone2.shot04.line05": ("If you're going to investigate, be careful.", "如果你要過去調查，一定要小心。"),
    "e10.zone2.shot07.line01": ("So... you're the one who did this to this place.", "原來……就是你讓這裡變成這樣的。"),
    "e10.zone2.shot07.line02": ("The slimes and the swarms... neither of them should have ended up like this.", "史萊姆也好，蜂群也好，牠們都不該變成現在這個樣子。"),
    "e10.zone2.shot07.line03": ("I can't let you keep doing this.", "我不能讓你再這樣下去了。"),
    "e10.zone2.shot09.line01": ("The wind... it's calm again.", "風……平靜下來了。"),
    "e10.zone2.shot09.line02": ("They weren't our enemies. They were caught in this too.", "原來牠們不是敵人，只是受到了影響。"),
    "e10.zone2.shot10.line01": ("Let's go.", "走吧。"),
}


def js_line(key: str, en: str, zh: str) -> str:
    return f"        '{key}': {{ en: {en!r}, zh: {zh!r} }},\n".replace("'", "'")


data = PATH.read_bytes()
newline = "\r\n" if b"\r\n" in data else "\n"
text = data.decode("utf-8").replace("\r\n", "\n")
old_keys = {
    "e10.zone2.shot02.dialogue",
    "e10.zone2.shot04.dialogue",
    "e10.zone2.shot09.dialogue",
    "e10.zone2.result.win.line",
}
lines = [line for line in text.splitlines() if not any(f"'{key}':" in line for key in old_keys)]
text = "\n".join(lines) + "\n"
anchor = "        'e10.zone2.lord.kicker':"
insert = "".join(js_line(key, en, zh) for key, (en, zh) in LINES.items())
text = text.replace(anchor, insert + anchor, 1)
result_anchor = "        'e10.zone2.result.fail.title':"
result_line = js_line("e10.zone2.result.win.line", "The slimes weren't our enemies. They were caught in this too.", "原來牠們不是敵人，只是受到了影響。")
text = text.replace(result_anchor, result_line + result_anchor, 1)
PATH.write_bytes(text.replace("\n", newline).encode("utf-8"))
