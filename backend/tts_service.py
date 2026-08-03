"""
TTS 语音合成服务模块
优先使用 edge-tts（微软神经网络语音，自然流畅），SAPI 为离线降级方案
"""
import threading
import queue
import time
import os
import tempfile
import subprocess

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

_tts_queue = queue.Queue()
_tts_worker_running = False


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
            print(f"[TTS] 🔊 播报: {text}")
            voice.Speak("", 1)   # 预热音频通道
            time.sleep(0.4)
            voice.Speak(text, 0) # 同步播报
            voice.WaitUntilDone(-1)
        except Exception as e:
            print(f"[TTS] ❌ 播报失败: {e}")
        _tts_queue.task_done()


def speak(text: str):
    """播报文字（同步阻塞）"""
    global _tts_worker_running
    print(f"[TTS] 🔊 播报: {text}")
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
        # 预热：说一个极短的音让音频设备就绪
        voice.Speak("", 1)  # 异步空播，触发音频设备
        time.sleep(0.4)    # 等音频通道就绪
        # 正式播报（同步模式）
        voice.Speak(text, 0)
        voice.WaitUntilDone(-1)  # 等待播完
    except Exception as e:
        print(f"[TTS] ❌ 播报失败: {e}")


def speak_async(text: str):
    """播报文字（异步放入队列）"""
    global _tts_worker_running
    if not _tts_worker_running:
        worker = threading.Thread(target=_tts_worker, daemon=True)
        worker.start()
        time.sleep(0.5)
    _tts_queue.put(text)
    print(f"[TTS] 📥 已加入播报队列: {text}")


def list_voices():
    """列出所有可用语音"""
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


def synthesize_to_wav(text: str, rate: int = -2, voice_name: str = "zh-CN-XiaoxiaoNeural") -> bytes:
    """
    将文字合成为 WAV 音频字节流
    优先 edge-tts 神经网络语音 → SAPI 降级
    Args:
        text: 要合成的文本
        rate: 语速，范围 -10 到 10（SAPI），edge-tts 用 rate_str 映射
        voice_name: edge-tts 语音名称或 SAPI 语音描述关键词
    """
    if _USE_EDGE:
        try:
            return _synthesize_edge(text, voice_name, rate)
        except Exception as e:
            print(f"[TTS] edge-tts 失败，降级到 SAPI: {e}")

    return _synthesize_sapi(text, rate, voice_name)


def _synthesize_edge(text: str, voice_name: str = "zh-CN-XiaoxiaoNeural", rate: int = -2) -> bytes:
    """edge-tts 神经网络语音 → MP3 → WAV"""
    import asyncio
    return asyncio.run(_synthesize_edge_async(text, voice_name, rate))


async def _synthesize_edge_async(text: str, voice_name: str = "zh-CN-XiaoxiaoNeural", rate: int = -2) -> bytes:
    import edge_tts
    # 将 SAPI rate 映射为 edge-tts 语速百分比字符串
    # SAPI -10..10 → edge-tts "-50%".."+50%"
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


def _synthesize_sapi(text: str, rate: int = -2, voice_keyword: str = "zh") -> bytes:
    """SAPI 语音合成 → WAV（离线降级方案）"""
    try:
        pythoncom.CoInitialize()
    except:
        pass
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.Rate = max(-10, min(10, rate))
    voice.Volume = 100
    # 按关键词匹配语音
    try:
        voices = voice.GetVoices()
        best = None
        for i in range(voices.Count):
            v = voices.Item(i)
            desc = v.GetDescription().lower()
            if voice_keyword.lower() in desc:
                best = v
                break
        if best:
            voice.Voice = best
        else:
            voice.Voice = voices.Item(0)
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


def list_available_voices() -> list:
    """列出所有可用的 TTS 语音名称"""
    # 尝试导入 edge-tts（如果首次 import 失败可能是因为未安装，强制再试一次）
    global _USE_EDGE
    if not _USE_EDGE:
        try:
            import edge_tts as _  # noqa: F811
            _USE_EDGE = True
        except ImportError:
            pass

    if _USE_EDGE:
        return [
            {"id": "zh-CN-XiaoxiaoNeural", "name": "女声 - 晓晓", "gender": "female"},
            {"id": "zh-CN-YunxiNeural", "name": "男声 - 云希", "gender": "male"},
            {"id": "zh-CN-YunjianNeural", "name": "男声 - 云健", "gender": "male"},
            {"id": "zh-CN-XiaoyiNeural", "name": "女声 - 晓伊", "gender": "female"},
            {"id": "zh-CN-YunyangNeural", "name": "男声 - 云扬", "gender": "male"},
            {"id": "zh-CN-XiaochenNeural", "name": "女声 - 晓辰", "gender": "female"},
        ]

    # SAPI 降级：提供虚拟音色名，实际按关键词匹配系统语音
    return [
        {"id": "zh", "name": "中文女声", "gender": "female"},
        {"id": "microsoft huihui", "name": "慧慧 (女声)", "gender": "female"},
        {"id": "microsoft kangkang", "name": "康康 (男声)", "gender": "male"},
        {"id": "microsoft yaoyao", "name": "瑶瑶 (女声)", "gender": "female"},
        {"id": "haruka", "name": "日语女声", "gender": "female"},
        {"id": "default", "name": "系统默认", "gender": "male"},
    ]


if __name__ == "__main__":
    print("测试 TTS 语音合成...")
    list_voices()
    print()
    time.sleep(0.5)
    speak("你好，我是你的数字人智能助手")
    print("✅ TTS 测试完成")
