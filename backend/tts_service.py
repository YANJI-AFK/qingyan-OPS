"""
TTS 语音合成服务模块

支持三种引擎（按音色 id 前缀分发）：
1. Microsoft SAPI —— Windows 系统语音（离线，含神经网络音色，音质最佳）
2. sherpa-onnx VITS —— 离线神经网络 TTS（支持多模型，见 SHERPA_MODELS）
3. edge-tts —— 微软在线神经网络语音（需联网，auto 模式可选）

音色 id 约定：
- sapi-<index>         : SAPI 系统语音（离线，按质量排序：神经网络 > 传统语音）
- sherpa-<sid>         : sherpa zh-ll 模型音色（离线，向后兼容）
- sherpa-<模型>-<sid>  : 其他 sherpa 模型音色（如 sherpa-melo-0 / sherpa-theresa-10）
- zh-CN-XiaoxiaoNeural 等 : edge-tts 在线音色

环境变量：
- TTS_MODE: offline（默认，强制离线：只暴露 sapi + sherpa）
            auto（同时暴露 edge-tts，优先在线音色）
- SHERPA_TTS_DIR: sherpa zh-ll 模型目录（默认 C:\\sherpa-tts\\sherpa-onnx-vits-zh-ll）
"""
import threading
import queue
import time
import os
import io
import struct
import tempfile
import subprocess
import wave

# ====== edge-tts 支持（需 pip install edge-tts） ======
_USE_EDGE = False
try:
    import edge_tts  # noqa: F401
    _USE_EDGE = True
except ImportError:
    pass

# ====== SAPI 降级方案 ======
try:
    import win32com.client
    import pythoncom
    _use_sapi = True
except ImportError:
    _use_sapi = False
    import pyttsx3

# ====== 引擎模式 ======
TTS_MODE = os.getenv("TTS_MODE", "offline")  # offline | auto
# zh-ll 模型目录（默认模型，兼容旧环境变量 SHERPA_TTS_DIR）
_DEFAULT_SHERPA_DIR = os.getenv(
    "SHERPA_TTS_DIR", r"C:\sherpa-tts\sherpa-onnx-vits-zh-ll"
)

# ====== sherpa-onnx 多模型注册表 ======
# key       : 内部标识，用于音色 id（sherpa-<key>-<sid>）
# dir       : 模型目录
# onnx_name : 模型文件名（部分模型用专属命名，如 theresa.onnx）
# label     : 音色列表中的展示标签
# voices    : 说话人列表（sid → 名称/性别）；为空时尝试从模型目录动态读取
SHERPA_MODELS = {
    "zh-ll": {
        "dir": _DEFAULT_SHERPA_DIR,
        "onnx_name": "model.onnx",
        "label": "VITS 5音色",
        "voices": [
            {"sid": 0, "name": "苏樱雪", "gender": "female"},
            {"sid": 1, "name": "古念", "gender": "female"},
            {"sid": 2, "name": "傅诗雨", "gender": "female"},
            {"sid": 3, "name": "冰娇", "gender": "female"},
            {"sid": 4, "name": "霸总", "gender": "male"},
        ],
    },
    "melo": {
        "dir": r"C:\sherpa-tts\vits-melo-tts-zh_en",
        "onnx_name": "model.onnx",
        "label": "VITS 中英混合",
        "voices": [
            {"sid": 0, "name": "Melo女声", "gender": "female"},
        ],
    },
    "fanchen": {
        "dir": r"C:\sherpa-tts\vits-zh-hf-fanchen-wnj",
        "onnx_name": "vits-zh-hf-fanchen-wnj.onnx",
        "label": "VITS 男声",
        "voices": [
            {"sid": 0, "name": "繁辰男声", "gender": "male"},
        ],
    },
}
# theresa（海量音色 说话人0~19）已移除：音色质量不佳，用户要求不再展示
# 多说话人模型在前端下拉框中最多展示的精选数量（为未来新增模型预留）
SHERPA_MAX_VOICES_PER_MODEL = 20

