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

from ..config import settings  # noqa: F401  确保 .env 已加载进 os.environ

DEFAULT_VOICE = os.getenv("TTS_VOICE", "Tingting")
DEFAULT_RATE = os.getenv("TTS_RATE", "205")
# TTS_PROVIDER: say(系统,默认) | elevenlabs(自然/可克隆,需 ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID)
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "say").lower()


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
    """把口播稿合成为音频文件，返回生成的音频路径（失败返回 None）。

    provider=elevenlabs 时优先用 ElevenLabs（自然/可克隆音色）；缺 key/voice 则回退系统 say。
    """
    if not text:
        return None
    if os.getenv("TTS_PROVIDER", "say").lower() == "elevenlabs":
        r = synthesize_elevenlabs(text, out_path)
        if r:
            return r
        print("[narrator] ElevenLabs 不可用(缺 key/voice_id?)，回退系统 say")
    if not shutil.which("say"):
        return None
    aiff = out_path + ".aiff"
    try:
        _say_to_file(text, aiff, voice, rate)
        result = _convert_to_mp3(aiff, out_path)
        return result
    finally:
        if os.path.exists(aiff):
            os.remove(aiff)


def synthesize_elevenlabs(text, out_path, voice_id=None,
                          model="eleven_multilingual_v2"):
    """用 ElevenLabs 合成（支持克隆音色、有感情、中文自然）。返回音频路径或 None。"""
    import requests
    key = os.getenv("ELEVENLABS_API_KEY", "")
    voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "")
    if not (key and voice_id):
        return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": key, "Content-Type": "application/json",
               "Accept": "audio/mpeg"}
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8,
                           "style": 0.35, "use_speaker_boost": True},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)
    return out_path


def clone_voice(name, audio_paths, description=""):
    """用录音做 ElevenLabs 即时克隆(IVC)，返回 voice_id。

    audio_paths: 1..N 段干净录音(建议 1-5 分钟、女声、安静无背景音、无混响)。
    需要 ELEVENLABS_API_KEY；Instant Voice Clone 需付费套餐。
    """
    import requests
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        raise RuntimeError("缺少 ELEVENLABS_API_KEY（写入 .env）")
    handles = [open(p, "rb") for p in audio_paths]
    try:
        files = [("files", (os.path.basename(p), h, "audio/mpeg"))
                 for p, h in zip(audio_paths, handles)]
        data = {"name": name, "description": description or f"{name}（克隆音色）"}
        resp = requests.post("https://api.elevenlabs.io/v1/voices/add",
                             headers={"xi-api-key": key}, files=files, data=data,
                             timeout=300)
        resp.raise_for_status()
        return resp.json().get("voice_id")
    finally:
        for h in handles:
            h.close()


def narrate(content, out_dir, filename="语音解说.mp3"):
    """为一篇文案生成语音解说，写入 out_dir，返回音频路径（无 say 或空稿则 None）。"""
    text = build_narration(content)
    if not text:
        return None
    out_path = os.path.join(out_dir, filename)
    return synthesize(text, out_path)
