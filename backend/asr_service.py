"""
ASR 语音识别服务模块
使用 FunASR + paraformer-zh 模型进行中文语音识别
"""
import os
import re
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

# ====== 中文数字 → 阿拉伯数字转换（修复 ASR 数字变汉字问题）======
_CN_NUM_MAP = {
    '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
    '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
    '幺': '1',  # 工单/电话号数字中"幺"表示 1
}


def _cn_numerals_to_digits(text: str) -> str:
    """
    将连续的中文数字字符序列转换为阿拉伯数字。
    仅转换长度 >= 2 的连续序列，避免影响正常中文单字（如「一个人」）。
    
    例如:
        "二零二六"              → "2026"
        "零八三幺"              → "0831"（含「幺」→1）
        "零零零五"              → "0005"
        "TKT二零二六零八三幺零零零五" → "TKT202608310005"
        "一个人"                → "一个人"（单字不转换）
    """
    if not text:
        return text

    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in _CN_NUM_MAP:
            start = i
            while i < len(text) and text[i] in _CN_NUM_MAP:
                i += 1
            span = text[start:i]
            if len(span) >= 2:
                result.append(''.join(_CN_NUM_MAP[c] for c in span))
            else:
                result.append(span)
        else:
            result.append(ch)
            i += 1

    return ''.join(result)


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
    text = ""
    if isinstance(result, list) and len(result) > 0:
        text = result[0].get("text", "")
    elif isinstance(result, dict):
        text = result.get("text", "")
    
    # 中文数字 → 阿拉伯数字转换（修复"二零二六"→"2026"等 ASR 数字变汉字问题）
    return _cn_numerals_to_digits(text)


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
    
    text = ""
    if isinstance(result, list) and len(result) > 0:
        text = result[0].get("text", "")
    elif isinstance(result, dict):
        text = result.get("text", "")
    
    # 中文数字 → 阿拉伯数字转换
    return _cn_numerals_to_digits(text)


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