# SAPI 神经网络中文音色关键词（Windows 10/11 Natural Voices）
NEURAL_VOICE_KEYWORDS = [
    "xiaoxiao", "xiaoyi", "yunxi", "yunjian", "yunyang", "xiaochen",
    "晓晓", "晓伊", "云希", "云健", "云扬", "晓辰",
    "natural",   # "Microsoft Xiaoxiao Online (Natural)"
]
# 非神经网络中文音色关键词（传统 SAPI5 语音）
TRADITIONAL_CHINESE_KEYWORDS = [
    "huihui", "hui", "yaoyao", "chinese", "zh", "中文",
    "kangkang", "hanhan", "hong",
]

_tts_queue = queue.Queue()
_tts_worker_running = False

# ====== sherpa-onnx 懒加载（按模型 key 缓存） ======
_sherpa_tts_cache: dict = {}          # model_key -> OfflineTts 实例
_sherpa_error_cache: dict = {}        # model_key -> 错误信息


def _sherpa_model_onnx(model_key: str) -> str:
    """返回模型 ONNX 路径（不存在返回空串）"""
    cfg = SHERPA_MODELS.get(model_key, {})
    fname = cfg.get("onnx_name", "model.onnx")
    p = os.path.join(cfg.get("dir", ""), fname)
    return p if os.path.exists(p) else ""


def _get_sherpa_tts(model_key: str = "zh-ll"):
    """懒加载指定 sherpa-onnx TTS 实例（模型不存在/加载失败返回 None）"""
    if model_key in _sherpa_tts_cache:
        return _sherpa_tts_cache[model_key]
    cfg = SHERPA_MODELS.get(model_key, {})
    model_dir = cfg.get("dir", "")
    model_onnx = _sherpa_model_onnx(model_key)
    if not model_onnx:
        _sherpa_error_cache[model_key] = f"模型不存在: {model_dir}"
        print(f"[TTS] sherpa-onnx [{model_key}] {_sherpa_error_cache[model_key]}")
        return None
    try:
        import sherpa_onnx
        # 各文件按存在性动态配置（不同模型包结构略有差异）
        lexicon = os.path.join(model_dir, "lexicon.txt")
        tokens = os.path.join(model_dir, "tokens.txt")
        dict_dir = os.path.join(model_dir, "dict")
        data_dir = os.path.join(model_dir, "espeak-ng-data")
        fsts = []
        for f in ["date.fst", "number.fst", "phone.fst", "new_heteronym.fst"]:
            p = os.path.join(model_dir, f)
            if os.path.exists(p):
                fsts.append(p)
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=model_onnx,
                    tokens=tokens,
                    lexicon=lexicon,
                    dict_dir=dict_dir if os.path.isdir(dict_dir) else "",
                    data_dir=data_dir if os.path.isdir(data_dir) else "",
                ),
                num_threads=2,
                provider="cpu",
                debug=False,
            ),
            rule_fsts=",".join(fsts),
            max_num_sentences=1,
            rule_fars="",
        )
        _sherpa_tts_cache[model_key] = sherpa_onnx.OfflineTts(config)
        n_spk = len(_get_model_voices(model_key))
        print(f"[TTS] sherpa-onnx [{model_key}] 加载成功: {model_dir} ({n_spk} 音色)")
        return _sherpa_tts_cache[model_key]
    except Exception as e:
        _sherpa_error_cache[model_key] = str(e)
        print(f"[TTS] sherpa-onnx [{model_key}] 初始化失败: {e}")
        return None


