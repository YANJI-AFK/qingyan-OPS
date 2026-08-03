"""
整合测试脚本：全链路串联验证
流程：录音 → ASR识别 → LLM理解 → 执行API → LLM润色回复 → TTS播报
"""
import time
import sys
import json

# 导入所有模块
from asr_service import recognize_from_file
from ollama_service import understand_intent, call_ollama_raw
from tts_service import speak
from mock_data import TICKETS, SERVERS_METRICS

import pyaudio
import wave
import threading

# ========== 录音、识别、LLM 都在各自模块中 ==========
# 这里只需要测试链路串联

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
RECORD_SECONDS = 5
OUTPUT_FILE = "test_int.wav"


def record_audio(filename: str, duration: int = 5) -> bool:
    """录音函数（带 321 倒计时）"""
    p = pyaudio.PyAudio()
    try:
        info = p.get_default_input_device_info()
        print(f"🎤 设备: {info['name']}")
    except:
        pass

    stream = p.open(
        format=p.get_format_from_width(SAMPLE_WIDTH),
        channels=CHANNELS, rate=SAMPLE_RATE,
        input=True, frames_per_buffer=1024,
    )

    # 倒计时，让用户准备好
    import time
    for s in [3, 2, 1]:
        print(f"\r   {s}...", end="", flush=True)
        time.sleep(1)
    print(f"\r🔴 开始说话！... ({duration}秒)  ")

    frames = []
    # 录音前先清空缓冲区
    for _ in range(5):
        stream.read(1024, exception_on_overflow=False)

    for i in range(int(SAMPLE_RATE / 1024 * duration)):
        data = stream.read(1024, exception_on_overflow=False)
        frames.append(data)
        progress = int((i + 1) / (SAMPLE_RATE / 1024 * duration) * 20)
        bar = "█" * progress + "░" * (20 - progress)
        print(f"\r   [{bar}] {int((i+1)/(SAMPLE_RATE/1024*duration)*100)}%", end="")
    print("\n🟢 录音结束！")

    stream.stop_stream(); stream.close(); p.terminate()

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(p.get_format_from_width(SAMPLE_WIDTH)))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))

    print(f"💾 已保存: {filename}")
    return True


def test_step(name: str):
    """打印测试步骤"""
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")


def main():
    print("╔════════════════════════════════════════╗")
    print("║   🚀 全链路整合测试                   ║")
    print("║   录音→ASR→LLM→API→LLM→TTS           ║")
    print("╚════════════════════════════════════════╝")

    # ========== 步骤 1：录音 ==========
    test_step("步骤 1/6：录音（请对着麦克风说话）")
    record_audio(OUTPUT_FILE, RECORD_SECONDS)
    print("💾 已保存录音")

    # ========== 步骤 2：ASR 识别 ==========
    test_step("步骤 2/6：语音识别（ASR）")
    text = recognize_from_file(OUTPUT_FILE)
    print(f"📝 识别结果: 「{text}」")
    if not text:
        print("❌ 识别失败，退出")
        return

    # ========== 步骤 3：LLM 理解意图 ==========
    test_step("步骤 3/6：LLM 理解意图")
    intent = understand_intent(text)
    print(f"🧠 意图解析: {json.dumps(intent, indent=2, ensure_ascii=False)}")

    intent_type = intent.get("intent", "error")
    if intent_type == "error":
        reply_text = f"抱歉，{intent.get('message', '未理解')}"
        print(f"❌ {reply_text}")
        speak(reply_text)
        return
    elif intent_type == "greeting":
        reply_text = "你好！欢迎使用数字人智能助手。"
        print(f"✅ 意图：问候")
    elif intent_type == "navigate":
        target = intent.get("target", "")
        print(f"✅ 意图：导航 → {target}")
        reply_text = f"正在为您跳转到{target}"
    elif intent_type in ("query", "action"):
        api_name = intent.get("api", "")
        print(f"✅ 意图：{intent_type}，API：{api_name}")

        # ========== 步骤 4：执行 Mock API ==========
        test_step("步骤 4/6：执行 API 获取数据")

        api_data = {}
        if api_name == "stat":
            total = len(TICKETS)
            status_count = {}
            for t in TICKETS:
                s = t["status"]; status_count[s] = status_count.get(s, 0) + 1
            api_data = {"total": total, "status_distribution": status_count}
            print(f"📊 API 返回: {json.dumps(api_data, ensure_ascii=False)}")
        elif api_name == "metrics":
            api_data = SERVERS_METRICS
            print(f"📊 API 返回: {json.dumps(api_data, ensure_ascii=False)}")
        else:
            api_data = {}

        # ========== 步骤 5：LLM 润色回复 ==========
        test_step("步骤 5/6：LLM 润色回复")
        if api_data:
            polish_prompt = (
                f"用户的问题是：「{text}」。以下是查到的数据：{json.dumps(api_data, ensure_ascii=False)}。"
                f"请把这些数据用自然语言总结成一句话中文回复，直接说出来，不要任何多余内容。"
            )
            try:
                polished = call_ollama_raw(polish_prompt, max_tokens=100)
                reply_text = polished.strip()
                print(f"✨ 润色后: 「{reply_text}」")
            except:
                reply_text = f"查询完成，数据已获取。"
                print(f"⚠️ LLM润色失败，使用默认回复")
        else:
            reply_text = "查询完成。"
    else:
        reply_text = "你好，我是数字人助手。"

    # ========== 步骤 6：TTS 播报 ==========
    test_step("步骤 6/6：TTS 语音播报")
    print(f"🔊 播报: 「{reply_text}」")
    speak(reply_text)

    # ========== 完成 ==========
    print(f"\n{'='*50}")
    print("  ✅ 全链路测试完成！")
    print(f"{'='*50}")

    if text:
        print(f"\n📊 离线能力验证：")
        print(f"   语音输入 → 「{text}」")
        print(f"   意图识别 → {intent_type} / {intent.get('api', '')}")
        print(f"   语音播报 → 「{reply_text}」")
        print(f"   ✅ 全程离线，无需网络！")


if __name__ == "__main__":
    main()
