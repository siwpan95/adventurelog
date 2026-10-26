# -*- coding: utf-8 -*-
"""探险日志 · 无头自检（不启动 tkinter 界面）。

验证三件事：
1. 游戏数据能完整加载、基础字段可解析，地下城怪物 / Boss 引用齐全；
2. core.state_machine.GenericStateMachine 能按 auto_config.json 推进状态；
3. core.battle.BattleSystem 能跑完一场回合制战斗并正确结算（并容忍未收录技能）。

仅使用标准库 + 项目自身模块。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 统一 UTF-8 输出，避免 Windows 管道下中文变成乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core.config import CONFIG_DIR, DATA_DIR                    # noqa: E402
from core.models import Adventurer                              # noqa: E402
from core.state_machine import GenericStateMachine              # noqa: E402
from core.battle import BattleSystem                            # noqa: E402
import data.loader as loader_mod                                # noqa: E402
from data.loader import DataLoader                              # noqa: E402


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def load_game_data() -> DataLoader:
    """走正式加载路径（优先 Excel，失败回退 JSON），屏蔽加载器的控制台输出。"""
    loader = DataLoader()
    with contextlib.redirect_stdout(io.StringIO()):
        loader.load_all(DATA_DIR, CONFIG_DIR)
    loader_mod._loader = loader  # 让 core.battle 使用这份已加载的数据
    return loader


def check_data_integrity(loader: DataLoader) -> tuple[dict, int]:
    counts = {
        "jobs": len(loader.jobs),
        "skills": len(loader.skills),
        "equipment": len(loader.equipment),
        "monsters": len(loader.monsters),
        "dungeons": len(loader.dungeons),
    }
    check(counts["jobs"] > 0, "职业数据为空")
    check(counts["skills"] > 0, "技能数据为空")
    check(counts["monsters"] > 0, "怪物数据为空")
    check(counts["dungeons"] > 0, "地下城数据为空")

    for job in loader.jobs.values():
        check(job.base_hp > 0 and job.base_atk > 0 and job.base_def > 0,
              f"职业 {job.name} 的基础属性异常")

    # 数据源里存在少量“初始技能未收录”的既有缺口，游戏会跳过未知技能；
    # 自检只统计该缺口，不把它当作加载失败，同时验证可解析的引用确实有效。
    missing_skill_refs = 0
    for job in loader.jobs.values():
        for skill_name in job.initial_skills:
            if skill_name in loader.skills:
                check(hasattr(loader.skills[skill_name], "power"),
                      f"技能 {skill_name!r} 解析结果异常")
            else:
                missing_skill_refs += 1

    for monster in loader.monsters.values():
        check(monster.hp > 0 and monster.atk > 0,
              f"怪物 {monster.name} 的属性异常")
        missing_skill_refs += sum(1 for name in monster.skills
                                  if name not in loader.skills)

    for dungeon in loader.dungeons:
        check(dungeon.floors > 0, f"地下城 {dungeon.name} 层数异常")
        for monster_name in dungeon.monster_names:
            check(monster_name in loader.monsters,
                  f"地下城 {dungeon.name} 的怪物 {monster_name!r} 不存在")
        check(dungeon.boss_name in loader.monsters,
              f"地下城 {dungeon.name} 的 Boss {dungeon.boss_name!r} 不存在")
    return counts, missing_skill_refs


def check_battle(loader: DataLoader, monster):
    """用一个必赢的冒险者验证战斗结算（不依赖随机结果）。"""
    job_key = next(iter(loader.jobs))
    hero = Adventurer(
        name="自检勇者",
        job_key=job_key,
        level=1,
        hp=10 ** 6,
        max_hp=10 ** 6,
        mp=100,
        max_mp=100,
        atk=10 ** 6,
        def_=10 ** 6,
        spd=9999,
        # 含一个不存在的技能名：验证战斗会跳过未知技能而不是崩溃
        skills=["__自检缺失技能__"],
    )
    random.seed(20260826)
    victory, log, gold, exp = BattleSystem.run([hero], monster, max_turns=5)
    check(victory is True, "高属性勇者未能击败最弱怪物")
    check(isinstance(log, list) and log, "战斗日志为空")
    check(any("被击败" in line for line in log), "战斗日志缺少击杀结算")
    check(exp == monster.exp, f"经验结算错误: {exp} != {monster.exp}")
    check(gold >= monster.gold,
          f"金币结算错误: {gold} < 基础金币 {monster.gold}")
    return gold, exp


def check_state_machine() -> str:
    path = os.path.join(BASE_DIR, "core", "auto_config.json")
    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    machines = config.get("state_machines", {})
    check(bool(machines), "auto_config.json 没有 state_machines")

    # 配置完整性：初始状态与所有转移目标都必须存在
    for name, machine in machines.items():
        states = machine.get("states", {})
        check(bool(states), f"状态机 {name} 没有 states")
        check(machine.get("initial") in states,
              f"状态机 {name} 的初始状态不存在")
        for state_id, state in states.items():
            for event, target in state.get("transitions", {}).items():
                target_id = target if isinstance(target, str) else target.get("target")
                check(target_id in states,
                      f"状态机 {name}: {state_id} --{event}--> {target_id} 目标不存在")

    machine = GenericStateMachine("SM_Explore", config)
    check(machine.current_state_id == "idle", "SM_Explore 初始状态不是 idle")

    state, _content = machine.trigger("start")
    check(state == "selecting_dungeon", f"start 转移错误: {state}")
    state, _content = machine.trigger("dungeon_selected")
    check(state == "entering", f"dungeon_selected 转移错误: {state}")
    state, _content = machine.trigger("entered")
    check(state == "on_floor", f"entered 转移错误: {state}")
    check(len(machine.history) == 3, f"转移历史条数错误: {len(machine.history)}")

    rejected, reason = machine.trigger("no_such_event")
    check(rejected is None and isinstance(reason, str), "非法事件未被拒绝")

    machine.reset()
    check(machine.current_state_id == "idle", "reset 未回到初始状态")
    check(machine.history == [], "reset 未清空转移历史")
    return "SM_Explore"


def main() -> int:
    try:
        loader = load_game_data()
        counts, missing_skill_refs = check_data_integrity(loader)

        weakest = min(loader.monsters.values(), key=lambda m: (m.hp, m.name))
        gold, exp = check_battle(loader, weakest)

        machine_name = check_state_machine()

        print(
            "selfcheck ok: 数据加载与结构校验通过 "
            f"({counts['jobs']}职业/{counts['skills']}技能/{counts['equipment']}装备/"
            f"{counts['monsters']}怪物/{counts['dungeons']}地下城，"
            f"兼容 {missing_skill_refs} 个未收录技能引用)；"
            f"战斗胜利结算 {gold} 金币 {exp} 经验；{machine_name} 3 步状态推进与重置"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - 自检入口统一转为 FAIL
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