def _read_speaker_names(model_dir: str) -> list:
    """
    从模型目录读取说话人名称映射。
    优先 speakers.txt（行格式: sid 名称），其次 G_multispeaker_latest.json。
    返回 None 表示未找到映射文件。
    """
    try:
        sp = os.path.join(model_dir, "speakers.txt")
        if os.path.exists(sp):
            result = []
            with open(sp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.replace("\t", " ").split()
                    if len(parts) >= 2:
                        try:
                            result.append((int(parts[0]), " ".join(parts[1:])))
                        except ValueError:
                            continue
            if result:
                return result
        jp = os.path.join(model_dir, "G_multispeaker_latest.json")
        if os.path.exists(jp):
            import json
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            speakers = data.get("speakers", {}) if isinstance(data, dict) else {}
            result = []
            for k, v in speakers.items():
                try:
                    result.append((int(k), str(v)))
                except (ValueError, TypeError):
                    continue
            if result:
                return sorted(result)
    except Exception as e:
        print(f"[TTS] 读取说话人映射失败: {e}")
    return None


def _get_model_voices(model_key: str) -> list:
    """获取模型音色列表（静态注册表 + 动态读取）"""
    cfg = SHERPA_MODELS.get(model_key, {})
    voices = list(cfg.get("voices", []))
    if voices:
        return voices
    # 注册表为空：尝试从模型目录读取说话人映射
    names = _read_speaker_names(cfg.get("dir", ""))
    if names:
        for sid, name in names[:SHERPA_MAX_VOICES_PER_MODEL]:
            voices.append({"sid": sid, "name": name, "gender": "unknown"})
        if voices:
            return voices
    # 仍为空：尝试通过已加载的 sherpa-onnx 实例获取 num_speakers
    tts = _get_sherpa_tts(model_key)
    if tts is not None:
        n_spk = getattr(tts, "num_speakers", 1) or 1
        for sid in range(min(n_spk, SHERPA_MAX_VOICES_PER_MODEL)):
            voices.append({"sid": sid, "name": f"说话人{sid}", "gender": "unknown"})
        if voices:
            return voices
    # 兜底
    return [{"sid": 0, "name": "默认音色", "gender": "unknown"}]


def _synthesize_sherpa(text: str, rate: int = 0, sid: int = 0, model_key: str = "zh-ll") -> bytes:
    """sherpa-onnx VITS 离线神经网络合成 → 16bit PCM WAV bytes"""
    tts = _get_sherpa_tts(model_key)
    if tts is None:
        raise RuntimeError(f"sherpa-onnx [{model_key}] 模型未加载")
    import numpy as np

    speed = max(0.5, min(2.0, 1.0 + rate * 0.05))
    audio = tts.generate(text, sid=sid, speed=speed)
    if audio is None or len(audio.samples) == 0:
        raise RuntimeError(f"sherpa-onnx [{model_key}] 合成结果为空")
    pcm = (np.asarray(audio.samples) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(audio.sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _parse_sherpa_voice(voice_name: str):
    """
    解析 sherpa 音色 id → (model_key, sid)
    - sherpa-<sid>        → zh-ll 模型（向后兼容）
    - sherpa-<模型>-<sid> → 指定模型
    非法格式返回 (None, None)
    """
    parts = voice_name.split("-")
    if len(parts) == 2:
        try:
            return "zh-ll", int(parts[1])
        except ValueError:
            return None, None
    if len(parts) == 3 and parts[1] in SHERPA_MODELS:
        try:
            return parts[1], int(parts[2])
        except ValueError:
            return None, None
    return None, None


# ====== SAPI 语音质量评分与排序 ======

def _score_sapi_voice(desc: str, attributes: str) -> int:
    """
    对 SAPI 语音评分，分数越高越好（用于排序）
    神经网络中文: 100+
    传统中文:     80+
    神经网络其他: 60+
    传统其他:     0+
    """
    low = desc.lower()
    score = 0
    # 神经网络语音：高分（Windows 自然语音/OneCore neural）
    if any(kw in low for kw in ["natural", "online"]):
        score += 30
    # 中文：高分
    is_zh = "中文" in desc or "Chinese" in desc or "804" in str(attributes)
    if is_zh or any(kw in low for kw in ["xiaoxiao", "xiaoyi", "yunxi", "yunjian",
                                           "yunyang", "xiaochen", "huihui", "hui",
                                           "yaoyao", "kangkang", "hanhan", "hong"]):
        score += 50
    # 特定音色加分
    if "xiaoxiao" in low:       # 晓晓 — 最佳
        score += 20
    elif "xiaoyi" in low:       # 晓伊
        score += 15
    elif "yunxi" in low:        # 云希（男声）
        score += 10
    elif "huihui" in low:       # 慧慧
        score += 5
    elif "yaoyao" in low:       # 瑶瑶
        score += 3
    elif "kangkang" in low:     # 康康
        score += 3
    # OneCore 语音（非 Desktop）质量更优，排前
    if "desktop" in low:
        score -= 15             # 旧版桌面语音质量较差
    else:
        score += 15             # OneCore 新版语音
    # 女声偏好
    if any(kw in low for kw in ["female", "女"]):
        score += 2
    return score


# 缓存 SAPI 语音列表（启动后不变）
_sapi_voice_cache: list = None


def _list_sapi_voices() -> list:
    """
    动态枚举系统 SAPI 语音，按质量排序
    返回格式: [{"id": "sapi-N", "name": "...", "gender": "...", "score": N}, ...]
    """
    global _sapi_voice_cache
    if _sapi_voice_cache is not None:
        return _sapi_voice_cache
    result = []
    if not _use_sapi:
        return result
    try:
        pythoncom.CoInitialize()
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voices = voice.GetVoices()
        raw = []
        for i in range(voices.Count):
            v = voices.Item(i)
            desc = v.GetDescription()
            try:
                attrs = v.GetAttribute("Language") or ""
            except Exception:
                attrs = ""
            raw.append({"index": i, "desc": desc, "attrs": str(attrs)})
        # 按评分倒序：最佳音色在前
        raw.sort(key=lambda x: _score_sapi_voice(x["desc"], x["attrs"]), reverse=True)
        for rank, item in enumerate(raw):
            desc = item["desc"]
            low = desc.lower()
            is_neural = any(kw in low for kw in ["natural", "online"])
            is_zh = "中文" in desc or "Chinese" in desc or "804" in item["attrs"]
            short = desc.split(" - ")[0].strip()
            # 标签
            if is_neural:
                tag = "神经网络语音"
            elif is_zh:
                tag = "中文语音"
            else:
                tag = "系统语音"
            # 性别
            if any(k in low for k in ["female", "女", "hui", "huihui", "zira", "xiaoxiao", "xiaoyi", "xiaochen",
                                       "hanhan", "yaoyao"]):
                gender = "female"
            elif any(k in low for k in ["male", "男", "yunxi", "yunjian", "yunyang", "kangkang", "hong"]):
                gender = "male"
            else:
                gender = "unknown"
            result.append({
                "id": f"sapi-{item['index']}",
                "sapi_index": item["index"],
                "name": f"[{tag}] {short}",
                "gender": gender,
                "score": _score_sapi_voice(desc, item["attrs"]),
                "description": desc,
            })
    except Exception as e:
        print(f"[TTS] 枚举 SAPI 语音失败: {e}")
    _sapi_voice_cache = result
    return result


def _get_best_sapi_index() -> int:
    """获取最佳中文 SAPI 语音的枚举序号（离线可用）"""
    voices = _list_sapi_voices()
    if not voices:
        return 0
    return voices[0].get("sapi_index", 0)


def _get_sapi_voice_name() -> str:
    """获取最佳中文 SAPI 语音名称（用于日志）"""
    voices = _list_sapi_voices()
    if voices:
        return voices[0].get("description", "默认语音")
    return "默认语音"


def _synthesize_sapi(text: str, rate: int = -2, voice_index: int = None) -> bytes:
    """
    SAPI 语音合成 → WAV（离线，含抗截断优化）
    
    修复"首音节丢失"的手段：
    1. 延长音频通道预热时间（0.6 → 1.0s）
    2. 先播一个短促低音量音节触发音频设备满缓冲
    3. 在 WAV 开头插入 100ms 静音帧（安全余量）
    """
    try:
        pythoncom.CoInitialize()
    except:
        pass

    if voice_index is None:
        voice_index = _get_best_sapi_index()

    tmp_path = None
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.Rate = max(-10, min(10, rate))
        voice.Volume = 100

        # 选择语音
        try:
            voices = voice.GetVoices()
            if 0 <= voice_index < voices.Count:
                voice.Voice = voices.Item(voice_index)
                print(f"[TTS] SAPI 使用语音: {voices.Item(voice_index).GetDescription()}")
            else:
                # 回退到最佳中文语音
                best = _get_best_sapi_index()
                if best < voices.Count:
                    voice.Voice = voices.Item(best)
                    print(f"[TTS] SAPI 回退到: {voices.Item(best).GetDescription()}")
        except Exception as e:
            print(f"[TTS] SAPI 选语音失败: {e}")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(tmp_path, 3, False)
        voice.AudioOutputStream = stream

        # ──── 关键：防截断的预热流程 ────
        # 1) 异步空播一次，触发设备初始化
        voice.Speak("", 1)          # SVSFlagsAsync = 1
        time.sleep(1.0)             # 充分等待音频管道就绪（从 0.6 → 1.0）

        # 2) 追加一次静默短播（低声量），确保音频缓冲区满载
        voice.Volume = 5            # 极低音量，人耳听不到但能填充缓冲区
        voice.Speak(".", 1)         # 异步播一个句号（几乎是静音）
        time.sleep(0.5)
        voice.Volume = 100          # 恢复音量

        # 3) 正式播报
        voice.Speak(text, 0)        # SVSFlagsAsync = 0，同步等待
        voice.WaitUntilDone(-1)
        stream.Close()

        # ──── 读取 WAV，在开头插入 100ms 静音帧 ────
        return _add_wav_silence_prefix(tmp_path, silence_ms=100)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _add_wav_silence_prefix(wav_path: str, silence_ms: int = 100) -> bytes:
    """
    在 WAV 数据开头插入静音帧，防止播放器截断开头
    使用 wave 模块解析头部（SAPI 输出的 fmt chunk 为 18 字节，非标准 44 字节头）
    """
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    # 计算静音帧字节数
    silence_frames = int(framerate * (silence_ms / 1000.0))
    silence_bytes = b'\x00' * (silence_frames * channels * sampwidth)
    # 用 wave 模块重建标准 WAV：静音 + 原 PCM
    buf = io.BytesIO()
    with wave.open(buf, "wb") as nf:
        nf.setnchannels(channels)
        nf.setsampwidth(sampwidth)
        nf.setframerate(framerate)
        nf.writeframes(silence_bytes + pcm)
    return buf.getvalue()


# ====== edge-tts（在线） ======

def _synthesize_edge(text: str, voice_name: str = "zh-CN-XiaoxiaoNeural", rate: int = -2) -> bytes:
    """edge-tts 神经网络语音 → MP3 → WAV"""
    import asyncio
    return asyncio.run(_synthesize_edge_async(text, voice_name, rate))


async def _synthesize_edge_async(text: str, voice_name: str = "zh-CN-XiaoxiaoNeural", rate: int = -2) -> bytes:
    import edge_tts
    rate_pct = max(-50, min(50, int(rate * 5)))
    rate_str = f"{rate_pct:+d}%"

    mp3_path = None
    wav_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = tmp.name
        wav_path = mp3_path + ".wav"

        communicate = edge_tts.Communicate(text, voice_name, rate=rate_str)
        await communicate.save(mp3_path)

        subprocess.run([
            r"C:\ffmpeg\bin\ffmpeg.exe", "-y",
            "-i", mp3_path,
            "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
            wav_path
        ], capture_output=True, timeout=15)

        with open(wav_path, "rb") as f:
            return f.read()
    finally:
        for p in [mp3_path, wav_path]:
            if p and os.path.exists(p):
                os.unlink(p)


EDGE_VOICES = [
    {"id": "zh-CN-XiaoxiaoNeural", "name": "女声 - 晓晓", "gender": "female"},
    {"id": "zh-CN-YunxiNeural", "name": "男声 - 云希", "gender": "male"},
    {"id": "zh-CN-YunjianNeural", "name": "男声 - 云健", "gender": "male"},
    {"id": "zh-CN-XiaoyiNeural", "name": "女声 - 晓伊", "gender": "female"},
    {"id": "zh-CN-YunyangNeural", "name": "男声 - 云扬", "gender": "male"},
    {"id": "zh-CN-XiaochenNeural", "name": "女声 - 晓辰", "gender": "female"},
]


# ====== 对外接口 ======

def list_available_voices() -> list:
    """获取可用 TTS 语音列表（离线 SAPI 优先，再 sherpa，最后 edge-tts）"""
    voices = []

    # 1. SAPI 系统语音（离线，已按质量排序，神经网络语音排在最前）
    sapi_voices = _list_sapi_voices()
    for v in sapi_voices:
        voices.append({
            "id": f"sapi-{v['sapi_index']}",
            "name": v["name"],
            "gender": v["gender"],
        })

    # 2. sherpa-onnx 离线神经网络音色（遍历多模型）
    for model_key, cfg in SHERPA_MODELS.items():
        if _get_sherpa_tts(model_key) is None:
            continue
        label = cfg.get("label", model_key)
        for v in _get_model_voices(model_key):
            # zh-ll 保持旧 id（sherpa-<sid>），其他模型用 sherpa-<key>-<sid>
            if model_key == "zh-ll":
                vid = f"sherpa-{v['sid']}"
            else:
                vid = f"sherpa-{model_key}-{v['sid']}"
            voices.append({
                "id": vid,
                "name": f"[神经网络(VITS) {label}] {v['name']}",
                "gender": v["gender"],
            })

    # 3. edge-tts 在线音色（仅 auto 模式）
    if TTS_MODE != "offline" and _USE_EDGE:
        for v in EDGE_VOICES:
            voices.append({
                "id": v["id"],
                "name": f"[在线] {v['name']}",
                "gender": v["gender"],
            })

    # 兜底
    if not voices:
        voices.append({"id": "sapi-0", "name": "系统默认", "gender": "male"})
    return voices


def synthesize_to_wav(text: str, rate: int = -2, voice_name: str = "sapi-0") -> bytes:
    """
    将文字合成为 WAV 音频字节流（离线优先）
    Args:
        text: 要合成的文本
        rate: 语速，范围 -10 到 10
        voice_name: 音色 id（sapi-* / sherpa-* / edge-tts 音色 id）
    """
    # SAPI 系统语音（离线，含神经网络音色）
    if voice_name.startswith("sapi-"):
        idx = int(voice_name.split("-")[1])
        return _synthesize_sapi(text, rate, idx)

    # sherpa-onnx 离线神经网络（多模型）
    if voice_name.startswith("sherpa-"):
        model_key, sid = _parse_sherpa_voice(voice_name)
        if model_key is not None:
            return _synthesize_sherpa(text, rate, sid, model_key)
        raise ValueError(f"无效的 sherpa 音色 id: {voice_name}")

    # edge-tts 音色：auto 模式尝试在线，失败走离线兜底
    if TTS_MODE != "offline" and _USE_EDGE:
        try:
            return _synthesize_edge(text, voice_name, rate)
        except Exception as e:
            print(f"[TTS] edge-tts 失败，降级到离线: {e}")

    # 离线兜底：SAPI → sherpa
    return _synthesize_sapi(text, rate, _get_best_sapi_index())


# ====== 播报（扬声器播放） ======

def _tts_worker():
    """后台 TTS 播报工作线程（使用最佳 SAPI 语音）"""
    global _tts_worker_running
    _tts_worker_running = True
    try:
        pythoncom.CoInitialize()
    except:
        pass
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.Rate = 0
    voice.Volume = 100
    # 使用最佳中文语音
    best_idx = _get_best_sapi_index()
    try:
        voices_obj = voice.GetVoices()
        if best_idx < voices_obj.Count:
            voice.Voice = voices_obj.Item(best_idx)
            voice_name = voices_obj.Item(best_idx).GetDescription()
        else:
            voice_name = "默认语音"
    except Exception:
        voice_name = "默认语音"
    print(f"[TTS] 工作线程启动, 语音: {voice_name}")

    while True:
        text = _tts_queue.get()
        if text is None:
            break
        try:
            print(f"[TTS] 播报: {text}")
            # 防截断预热（与 _synthesize_sapi 对齐）
            voice.Speak("", 1)
            time.sleep(0.8)
            voice.Volume = 5
            voice.Speak(".", 1)
            time.sleep(0.4)
            voice.Volume = 100
            voice.Speak(text, 0)
            voice.WaitUntilDone(-1)
        except Exception as e:
            print(f"[TTS] 播报失败: {e}")
        _tts_queue.task_done()


def speak(text: str):
    """播报文字（同步阻塞，使用最佳 SAPI 语音 + 防截断预热）"""
    global _tts_worker_running
    print(f"[TTS] 播报: {text}")
    # 停止后台工作线程
    if _tts_worker_running:
        _tts_queue.put(None)
        _tts_worker_running = False
        time.sleep(0.3)
    try:
        pythoncom.CoInitialize()
    except:
        pass
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voice.Rate = 0
        voice.Volume = 100
        best_idx = _get_best_sapi_index()
        try:
            voices_obj = voice.GetVoices()
            if best_idx < voices_obj.Count:
                voice.Voice = voices_obj.Item(best_idx)
        except:
            pass
        # 防截断预热
        voice.Speak("", 1)      # 异步空播，触发设备
        time.sleep(0.8)         # 等音频通道就绪
        voice.Volume = 5
        voice.Speak(".", 1)     # 填充缓冲区
        time.sleep(0.4)
        voice.Volume = 100
        voice.Speak(text, 0)    # 同步播报
        voice.WaitUntilDone(-1)
    except Exception as e:
        print(f"[TTS] 播报失败: {e}")


def speak_async(text: str):
    """播报文字（异步放入队列）"""
    global _tts_worker_running
    if not _tts_worker_running:
        worker = threading.Thread(target=_tts_worker, daemon=True)
        worker.start()
        time.sleep(0.5)
    _tts_queue.put(text)
    print(f"[TTS] 已加入播报队列: {text}")


def list_voices():
    """列出所有可用语音（调试用）"""
    try:
        pythoncom.CoInitialize()
    except:
        pass
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voices_obj = voice.GetVoices()
    print(f"可用语音 ({voices_obj.Count} 个):")
    for i in range(voices_obj.Count):
        v = voices_obj.Item(i)
        print(f"  [{i}] {v.GetDescription()}")


# 清除 SAPI 缓存（系统语音变化时调用）
def clear_sapi_cache():
    global _sapi_voice_cache
    _sapi_voice_cache = None


if __name__ == "__main__":
    print("测试 TTS 语音合成...")
    print("模式:", TTS_MODE)
    for k, cfg in SHERPA_MODELS.items():
        print(f"sherpa [{k}] 模型目录: {cfg['dir']}")
    print()
    vs = list_available_voices()
    for v in vs:
        print(f"  {v['id']} | {v['name']} | {v['gender']}")
    print()
    print("最佳 SAPI 语音索引:", _get_best_sapi_index())
    # 逐个测试各 sherpa 模型合成
    for k in SHERPA_MODELS:
        if _get_sherpa_tts(k) is None:
            continue
        try:
            if k == "zh-ll":
                vid = "sherpa-0"
            else:
                vid = f"sherpa-{k}-0"
            print(f"合成测试 {vid}:")
            data = synthesize_to_wav("你好，我是你的数字人智能助手", rate=0, voice_name=vid)
            print(f"  -> {len(data)} bytes")
        except Exception as e:
            print(f"  -> 失败: {e}")
    print("✅ TTS 测试完成")
