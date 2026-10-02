"""人物形象：加载角色动作图（待机 / 出牌 / 胜利 / 失败），按身份和动作画到牌桌上。"""
import math
import os
import sys

import pygame

POSES = ('idle', 'play', 'win', 'lose')
NAMES = ('landlord', 'farmer_m', 'farmer_f')


def asset_path(*parts):
    """素材路径；打包成 exe 后素材在 PyInstaller 的解压目录里。"""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'assets', *parts)


class Sprites:
    """所有角色、所有动作、朝左朝右两个方向的图。缺素材时 ok=False，牌桌改画圆形头像。"""

    def __init__(self, height):
        self.height = height
        self.frames = {}
        self.ok = True
        for name in NAMES:
            try:
                sheet = pygame.image.load(asset_path('characters', name + '.png')).convert_alpha()
            except (pygame.error, FileNotFoundError):
                self.ok = False
                return
            fw = sheet.get_width() // len(POSES)
            for k, pose in enumerate(POSES):
                fr = sheet.subsurface((k * fw, 0, fw, sheet.get_height()))
                s = height / fr.get_height()
                img = pygame.transform.smoothscale(fr, (round(fw * s), height))
                self.frames[(name, pose, False)] = img
                self.frames[(name, pose, True)] = pygame.transform.flip(img, True, False)

    def get(self, name, pose, face_left):
        return self.frames[(name, pose, face_left)]


def pose_transform(pose, age, t, seat, facing):
    """动作的程序动画：返回 (水平偏移, 垂直偏移, 横向缩放, 纵向缩放)。"""
    if pose == 'play':
        k = min(1.0, age / 0.7)
        dx = facing * 18 * math.sin(math.pi * k)              # 向前一冲再收回
        sy = 1 + 0.05 * math.sin(math.pi * min(1.0, age / 0.3))
        return dx, 0, 1 / sy ** 0.5, sy
    if pose == 'win':
        return 0, -abs(math.sin(age * 6.5)) * 12, 1, 1        # 原地蹦跳
    if pose == 'lose':
        sway = math.sin(age * 1.5) * 0.01
        return 0, 0, 1 + sway, 0.97
    breath = math.sin(t * 2.4 + seat * 1.7)                    # 待机呼吸
    return 0, 0, 1 - 0.006 * breath, 1 + 0.012 * breath
