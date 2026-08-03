"""
ASR 测试脚本：验证 FunASR 语音识别是否正常工作
"""
from asr_service import recognize_from_file, get_model


def main():
    print("=" * 50)
    print("🎤 ASR 语音识别测试")
    print("=" * 50)

    # 第一步：测试模型加载
    print("\n[1/2] 加载语音识别模型...")
    try:
        model = get_model()
        print("✅ 模型加载成功！")
    except Exception as e:
        print(f"❌ 加载失败: {e}")
        print("\n💡 请先安装依赖:")
        print("   pip install funasr modelscope soundfile")
        return

    # 第二步：提示用户准备音频文件
    print("\n[2/2] 准备测试音频")
    print("-" * 30)
    print("请准备一个 16kHz 采样率的 WAV 音频文件")
    print("或者使用以下 Python 代码生成测试音频：")
    print()
    print("  import soundfile as sf")
    print("  import numpy as np")
    print('  # 生成 3 秒的测试音频（说"你好"）')
    print("  sr = 16000")
    print("  duration = 3")
    print("  t = np.linspace(0, duration, int(sr * duration))")
    print('  audio = np.sin(2 * np.pi * 440 * t) * 0.3')
    print('  sf.write("test.wav", audio, sr)')
    print()
    print("然后将 test.wav 放到 backend 目录下，修改下方路径测试。")
    print()

    # 如果要测试已有的音频文件，取消注释下面这行
    # text = recognize_from_file("test.wav")
    # print(f"识别结果: {text}")


if __name__ == "__main__":
    main()
