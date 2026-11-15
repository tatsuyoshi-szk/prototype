"""Render a customer-facing product journey as PNG and editable SVG.

Requires Pillow and the Windows Meiryo fonts. No application/API calls are made.
"""
from pathlib import Path
import math
from html import escape

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
W, H = 2800, 2440
BG = "#F4F7FB"
INK = "#182B47"
MUTED = "#52647C"
BLUE = "#315ED1"
TEAL = "#087F80"
AMBER = "#A86A13"
LINE = "#B7C6D8"
im = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       '<title>外国人留学生向け AI就活相談：利用の流れ</title>',
       '<desc>相談から就活軸の発見、優先順位の設定、企業との相性評価、候補企業の比較までの利用フロー。</desc>',
       f'<rect width="{W}" height="{H}" fill="{BG}"/>']
fonts = {}


def font(size, bold=False):
    key = size, bold
    if key not in fonts:
        fonts[key] = ImageFont.truetype(
            "C:/Windows/Fonts/meiryob.ttc" if bold else "C:/Windows/Fonts/meiryo.ttc", size)
    return fonts[key]


def rect(x, y, w, h, fill="white", stroke=LINE, radius=20, width=2):
    draw.rounded_rectangle((x, y, x+w, y+h), radius=radius, fill=fill, outline=stroke, width=width)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')


def text(x, y, value, size=30, color=INK, bold=False, center=False, max_width=None):
    f = font(size, bold)
    length = draw.textlength(value, font=f)
    if max_width is not None and length > max_width:
        raise ValueError(f"Text exceeds box ({length:.0f}>{max_width}): {value}")
    if center:
        x -= length / 2
    draw.text((x, y), value, fill=color, font=f, anchor="lt")
    # Meiryo's em box starts above the visible glyph. Pillow's lt uses visible top.
    ascent = f.getmetrics()[0]
    bbox = f.getbbox(value)
    baseline = y + ascent - bbox[1]
    svg.append(f'<text x="{x:.1f}" y="{baseline:.1f}" fill="{color}" font-family="Meiryo, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}">{escape(value)}</text>')


def arrow(points, color=BLUE, width=4, dashed=False, head=True):
    if dashed:
        for a, b in zip(points, points[1:]):
            dx, dy = b[0]-a[0], b[1]-a[1]
            d = math.hypot(dx, dy)
            for i in range(0, int(d), 20):
                s, e = i/d, min(i+11, d)/d
                draw.line((a[0]+dx*s, a[1]+dy*s, a[0]+dx*e, a[1]+dy*e), fill=color, width=width)
    else:
        draw.line(points, fill=color, width=width, joint="curve")
    pts = " ".join(f"{x},{y}" for x, y in points)
    svg.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"' + (' stroke-dasharray="11 9"' if dashed else '') + '/>')
    if head:
        a, b = points[-2:]
        angle = math.atan2(b[1]-a[1], b[0]-a[0])
        tri = [b, (b[0]-17*math.cos(angle-0.45), b[1]-17*math.sin(angle-0.45)),
               (b[0]-17*math.cos(angle+0.45), b[1]-17*math.sin(angle+0.45))]
        draw.polygon(tri, fill=color)
        svg.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in tri)}" fill="{color}"/>')



def node(x, y, w, h, title, lines=(), color=BLUE, tag=None, title_size=34, body_size=28):
    rect(x, y, w, h, stroke=color)
    offset = 22
    if tag:
        text(x+28, y+offset, tag, 23, color, True, max_width=w-56)
        offset += 36
    text(x+28, y+offset, title, title_size, INK, True, max_width=w-56)
    offset += title_size+18
    for row in lines:
        text(x+28, y+offset, row, body_size, MUTED, max_width=w-56)
        offset += body_size+14
    if offset-14 > h-12:
        raise ValueError(f"Text too tall: {title}")


def panel(x, w, label, title, lead, color):
    rect(x, 565, w, 1490, fill="white", stroke="#DCE4EF", radius=24)
    text(x+32, 593, label, 24, color, True)
    text(x+32, 636, title, 38, INK, True, max_width=w-64)
    text(x+32, 693, lead, 25, MUTED, max_width=w-64)


