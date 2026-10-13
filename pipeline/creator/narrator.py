"""配图语音解说：把文案转成女声（学姐音色）口播 mp3，用于发布时的配乐/解说。

默认用 macOS 内置 `say`（零成本、离线、无需 key），女声选 Tingting（婷婷，年轻女声）。
- 音色/语速可用环境变量覆盖：TTS_VOICE（默认 Tingting）、TTS_RATE（默认 205）。
- 生成 aiff 后转 mp3（优先 ffmpeg，缺失则 afconvert 转 m4a）。
- 若配了 ElevenLabs key（ELEVENLABS_API_KEY），可改用更自然的高质量音色（见 synthesize_elevenlabs）。
"""
import os
import re
import shutil
import subprocess

DEFAULT_VOICE = os.getenv("TTS_VOICE", "Tingting")
DEFAULT_RATE = os.getenv("TTS_RATE", "205")


def _clean_for_tts(s):
    """清掉 emoji/markdown 符号，保留中文/数字/标点，适合朗读。"""
    s = str(s)
    kept = []
    for ch in s:
        o = ord(ch)
        if o >= 0x1F000:            # 绝大多数 emoji
            continue
        if ch in "#*_`>[]()|~":
            continue
        kept.append(ch)
    s = "".join(kept)
    s = re.sub(r"[✔✅✗✖❌❓⚠❗⭐🌟💡📌👉🔥✨🎯❤️→➡·•]", "", s)
    s = re.sub(r"\n+", "。", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def build_narration(content):
    """从文案组装口播稿：标题 → 每页(小标题+要点) → 结尾。与配图内容一致。"""
    parts = []
    title = _clean_for_tts(content.get("title", ""))
    if title:
        parts.append(title)
    for pg in content.get("pages", []) or []:
        seg = []
        h = _clean_for_tts(pg.get("heading", ""))
        if h:
            seg.append(h)
        texts = list(pg.get("points", []) or [])
        for it in (pg.get("items", []) or []):
            if isinstance(it, dict):
                texts.append(f'{it.get("title", "")}，{it.get("desc", "")}')
            else:
                texts.append(str(it))
        texts += (pg.get("left", []) or []) + (pg.get("right", []) or [])
        if pg.get("quote"):
            texts.append(pg.get("quote"))
        for t in texts:
            t = _clean_for_tts(t)
            if t:
                seg.append(t)
        if seg:
            parts.append("。".join(seg))
    closing = _clean_for_tts(content.get("closing", ""))
    if closing:
        parts.append(closing)
    text = "。".join(p for p in parts if p)
    return (text + "。") if text else ""


def _say_to_file(text, aiff_path, voice, rate):
    subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", aiff_path, text],
                   check=True, timeout=600)


def _convert_to_mp3(aiff_path, mp3_path):
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-i", aiff_path, "-codec:a", "libmp3lame",
                        "-qscale:a", "4", mp3_path], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        return mp3_path
    # 无 ffmpeg：用系统 afconvert 转 m4a(AAC)
    m4a = os.path.splitext(mp3_path)[0] + ".m4a"
    subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "128000",
                    aiff_path, m4a], check=True, timeout=600)
    return m4a


def synthesize(text, out_path, voice=DEFAULT_VOICE, rate=DEFAULT_RATE):
    """把口播稿合成为音频文件，返回生成的音频路径（失败返回 None）。"""
    if not text or not shutil.which("say"):
        return None
    aiff = out_path + ".aiff"
    try:
        _say_to_file(text, aiff, voice, rate)
        result = _convert_to_mp3(aiff, out_path)
        return result
    finally:
        if os.path.exists(aiff):
            os.remove(aiff)


def narrate(content, out_dir, filename="语音解说.mp3"):
    """为一篇文案生成语音解说，写入 out_dir，返回音频路径（无 say 或空稿则 None）。"""
    text = build_narration(content)
    if not text:
        return None
    out_path = os.path.join(out_dir, filename)
    return synthesize(text, out_path)
