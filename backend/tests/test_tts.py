"""
TTS 测试脚本：验证文字转语音是否正常工作
"""
from tts_service import speak, list_voices


def main():
    print("=" * 50)
    print("🔊 TTS 语音合成测试")
    print("=" * 50)

    print("\n[1/2] 列出可用语音...")
    list_voices()

    print("\n[2/2] 开始播报...")
    test_texts = [
        "工单查询已完成",
        "你好，我是你的数字人智能助手",
        "当前CPU使用率百分之六十七，内存使用率百分之七十二",
    ]

    for text in test_texts:
        input(f"\n按回车播报: 「{text}」")
        speak(text)

    print("\n✅ TTS 测试完成！")


if __name__ == "__main__":
    main()
