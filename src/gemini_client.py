"""Gemini API client.

Calls the Gemini REST API directly via `requests` — no SDK dependency.
Falls back gracefully when the key is missing or the API fails.
"""
from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

import requests

from .models import FilteredItem

logger = logging.getLogger("tech-radar.gemini")

# Primary model, fallback chain on 503/429/network errors
_MODEL_CHAIN = [
    "gemini-flash-latest",      # stable alias, no thinking overhead
    "gemini-2.5-flash-lite",    # lighter/faster
    "gemini-2.5-flash",         # full version (may be slow)
]
_GEMINI_ENDPOINT_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

# ---------------------------------------------------------------------------
# System prompt (do not weaken)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
你是我的"疯狂发明家技术雷达"。

你的任务不是普通新闻总结，而是每天帮我搜索、筛选、解释最新技术栈趋势和有趣项目，并把它们转化成可执行的发明灵感。

我的背景：
- 我是设计/艺术 + CS 跨学科学生。
- 我关注 AI、agent、spec-driven development、creative coding、game systems、Minecraft/世界生成、LLM工具链、自动化、HCI、艺术技术、生成式系统。
- 我喜欢"疯狂但可做"的发明，不喜欢泛泛的科技新闻。
- 输出要帮助我产生项目灵感，而不是制造信息焦虑。

请从候选内容中选出 5 条以内。

每条必须满足至少一个条件：
- 对 AI 开发工作流有启发
- 可以变成我自己的项目
- 适合艺术/设计/游戏/叙事系统结合
- 能启发 Drift、spec-driven、agent workflow、creative tool、自动化系统
- 足够新、足够怪、足够可实验

每条内容按这个格式输出：

## [标题]
- 来源：
- 链接：
- 一句话解释：
- 它为什么重要：
- 技术趋势标签：
- 可复用模式：
- 疯狂发明家灵感：
  1. 一个小实验
  2. 一个中型项目
  3. 一个艺术/游戏/叙事方向
- 对我项目的启发：
- 今天是否值得深入研究：是/否
- 建议行动：收藏 / 试用 / 做demo / 忽略

最后输出：

## 今日模式总结
总结今天出现的 2-3 个技术模式。

## 今日可做小实验
给我一个 2 小时内能做的小实验，必须具体到：
- 项目名
- 输入
- 输出
- 技术栈
- 第一步怎么做

风格要求：
- 中文输出
- 直接、兴奋、但不吹水
- 不要给我太多内容
- 不要变成新闻简报
- 要像一个懂技术、懂艺术、懂项目孵化的研究助手
"""

# ---------------------------------------------------------------------------
# Mock response (used when GEMINI_API_KEY is not set)
# ---------------------------------------------------------------------------

_MOCK_RESPONSE = """\
> 🔧 **Mock 模式** — 未设置 GEMINI_API_KEY，以下为示例输出格式。

## Open Interpreter：本地运行代码的 AI Agent
- 来源：Hacker News
- 链接：https://github.com/OpenInterpreter/open-interpreter
- 一句话解释：让 LLM 直接在你的电脑上执行 Python/Shell/JS，像 ChatGPT Code Interpreter 的开源本地版。
- 它为什么重要：把"让 AI 帮我做事"从云端拉到本地，意味着可以访问文件系统、调用 API、自动化任何工作流。
- 技术趋势标签：`local-agent` `code-execution` `automation` `open-source`
- 可复用模式：LLM + 安全沙箱 + 工具调用 = 可编程 AI 助手
- 疯狂发明家灵感：
  1. 小实验：让它帮你自动整理 Downloads 文件夹并分类
  2. 中型项目：搭一个"创意项目日志"Bot，每天早上总结昨天的 git commit 并生成灵感报告
  3. 艺术/游戏方向：用它驱动 Blender 脚本自动生成程序化世界
- 对我项目的启发：可以作为 Drift 系统的本地执行层，spec → agent → 代码直接落地
- 今天是否值得深入研究：是
- 建议行动：做demo

## 今日模式总结
1. **Local-first Agent**：AI 工具从云端服务转向本地执行，强调隐私和可控性。
2. **LLM × 工具调用**：Function calling / tool use 成为标准范式，任何 API 都可以被 AI 调用。

