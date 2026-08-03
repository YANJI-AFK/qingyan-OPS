"""
ASR 语音识别服务模块
使用 FunASR + paraformer-zh 模型进行中文语音识别
"""
import os
import time

# ⚠️ 必须在 import funasr 之前设置
os.environ["MODELSCOPE_CACHE"] = os.path.expanduser("~/.cache/modelscope")
os.environ["MODELSCOPE_OFFLINE"] = "1"

import base64
import numpy as np

# FunASR 相关导入（延迟加载，带重试）
_AutoModel = None
_import_attempted = False


def _try_import_funasr():
    """尝试导入 FunASR AutoModel（最多重试 5 次，应对 Windows Defender 慢扫描）"""
    global _AutoModel, _import_attempted
    if _AutoModel is not None:
        return _AutoModel
    for attempt in range(1, 6):
        try:
            from funasr import AutoModel as AM
            _AutoModel = AM
            _import_attempted = True
            return _AutoModel
        except ImportError:
            if attempt == 1:
                print(f"[ASR] FunASR 首次导入等待中（Windows Defender 扫描中，请稍候）...")
            time.sleep(3)  # 等 3 秒后重试
    _import_attempted = True
    return None


# 本地模型缓存路径（从 modelscope 缓存直接加载，无需联网）
_CACHE = os.path.expanduser("~/.cache/modelscope/models")

# 三个模型的本地目录
_ASR_DIR = os.path.join(_CACHE, "iic--speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch", "snapshots", "master")
_VAD_DIR = os.path.join(_CACHE, "iic--speech_fsmn_vad_zh-cn-16k-common-pytorch", "snapshots", "master")
_PUNC_DIR = os.path.join(_CACHE, "iic--punc_ct-transformer_zh-cn-common-vocab272727-pytorch", "snapshots", "master")

# 全局模型实例（只加载一次）
_asr_model = None


def get_model():
    """获取 ASR 模型（单例），从本地缓存直接加载，完全离线"""
    global _asr_model
    if _asr_model is None:
        AutoModel = _try_import_funasr()
        if AutoModel is None:
            raise ImportError("请先安装 FunASR: pip install funasr；如已安装，请检查网络/杀毒软件是否卡顿")
        print("[ASR] 正在从本地加载语音识别模型...")

        # 检查本地缓存是否存在
        if not os.path.isdir(_ASR_DIR):
            print(f"[ASR] ⚠️ 模型缓存不存在: {_ASR_DIR}")
            print("[ASR] 首次使用需联网下载模型，连接网络后重试即可")
            raise FileNotFoundError(f"模型未缓存，请先联网下载: {_ASR_DIR}")

        _asr_model = AutoModel(
            model=_ASR_DIR,          # 直接传本地路径，跳过 hub 检查
            vad_model=_VAD_DIR,
            punc_model=_PUNC_DIR,
            disable_sv=True,
            disable_update=True,
            device="cpu",
            # ===== VAD 参数调优（解决吞开头字问题）=====
            vad_kwargs={
                "max_end_silence_time": 1200,     # 句尾最大静音时长(ms)，加大避免中途截断
                "speech_start_silence_time": 120,  # 句首允许的静音(ms)，收窄以捕获开头
                "speech_noise_threshold": 0.5,     # 噪声阈值（越小越敏感，0.4-0.6）
            },
        )
        print("[ASR] 模型加载完成（离线模式）")
    return _asr_model


def recognize_from_bytes(audio_bytes: bytes, sample_rate: int = 16000) -> str:
    """
    从音频字节数据识别文字
    
    Args:
        audio_bytes: 原始音频 PCM 数据
        sample_rate: 采样率（默认 16000）
    
    Returns:
        识别出的文字
    """
    model = get_model()
    
    # 将字节数据转为 numpy 数组
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    
    # 执行识别
    result = model.generate(input=audio_np, fs=sample_rate)
    
    # 解析结果
    if isinstance(result, list) and len(result) > 0:
        return result[0].get("text", "")
    elif isinstance(result, dict):
        return result.get("text", "")
    return ""


def recognize_from_file(file_path: str) -> str:
    """
    从音频文件识别文字
    
    Args:
        file_path: 音频文件路径（支持 wav、mp3 等）
    
    Returns:
        识别出的文字
    """
    model = get_model()
    result = model.generate(input=file_path)
    
    if isinstance(result, list) and len(result) > 0:
        return result[0].get("text", "")
    elif isinstance(result, dict):
        return result.get("text", "")
    return ""


def recognize_from_base64(base64_str: str, sample_rate: int = 16000) -> str:
    """
    从 base64 编码的音频数据识别文字
    
    Args:
        base64_str: base64 编码的音频数据
        sample_rate: 采样率
    
    Returns:
        识别出的文字
    """
    audio_bytes = base64.b64decode(base64_str)
    return recognize_from_bytes(audio_bytes, sample_rate)


if __name__ == "__main__":
    # 测试：加载模型
    print("测试 ASR 模型加载...")
    try:
        model = get_model()
        print("✅ ASR 模型加载成功！")
        print("  模型路径:", _ASR_DIR)
    except Exception as e:
        print(f"❌ 加载失败: {e}")
