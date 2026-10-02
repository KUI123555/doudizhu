"""把 AI 生成的原图加工成游戏素材。

用法：
    python tools/make_assets.py sheet 原图.png assets/characters/landlord.png
    python tools/make_assets.py bg    原图.png assets/backgrounds/redwood.jpg

sheet：一行 4 个动作的角色图（待机 / 出牌 / 胜利 / 失败）。去掉背景、切成 4 帧、
       统一缩放并让脚底对齐，输出 4 帧横排的透明 PNG。
bg：   居中裁成 1280x760 输出 JPG。
"""
import sys

import numpy as np
from PIL import Image

FRAME_H = 260          # 输出帧高度（游戏里再缩放）
FRAMES = 4
BG_SIZE = (1280, 760)


def _remove_background(img):
    """原图没有透明通道时：从四条边开始把和背景颜色相近、且连通的像素抠掉。"""
    a = np.asarray(img.convert('RGBA')).astype(np.int16)
    if (a[..., 3] < 250).mean() > 0.05:        # 已经是透明背景
        return img.convert('RGBA')
    rgb = a[..., :3]
    corners = np.concatenate([rgb[:8, :8].reshape(-1, 3), rgb[:8, -8:].reshape(-1, 3),
                              rgb[-8:, :8].reshape(-1, 3), rgb[-8:, -8:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    cand = np.abs(rgb - bg).sum(axis=2) < 60
    region = np.zeros_like(cand)
    region[0, :] = cand[0, :]
    region[-1, :] = cand[-1, :]
    region[:, 0] |= cand[:, 0]
    region[:, -1] |= cand[:, -1]
    while True:                                 # 约束膨胀 = 和边缘连通的背景
        grown = region.copy()
        grown[1:] |= region[:-1]
        grown[:-1] |= region[1:]
        grown[:, 1:] |= region[:, :-1]
        grown[:, :-1] |= region[:, 1:]
        grown &= cand
        if (grown == region).all():
            break
        region = grown
    out = np.asarray(img.convert('RGBA')).copy()
    out[region, 3] = 0
    return Image.fromarray(out)


def _components(mask):
    """四连通区域标记，返回 [(像素数, x0, x1, ys, xs)]。"""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    comps = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack, ys, xs = [(y0, x0)], [], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            ys.append(y)
            xs.append(x)
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        comps.append((len(ys), min(xs), max(xs) + 1, np.array(ys), np.array(xs)))
    return comps


def _figures(alpha):
    """把图里的像素分给 4 个人物：大块是人物本身；甩出去的牌等小块
    如果不在某个人物身体正中范围内，就归给它左边的人物（人物都朝右甩牌）；零星噪点丢掉。"""
    comps = [c for c in _components(alpha > 40) if c[0] >= 60]
    biggest = max(c[0] for c in comps)
    figs = sorted([c for c in comps if c[0] >= biggest * 0.2], key=lambda c: c[1])
    while len(figs) > FRAMES:                   # 一个人物被分成两大块：并到横向重叠最多的那块
        i = min(range(len(figs)), key=lambda k: figs[k][0])
        j = max((k for k in range(len(figs)) if k != i),
                key=lambda k: min(figs[i][2], figs[k][2]) - max(figs[i][1], figs[k][1]))
        a, b = figs[i], figs[j]
        figs[j] = (a[0] + b[0], min(a[1], b[1]), max(a[2], b[2]),
                   np.concatenate([a[3], b[3]]), np.concatenate([a[4], b[4]]))
        del figs[i]
    if len(figs) != FRAMES:
        raise SystemExit(f'找到 {len(figs)} 个人物，应该是 {FRAMES} 个')
    owner = [[f] for f in figs]
    for c in comps:
        if any(c is f for f in figs):
            continue
        cx = (c[1] + c[2]) / 2
        k = next((k for k, f in enumerate(figs)
                  if f[1] + 0.15 * (f[2] - f[1]) <= cx <= f[2] - 0.15 * (f[2] - f[1])), None)
        if k is None:
            left = [k for k, f in enumerate(figs) if f[1] < cx]
            k = left[-1] if left else 0
        owner[k].append(c)
    return owner


def make_sheet(src, dst):
    img = _remove_background(Image.open(src))
    rgba = np.asarray(img)
    crops = []
    for parts in _figures(rgba[..., 3]):
        ys = np.concatenate([p[3] for p in parts])
        xs = np.concatenate([p[4] for p in parts])
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        own = np.zeros(rgba.shape[:2], bool)
        own[ys, xs] = True
        # 半透明的描边像素不在 alpha>40 的区域里：把人物区域往外扩 2 像素一起带上
        for _ in range(2):
            grown = own.copy()
            grown[1:] |= own[:-1]
            grown[:-1] |= own[1:]
            grown[:, 1:] |= own[:, :-1]
            grown[:, :-1] |= own[:, 1:]
            own = grown
        sub = rgba.copy()
        sub[~own, 3] = 0
        crop = Image.fromarray(sub).crop((max(0, x0 - 2), max(0, y0 - 2), x1 + 2, y1 + 2))
        ca = np.asarray(crop)[..., 3] > 40
        h = ca.shape[0]
        feet = ca[int(h * 0.85):]               # 脚的水平位置用来对齐
        fx = np.where(feet.any(axis=0))[0]
        foot_x = (fx[0] + fx[-1]) / 2 if len(fx) else ca.shape[1] / 2
        crops.append((crop, foot_x))
    scale = FRAME_H / max(c.height for c, _ in crops)
    half = max(max(fx, c.width - fx) for c, fx in crops) * scale
    fw = int(half * 2) + 8
    sheet = Image.new('RGBA', (fw * FRAMES, FRAME_H), (0, 0, 0, 0))
    for k, (crop, fx) in enumerate(crops):
        w, h = max(1, round(crop.width * scale)), max(1, round(crop.height * scale))
        small = crop.resize((w, h), Image.LANCZOS)
        x = k * fw + int(fw / 2 - fx * scale)
        sheet.alpha_composite(small, (x, FRAME_H - h))
    sheet.save(dst, optimize=True)
    print(f'{dst}: {FRAMES} 帧, 每帧 {fw}x{FRAME_H}')


def make_bg(src, dst):
    img = Image.open(src).convert('RGB')
    tw, th = BG_SIZE
    r = max(tw / img.width, th / img.height)
    img = img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)
    x, y = (img.width - tw) // 2, (img.height - th) // 2
    img.crop((x, y, x + tw, y + th)).save(dst, quality=88, optimize=True)
    print(f'{dst}: {tw}x{th}')


if __name__ == '__main__':
    kind, src, dst = sys.argv[1:4]
    {'sheet': make_sheet, 'bg': make_bg}[kind](src, dst)
