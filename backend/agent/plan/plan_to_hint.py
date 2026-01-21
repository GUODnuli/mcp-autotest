# -*- coding: utf-8 -*-
"""
自定义计划提示词生成器。
将 AgentScope 的默认提示词翻译为中文，并针对 MCP 自动化测试场景进行优化。
"""
from agentscope.plan._plan_model import Plan

class CustomPlanToHint:
    """
    自定义函数，根据当前计划生成提示信息，引导智能体执行下一步。
    """

    hint_prefix: str = "<system-hint>"
    hint_suffix: str = "</system-hint>"

    no_plan: str = (
        "如果用户的请求比较复杂（例如：编写一个网站、游戏或应用，或者需要执行一系列复杂的自动化测试步骤）， "
        "或者需要多个步骤才能完成（例如：从不同来源对特定主题进行研究，或者执行端到端的接口测试流程），"
        "你需要先通过调用 'create_plan' 来创建一个计划。否则，你可以直接执行用户的查询而无需规划。"
    )

    at_the_beginning: str = (
        "当前计划：\n"
        "```\n"
        "{plan}\n"
        "```\n"
        "你的选项包括：\n"
        "- 调用 'update_subtask_state' 并设置 subtask_idx=0 且 state='in_progress'，将第一个子任务标记为 '进行中'，然后开始执行它。\n"
        "- 如果第一个子任务无法立即执行，请分析原因以及你可以采取什么行动来推进计划，例如：询问用户更多信息，或者调用 'revise_current_plan' 修改计划。\n"
        "- 如果用户要求你做一些与计划无关的事情，请优先完成用户的查询，然后再回到计划中。\n"
        "- 如果用户不再希望执行当前计划，请与用户确认并调用 'finish_plan' 函数。\n"
    )

    when_a_subtask_in_progress: str = (
        "当前计划：\n"
        "```\n"
        "{plan}\n"
        "```\n"
        "现在索引为 {subtask_idx} 的子任务 '{subtask_name}' 处于 '进行中'。其详细信息如下：\n"
        "```\n"
        "{subtask}\n"
        "```\n"
        "你的选项包括：\n"
        "- 继续执行该子任务并获取结果。\n"
        "- 如果子任务已完成，请调用 'finish_subtask' 并提供具体的结果（Outcome）。\n"
        "- 如果需要，请向用户询问更多信息。\n"
        "- 如有必要，请通过调用 'revise_current_plan' 来修改计划。\n"
        "- 如果用户要求你做一些与计划无关的事情，请优先完成用户的查询，然后再回到计划中。"
    )

    when_no_subtask_in_progress: str = (
        "当前计划：\n"
        "```\n"
        "{plan}\n"
        "```\n"
        "前 {index} 个子任务已完成，目前没有正在进行（in_progress）的子任务。现在你的选项包括：\n"
        "- 通过调用 'update_subtask_state' 将下一个子任务标记为 '进行中'，并开始执行它。\n"
        "- 如果需要，请向用户询问更多信息。\n"
        "- 如有必要，请通过调用 'revise_current_plan' 来修改计划。\n"
        "- 如果用户要求你做一些与计划无关的事情，请优先完成用户的查询，然后再回到计划中。"
    )

    at_the_end: str = (
        "当前计划：\n"
        "```\n"
        "{plan}\n"
        "```\n"
        "所有子任务均已完成。现在你的选项包括：\n"
        "- 调用 'finish_plan' 并提供具体的执行结果，完成计划，并向用户总结整个过程和结果。\n"
        "- 如有必要，请通过调用 'revise_current_plan' 来修改计划。\n"
        "- 如果用户要求你做一些与计划无关的事情，请优先完成用户的查询，然后再回到计划中。"
    )

    def __call__(self, plan: Plan | None) -> str | None:
        """根据输入的计划生成提示词，引导智能体采取下一步行动。"""
        if plan is None:
            hint = self.no_plan

        else:
            # 统计子任务状态
            n_todo, n_in_progress, n_done, n_abandoned = 0, 0, 0, 0
            in_progress_subtask_idx = None
            for idx, subtask in enumerate(plan.subtasks):
                if subtask.state == "todo":
                    n_todo += 1
                elif subtask.state == "in_progress":
                    n_in_progress += 1
                    in_progress_subtask_idx = idx
                elif subtask.state == "done":
                    n_done += 1
                elif subtask.state == "abandoned":
                    n_abandoned += 1

            hint = None
            if n_in_progress == 0 and n_done == 0:
                # 所有子任务都是待办状态
                hint = self.at_the_beginning.format(
                    plan=plan.to_markdown(),
                )
            elif n_in_progress > 0 and in_progress_subtask_idx is not None:
                # 有一个子任务正在进行中
                hint = self.when_a_subtask_in_progress.format(
                    plan=plan.to_markdown(),
                    subtask_idx=in_progress_subtask_idx,
                    subtask_name=plan.subtasks[in_progress_subtask_idx].name,
                    subtask=plan.subtasks[in_progress_subtask_idx].to_markdown(
                        detailed=True,
                    ),
                )
            elif n_in_progress == 0 and n_done > 0 and (n_done + n_abandoned < len(plan.subtasks)):
                # 没有正在进行的子任务，但有些已经完成，且还有待办任务
                hint = self.when_no_subtask_in_progress.format(
                    plan=plan.to_markdown(),
                    index=n_done,
                )
            elif n_done + n_abandoned == len(plan.subtasks):
                # 所有子任务都已完成或废弃
                hint = self.at_the_end.format(
                    plan=plan.to_markdown(),
                )

        if hint:
            return f"{self.hint_prefix}{hint}{self.hint_suffix}"

        return hint
