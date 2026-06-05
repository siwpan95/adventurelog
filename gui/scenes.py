# -*- coding: utf-8 -*-
"""日志格式化 & 辅助工具 — Canvas 场景绘制已废弃（改用标签页式 UI）"""

# 此模块在标签页重构后不再包含 Canvas 场景绘制。
# 如果你需要画布渲染功能，请在 gui/canvas_render.py 中新写。


def format_equipment_bonus(bonus_text: str) -> str:
    """格式化装备加成文本"""
    parts = []
    for part in bonus_text.replace(",", " ").split():
        part = part.strip()
        if part:
            parts.append(part)
    return "  ·  ".join(parts)


def format_stat_bar(value: int, max_val: int, width: int = 20) -> str:
    """生成 ASCII 属性条"""
    pct = value / max_val if max_val > 0 else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {value}/{max_val}"
