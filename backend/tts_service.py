"""
TTS 语音合成服务模块

支持三种引擎（按音色 id 前缀分发）：
1. sherpa-onnx VITS —— 离线神经网络 TTS（音质最佳，需下载模型）
2. Microsoft SAPI —— Windows 系统自带语音（离线，动态枚举）
3. edge-tts —— 微软神经网络语音（需联网）

音色 id 约定：
- sherpa-0 ~ sherpa-4 : sherpa-onnx VITS 音色（离线）
- sapi-<index>        : SAPI 系统语音（离线，按枚举序号）
- zh-CN-XiaoxiaoNeural 等 : edge-tts 音色（在线）

环境变量：
- TTS_MODE: offline（默认，强制离线：只暴露 sherpa + SAPI）
            auto（同时暴露 edge-tts，优先在线音色）
- SHERPA_TTS_DIR: sherpa-onnx 模型目录
                  （默认 C:\\sherpa-tts\\sherpa-onnx-vits-zh-ll）
"""
import threading
import queue
import time
import os
import io
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
SHERPA_TTS_DIR = os.getenv(
    "SHERPA_TTS_DIR", r"C:\sherpa-tts\sherpa-onnx-vits-zh-ll"
)

# sherpa-onnx 音色名称（G_multisperaker_latest.json 中 speakers 映射）
SHERPA_VOICES = [
    {"sid": 0, "name": "苏樱雪", "gender": "female"},
    {"sid": 1, "name": "古念", "gender": "female"},
    {"sid": 2, "name": "傅诗雨", "gender": "female"},
    {"sid": 3, "name": "冰娇", "gender": "female"},
    {"sid": 4, "name": "霸总", "gender": "male"},
]

_tts_queue = queue.Queue()
_tts_worker_running = False

# ====== sherpa-onnx 懒加载 ======
_sherpa_tts = None
_sherpa_error = None


def _get_sherpa_tts():
    """懒加载 sherpa-onnx TTS 实例（模型不存在时返回 None）"""
    global _sherpa_tts, _sherpa_error
    if _sherpa_tts is not None:
        return _sherpa_tts
    if _sherpa_error is not None:
        return None
    try:
        import sherpa_onnx
        model_onnx = os.path.join(SHERPA_TTS_DIR, "model.onnx")
        if not os.path.exists(model_onnx):
            _sherpa_error = f"模型不存在: {SHERPA_TTS_DIR}"
            print(f"[TTS] sherpa-onnx {_sherpa_error}")
            return None
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=model_onnx,
                    tokens=os.path.join(SHERPA_TTS_DIR, "tokens.txt"),
                    lexicon=os.path.join(SHERPA_TTS_DIR, "lexicon.txt"),
                    dict_dir=os.path.join(SHERPA_TTS_DIR, "dict"),
                    data_dir="",
                ),
                num_threads=2,
                provider="cpu",
                debug=False,
            ),
            rule_fsts=",".join(
                os.path.join(SHERPA_TTS_DIR, f)
                for f in ["date.fst", "number.fst", "phone.fst"]
            ),
            max_num_sentences=1,
            rule_fars="",
        )
        _sherpa_tts = sherpa_onnx.OfflineTts(config)
        print(f"[TTS] sherpa-onnx 加载成功: {SHERPA_TTS_DIR}")
        return _sherpa_tts
    except Exception as e:
        _sherpa_error = str(e)
        print(f"[TTS] sherpa-onnx 初始化失败: {e}")
        return None