# Same overview + three detailed flow panels as the original diagram.
text(70, 52, "外国人留学生向け  AI就活相談", 29, BLUE, True)
text(70, 116, "対話から、根拠のある企業提案まで。", 67, INK, True)
text(70, 211, "一人ひとりの就活軸と希望条件をもとに、自己理解から企業比較までを支援", 33, MUTED)
steps = [
    ("相談する", "経験・希望を話す"),
    ("就活軸を確認", "大切にしたいことを整理"),
    ("重要度を回答", "優先順位と譲れない条件"),
    ("企業を探す", "情報を調べ、相性を評価"),
    ("候補を比較する", "提案理由と出典を確認"),
]
for i, (title, desc) in enumerate(steps):
    x = 70+i*540
    rect(x, 300, 500, 180, stroke="#DCE4EF")
    text(x+25, 322, f"0{i+1}", 24, BLUE, True)
    text(x+25, 363, title, 36, INK, True, max_width=450)
    text(x+25, 421, desc, 27, MUTED, max_width=450)
    if i < 4:
        arrow([(x+505,390), (x+532,390)])
text(70, 512, "利用の流れ ↑     ／     提案につながる仕組み ↓", 24, MUTED)

panel(70, 760, "01  希望を理解する", "相談とアンケート", "対話と回答から、本人の価値観・希望条件を整理", BLUE)
panel(880, 1050, "02  企業との相性を確かめる", "企業の調査と評価", "15社を目標に、根拠を確かめながら候補を探索", TEAL)
panel(1980, 750, "03  比較・検討につなげる", "企業ランキングと提案理由", "相性の良さと、その理由をあわせて見せる", BLUE)

node(110,760,680,205,"AIとの対話で希望を深掘り",[
    "学生が経験・希望・不安を自分の言葉で話す",
    "AIが質問を重ね、価値観や働き方を整理"],tag="日本語・英語で相談", title_size=33, body_size=27)
arrow([(450,965),(450,1015)])
node(110,1015,680,155,"個人の就活軸を見つけ、確認",[
    "本人が大切にしたいことを言語化する"],title_size=33)
arrow([(450,1170),(450,1220)])
node(110,1220,680,245,"共通14項目＋個人軸を回答",[
    "会社選びの各項目に重要度を1〜5で回答",
    "「譲れない」条件も指定できる",
    "企業のグローバル度などと個人の希望を評価"],tag="会社選びで何を大事にするか",title_size=33,body_size=26)
arrow([(450,1465),(450,1520)])
node(110,1520,680,210,"本人に合う企業を探す準備",[
    "何をどれだけ重視するかを、回答から整理",
    "就活軸と譲れない条件を企業選びに反映"],tag="アンケート送信後に企業探しを開始", title_size=33,body_size=27)
text(115,1784,"相談で見つけた軸を、企業選びにつなげる。",27,BLUE,True,max_width=670)
text(115,1841,"会話・アンケート・結果は同じ流れで確認。",26,MUTED,max_width=670)
text(115,1889,"途中で離れても、続きから利用できる。",26,MUTED,max_width=670)
arrow([(790,1650),(855,1650),(855,850),(920,850)],color=TEAL)

node(920,760,970,220,"蓄積した企業情報から候補を選ぶ",[
    "公開情報をもとに、希望条件に合う企業を探す",
    "譲れない条件について、裏付けとなる情報を確認",
    "個人の就活軸との相性を考慮し、候補を選定"],color=TEAL,title_size=34)
arrow([(1405,980),(1405,1040)],color=TEAL)
node(920,1040,970,230,"共通項目と個人の就活軸を評価",[
    "共通14項目と個人軸の相性を、それぞれ1〜5で評価",
    "確認できた事実と出典に基づいて判断する",
    "譲れない条件は、4以上の評価と根拠があることが必要"],color=TEAL,tag="希望条件と企業情報を照らし合わせる",title_size=34,body_size=26)