## 今日可做小实验
- **项目名**：AutoCommitLog
- **输入**：git log --oneline（最近 7 天的 commit）
- **输出**：一段 200 字中文项目进展摘要 + 下一步建议
- **技术栈**：Python + subprocess + Gemini API
- **第一步**：`subprocess.run(['git', 'log', '--oneline', '--since=7 days ago'], capture_output=True)` 然后把输出传给 Gemini 的 prompt
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_candidates(items: List[FilteredItem]) -> str:
    """Render candidate items as structured text for the prompt."""
    lines = ["以下是今日候选内容，请按照系统要求分析并选出最有价值的 5 条以内：\n"]
    for i, item in enumerate(items, 1):
        lines.append(f"### 候选 {i}：{item.title}")
        lines.append(f"- 来源：{item.source}")
        lines.append(f"- 链接：{item.url}")
        if item.description:
            lines.append(f"- 摘要：{item.description[:400]}")
        if item.keywords_matched:
            lines.append(f"- 命中关键词：{', '.join(item.keywords_matched)}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _call_model(model: str, key: str, payload: dict) -> str:
    """Make one Gemini API call. Returns response text or raises RuntimeError."""
    endpoint = _GEMINI_ENDPOINT_TMPL.format(model=model)
    resp = requests.post(
        endpoint,
        headers={"Content-Type": "application/json"},
        json=payload,
        params={"key": key},
        timeout=90,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"HTTP {resp.status_code}: {resp.text[:300]}"
        )
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        finish = data.get("promptFeedback", {})
        raise RuntimeError(f"No candidates returned. Feedback: {finish}")
    # Concatenate all parts (model may split output into multiple parts)
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    finish_reason = candidates[0].get("finishReason", "")
    if finish_reason not in ("", "STOP", None):
        logger.warning("  finishReason=%s (output may be truncated)", finish_reason)
    return text


def analyze(items: List[FilteredItem], api_key: Optional[str] = None) -> str:
    """Call Gemini API and return the analysis as a Markdown string.

    Tries each model in _MODEL_CHAIN; retries once on 503/429 with backoff.

    Raises:
        ValueError: If GEMINI_API_KEY is not configured or items is empty.
        RuntimeError: If all models fail.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set — set it in .env or GitHub Secrets.")
    if not items:
        raise ValueError("No candidate items to analyze.")

    full_prompt = f"{SYSTEM_PROMPT}\n\n---\n\n{_format_candidates(items)}"

    last_error = ""
    for model in _MODEL_CHAIN:
        # Build payload per-model: thinkingConfig only supported by 2.5-series
        gen_config: dict = {"temperature": 0.75, "maxOutputTokens": 8192}
        if "2.5" in model:
            # Disable thinking tokens so full budget goes to visible output
            gen_config["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": gen_config,
        }
        for attempt in range(1, 3):  # max 2 attempts per model
            logger.info("Calling Gemini API (%s, attempt %d)…", model, attempt)
            try:
                text = _call_model(model, key, payload)
                logger.info("Gemini response received (%d chars) from %s.", len(text), model)
                return text
            except RuntimeError as exc:
                last_error = str(exc)
                if "503" in last_error or "429" in last_error or "UNAVAILABLE" in last_error:
                    wait = 10 * attempt
                    logger.warning("  %s — retrying in %ds…", last_error[:120], wait)
                    time.sleep(wait)
                else:
                    logger.warning("  %s — trying next model.", last_error[:120])
                    break  # non-transient error, skip to next model            except Exception as exc:
                # Network/proxy errors — retry once then move to next model
                last_error = str(exc)
                if attempt == 1:
                    logger.warning("  Network error: %s \u2014 retrying in 15s\u2026", last_error[:120])
                    time.sleep(15)
                else:
                    logger.warning("  Network error: %s \u2014 trying next model.", last_error[:120])
                    break
    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")


def make_fallback_report(date: str, items: List[FilteredItem], error: str) -> str:
    """Generate a minimal fallback Markdown report when Gemini is unavailable."""
    lines = [
        f"> ⚠️ AI 分析失败：{error}",
        "",
        "## 今日候选内容（原始抓取，未经 AI 分析）",
        "",
    ]
    for item in items[:15]:
        lines.append(f"### {item.title}")
        lines.append(f"- 来源：{item.source}")
        lines.append(f"- 链接：{item.url}")
        if item.description:
            lines.append(f"- 摘要：{item.description[:250]}")
        if item.keywords_matched:
            lines.append(f"- 关键词：{', '.join(item.keywords_matched)}")
        lines.append("")

    lines += [
        "---",
        "",
        "> 请配置 `GEMINI_API_KEY` 后重新运行以获取完整分析。",
    ]
    return "\n".join(lines)


def mock_analyze(items: List[FilteredItem]) -> str:
    """Return mock analysis output for local testing without an API key."""
    logger.info("Using mock Gemini response (MOCK_MODE=true).")
    return _MOCK_RESPONSE