def _synthesize_sherpa(text: str, rate: int = 0, sid: int = 0) -> bytes:
    """sherpa-onnx VITS 离线神经网络合成 → 16bit PCM WAV bytes"""
    tts = _get_sherpa_tts()
    if tts is None:
        raise RuntimeError("sherpa-onnx 模型未加载")
    import numpy as np

    # 前端 rate -10..10 → speed 0.5..2.0
    speed = max(0.5, min(2.0, 1.0 + rate * 0.05))
    audio = tts.generate(text, sid=sid, speed=speed)
    if audio is None or len(audio.samples) == 0:
        raise RuntimeError("sherpa-onnx 合成结果为空")
    pcm = (np.asarray(audio.samples) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(audio.sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _init_voice(voice_obj):
    """初始化中文语音"""
    try:
        voices = voice_obj.GetVoices()
        for i in range(voices.Count):
            v = voices.Item(i)
            name = v.GetDescription().lower()
            if any(kw in name for kw in ["chinese", "zh", "hui", "xiao", "yaoyao"]):
                voice_obj.Voice = v
                return v.GetDescription()
        voice_obj.Voice = voices.Item(0)
        return voices.Item(0).GetDescription()
    except:
        return "默认语音"


def _list_sapi_voices() -> list:
    """动态枚举系统 SAPI 语音"""
    result = []
    if not _use_sapi:
        return result
    try:
        pythoncom.CoInitialize()
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voices = voice.GetVoices()
        for i in range(voices.Count):
            v = voices.Item(i)
            desc = v.GetDescription()
            # 截短名称，避免下拉框被长文本撑破：取 " - " 前的短名
            short = desc.split(" - ")[0].strip()
            try:
                lang = v.GetAttribute("Language") or ""
            except Exception:
                lang = ""
            is_zh = ("中文" in desc) or ("Chinese" in desc) or (str(lang).startswith("804"))
            low = desc.lower()
            gender = "female" if any(k in low for k in ["female", "女", "hui", "xiao", "yaoyao"]) else "male"
            tag = "中文" if is_zh else "多语言"
            result.append({
                "id": f"sapi-{i}",
                "name": f"[系统语音·{tag}] {short}",
                "gender": gender,
            })
    except Exception as e:
        print(f"[TTS] 枚举 SAPI 语音失败: {e}")
    return result


def _synthesize_sapi(text: str, rate: int = -2, voice_index: int = 0) -> bytes:
    """SAPI 语音合成 → WAV（离线）"""
    try:
        pythoncom.CoInitialize()
    except:
        pass
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.Rate = max(-10, min(10, rate))
    voice.Volume = 100
    # 按枚举序号选择语音，回退到中文关键词匹配
    try:
        voices = voice.GetVoices()
        if 0 <= voice_index < voices.Count:
            voice.Voice = voices.Item(voice_index)
        else:
            _init_voice(voice)
    except:
        pass
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(tmp_path, 3, False)
        voice.AudioOutputStream = stream
        voice.Speak("", 1)          # 异步空播：触发音频设备初始化
        time.sleep(0.6)             # 充分等待音频通道就绪（吞字往往是因为这步太短）
        voice.Speak(text, 0)        # 同步播报
        voice.WaitUntilDone(-1)
        stream.Close()
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ====== edge-tts（在线） ======

def _synthesize_edge(text: str, voice_name: str = "zh-CN-XiaoxiaoNeural", rate: int = -2) -> bytes:
    """edge-tts 神经网络语音 → MP3 → WAV"""
    import asyncio
    return asyncio.run(_synthesize_edge_async(text, voice_name, rate))


async def _synthesize_edge_async(text: str, voice_name: str = "zh-CN-XiaoxiaoNeural", rate: int = -2) -> bytes:
    import edge_tts
    # 将 SAPI rate 映射为 edge-tts 语速百分比字符串
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
    """获取可用 TTS 语音列表（离线优先）"""
    voices = []

    # 1. sherpa-onnx 离线神经网络音色
    if _get_sherpa_tts() is not None:
        for v in SHERPA_VOICES:
            voices.append({
                "id": f"sherpa-{v['sid']}",
                "name": f"[神经网络] {v['name']}",
                "gender": v["gender"],
            })

    # 2. SAPI 系统语音（离线）
    voices.extend(_list_sapi_voices())

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


def synthesize_to_wav(text: str, rate: int = -2, voice_name: str = "sherpa-0") -> bytes:
    """
    将文字合成为 WAV 音频字节流（离线优先）
    Args:
        text: 要合成的文本
        rate: 语速，范围 -10 到 10
        voice_name: 音色 id（sherpa-* / sapi-* / edge-tts 音色 id）
    """
    # sherpa-onnx 离线神经网络
    if voice_name.startswith("sherpa-"):
        sid = int(voice_name.split("-")[1])
        return _synthesize_sherpa(text, rate, sid)

    # SAPI 系统语音
    if voice_name.startswith("sapi-"):
        idx = int(voice_name.split("-")[1])
        return _synthesize_sapi(text, rate, idx)

    # edge-tts 音色：auto 模式尝试在线，失败走离线兜底
    if TTS_MODE != "offline" and _USE_EDGE:
        try:
            return _synthesize_edge(text, voice_name, rate)
        except Exception as e:
            print(f"[TTS] edge-tts 失败，降级到离线: {e}")

    # 离线兜底：sherpa → SAPI
    if _get_sherpa_tts() is not None:
        return _synthesize_sherpa(text, rate, 0)
    return _synthesize_sapi(text, rate, 0)


# ====== 播报（扬声器播放） ======

def _tts_worker():
    """后台工作线程"""
    global _tts_worker_running
    _tts_worker_running = True
    try:
        pythoncom.CoInitialize()
    except:
        pass
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.Rate = 0
    voice.Volume = 100
    voice_name = _init_voice(voice)
    print(f"[TTS] 工作线程启动, 语音: {voice_name}")
    while True:
        text = _tts_queue.get()
        if text is None:
            break
        try:
            print(f"[TTS] 播报: {text}")
            voice.Speak("", 1)   # 预热音频通道
            time.sleep(0.4)
            voice.Speak(text, 0) # 同步播报
            voice.WaitUntilDone(-1)
        except Exception as e:
            print(f"[TTS] 播报失败: {e}")
        _tts_queue.task_done()


def speak(text: str):
    """播报文字（同步阻塞）"""
    global _tts_worker_running
    print(f"[TTS] 播报: {text}")
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
        _init_voice(voice)
        voice.Speak("", 1)  # 异步空播，触发音频设备
        time.sleep(0.4)    # 等音频通道就绪
        voice.Speak(text, 0)
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
    voices = voice.GetVoices()
    print(f"可用语音 ({voices.Count} 个):")
    for i in range(voices.Count):
        v = voices.Item(i)
        print(f"  [{i}] {v.GetDescription()}")


if __name__ == "__main__":
    print("测试 TTS 语音合成...")
    print("模式:", TTS_MODE)
    print("sherpa 模型目录:", SHERPA_TTS_DIR)
    print()
    vs = list_available_voices()
    for v in vs:
        print(f"  {v['id']} | {v['name']} | {v['gender']}")
    print()
    print("合成测试 sherpa-0:")
    data = synthesize_to_wav("你好，我是你的数字人智能助手", rate=0, voice_name="sherpa-0")
    print(f"  -> {len(data)} bytes")
    print("✅ TTS 测试完成")