arrow([(1405,1270),(1405,1320)],color=TEAL)
diamond=[(1405,1320),(1730,1420),(1405,1520),(1080,1420)]
draw.polygon(diamond,fill="#EAF6F5",outline=TEAL,width=3)
svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in diamond)}" fill="#EAF6F5" stroke="{TEAL}" stroke-width="3"/>')
text(1405,1380,"条件に合う企業が",31,INK,True,center=True)
text(1405,1429,"目標数に達した？",31,INK,True,center=True)
arrow([(1405,1520),(1405,1590)],color=AMBER)
rect(1160,1538,490,37,fill="white",stroke="white",radius=0)
text(1405,1540,"不足していれば、追加で候補を探す",24,AMBER,True,center=True)
node(960,1590,890,140,"就活軸と希望条件から新たな企業を選ぶ",[
    "すでに調べた企業との重複を避けて、候補を広げる"],color=AMBER,title_size=31,body_size=27)
arrow([(1405,1730),(1405,1780)],color=AMBER)
node(960,1780,890,190,"Webで企業を調査し、評価へ戻る",[
    "企業ごとに公開情報を調べ、事実と出典を集める",
    "新たに得た情報も使い、希望との相性を評価する"],color=AMBER,title_size=32,body_size=27)
arrow([(960,1875),(902,1875),(902,1155),(920,1155)],color=AMBER)
text(1060,2000,"追加調査後に候補を確定し、条件未達の点も明示。",25,MUTED,max_width=850)
arrow([(1730,1420),(1952,1420),(1952,865),(2020,865)],color=TEAL)
rect(1748,1333,176,70,fill="white",stroke="white",radius=0)
text(1838,1335,"目標達成／",25,TEAL,True,center=True)
text(1838,1374,"調査完了",25,TEAL,True,center=True)

node(2020,760,670,250,"比較する企業候補を確定",[
    "条件を満たす企業を優先して選ぶ",
    "候補が不足するときは、近い企業も含める",
    "その場合、満たしていない条件を明示",
    "本人の重要度と企業ごとの評価をまとめる"],title_size=33,body_size=26)
arrow([(2355,1010),(2355,1060)])
node(2020,1060,670,355,"本人との相性で順位をつける",[
    "① 譲れない条件を満たす企業が先",
    "② 条件未達が少ない企業を優先",
    "③ 根拠が少ない企業は順位を下げる",
    "④ 同じ条件の中で総合点が高い順",
    "根拠のある評価と本人の重要度で計算"],tag="相性を100点満点の総合点に",title_size=32,body_size=27)
arrow([(2355,1415),(2355,1475)])
node(2020,1475,670,265,"上位5社と、ほかの候補を表示",[
    "合う点・気になる点と、その根拠を示す",
    "条件の充足状況と未達の理由も見せる",
    "出典をたどり、本人が比較・検討できる"],tag="企業ランキングと提案理由",title_size=31,body_size=26)
rect(2020,1805,670,168,fill="#EEF3FD",stroke="#D8E2FA")
text(2048,1833,"調査中も、進み具合がわかる",29,BLUE,True,max_width=610)
text(2048,1888,"企業の選定・調査・評価の進捗を表示。",26,MUTED,max_width=610)
text(2048,1932,"完了すると、そのまま結果を確認できる。",26,MUTED,max_width=610)

text(70,2110,"この仕組みで支援できること",30,INK,True)
values=[
    (70,"一人ひとりに合わせた提案",["本人の価値観・重要度・譲れない条件を、","企業候補の選定と順位づけに反映。"]),
    (970,"根拠を確認できる企業比較",["相性の点数だけでなく、提案理由と出典を表示。","確認できない情報や条件未達も、見える形に。"]),
    (1870,"相談から企業選びまでを一貫して支援",["対話で深めた自己理解を、具体的な企業提案へ。","本人が納得して検討するための材料を示す。"]),
]
for x,title,body in values:
    rect(x,2172,860,175,stroke="#DCE4EF")
    text(x+28,2197,title,29,INK,True,max_width=804)
    for j,row in enumerate(body):
        text(x+28,2247+j*45,row,26,MUTED,max_width=804)
text(70,2384,"※ 企業の評価・提案は確認できた公開情報に基づきます。情報の充実度によって、評価や順位は変わります。",23,MUTED)
OUT.mkdir(exist_ok=True)
im.save(OUT / "system-flow.png", optimize=True)
(OUT / "system-flow.svg").write_text("\n".join(svg + ["</svg>"]), encoding="utf-8")
print(f"Created {OUT / 'system-flow.png'} ({W} x {H})")
print(f"Created {OUT / 'system-flow.svg'}")
