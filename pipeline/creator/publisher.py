"""发布物料导出：生成方便一键复制到自媒体平台（小红书/抖音等）的发布文档。

内容含：标题、正文、话题标签(#xxx)、配图顺序、语音解说文件名、合规提示。
默认保留原文（含 emoji），确保复制粘贴与发布内容一致。
"""
import os


def render_publish_doc(content, out_dir, assets=None, audio=None, narration=None):
    """把一篇草稿整理成 `发布文案.md`，写入 out_dir，返回文件路径。

    正文仅用 body（发布用完整正文）；closing 是尾页图上的互动引导，不重复进正文。
    口播稿(narration)随文档生成供确认；配音(audio)需确认后单独生成，不与出图绑定。
    """
    title = content.get("title", "")
    body = content.get("body", "") or ""
    tags = content.get("tags", []) or []

    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("> 复制以下内容到小红书/抖音等平台；图片按文件名序号顺序上传。")
    lines.append("> 语音解说：确认⑤口播稿没问题后，再单独生成配音（会消耗 MiniMax 额度）。")
    lines.append("")

    lines.append("## ① 标题（可直接复制）")
    lines.append("")
    lines.append(title)
    lines.append("")

    lines.append("## ② 正文（可直接复制）")
    lines.append("")
    lines.append(body)
    lines.append("")

    lines.append("## ③ 话题标签（可追加到正文末尾）")
    lines.append("")
    lines.append(" ".join(tags) if tags else "（无）")
    lines.append("")

    if assets:
        lines.append("## ④ 配图顺序（按序号上传）")
        lines.append("")
        for a in assets:
            lines.append(f"- {os.path.basename(a)}")
        lines.append("")

    if narration:
        lines.append("## ⑤ 语音解说口播稿（确认无误后再生成配音）")
        lines.append("")
        lines.append(narration)
        lines.append("")

    if audio:
        lines.append("## ⑥ 语音解说文件（发布配乐）")
        lines.append("")
        lines.append(f"- 文件：{os.path.basename(audio)}（女声口播，内容与上方口播稿一致）")
        lines.append("")

    lines.append("## 合规提示")
    lines.append("")
    lines.append("- 精确数据（招生人数/分数线/报录比/学费等）发布前请以学校官网/研招网最新公布为准。")
    lines.append("- 本内容由自动化流水线生成，发布前建议人工通读一遍。")

    path = os.path.join(out_dir, "发布文案.md")
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
