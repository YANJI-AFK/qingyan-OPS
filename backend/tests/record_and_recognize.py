"""
录音 + 语音识别测试脚本
录制3秒麦克风声音 → 保存 test.wav → FunASR 识别 → 输出文字
"""
import pyaudio
import wave
import numpy as np
from asr_service import get_model, recognize_from_file

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
RECORD_SECONDS = 3
OUTPUT_FILE = "test.wav"


def record_audio(filename: str, duration: int = 3) -> bool:
    """从麦克风录制音频并保存为 WAV 文件"""
    p = pyaudio.PyAudio()

    try:
        device_info = p.get_default_input_device_info()
        print(f"🎤 录音设备: {device_info['name']}")
    except:
        print("🎤 使用默认录音设备")

    stream = p.open(
        format=p.get_format_from_width(SAMPLE_WIDTH),
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=1024,
    )

    print(f"\n🔴 开始录音（请对着麦克风说话）...")
    print(f"   ⏱  时长: {duration} 秒")

    frames = []
    total_chunks = int(SAMPLE_RATE / 1024 * duration)
    for i in range(total_chunks):
        data = stream.read(1024, exception_on_overflow=False)
        frames.append(data)
        progress = int((i + 1) / total_chunks * 20)
        bar = "█" * progress + "░" * (20 - progress)
        print(f"\r   [{bar}] {int((i+1)/total_chunks*100)}%", end="")

    print(f"\n🟢 录音结束！")

    stream.stop_stream()
    stream.close()
    p.terminate()

    with wave.open(filename, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(p.get_format_from_width(SAMPLE_WIDTH)))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))

    print(f"💾 已保存: {filename}")
    return True


def main():
    print("=" * 50)
    print("🎙️  录音 + 语音识别测试")
    print("=" * 50)

    print("\n[1/3] 加载语音识别模型...")
    try:
        model = get_model()
        print("✅ 模型加载成功！")
    except Exception as e:
        print(f"❌ 加载失败: {e}")
        return

    print("\n[2/3] 开始录音...")
    try:
        record_audio(OUTPUT_FILE, RECORD_SECONDS)
    except Exception as e:
        print(f"❌ 录音失败: {e}")
        print("   💡 请确保麦克风已连接且未被其他程序占用")
        return

    print(f"\n[3/3] 正在识别...")
    try:
        text = recognize_from_file(OUTPUT_FILE)
        print(f"\n📝 识别结果: 「{text}」")
        if text:
            print(f"   ✅ 成功识别 {len(text)} 个字符")
        else:
            print("   ⚠️  未识别到文字，请再试一次")
    except Exception as e:
        print(f"❌ 识别失败: {e}")


if __name__ == "__main__":
    main()
