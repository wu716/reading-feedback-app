# -*- coding: utf-8 -*-
"""
语音识别模块 - 使用 Vosk 进行离线语音识别
"""
import os
import json
import logging
from typing import Optional
import wave
import io
import subprocess
import tempfile

try:
    import vosk
except ImportError:
    vosk = None

logger = logging.getLogger(__name__)

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
    logger.info("pydub 模块加载成功")
except ImportError as e:
    PYDUB_AVAILABLE = False
    logger.warning(f"pydub 模块不可用: {e}")

# Vosk 模型配置
MODEL_NAME = "vosk-model-small-cn-0.22"
MODEL_PATH = os.path.join("models", MODEL_NAME)

def is_speech_recognition_available() -> bool:
    """
    检查语音识别服务是否可用
    
    Returns:
        bool: 语音识别服务是否可用
    """
    if vosk is None:
        logger.warning("Vosk 库未安装")
        return False
    
    if not os.path.exists(MODEL_PATH):
        logger.warning(f"Vosk 模型文件不存在: {MODEL_PATH}")
        logger.info("请下载中文模型: https://alphacephei.com/vosk/models")
        return False
    
    try:
        # 尝试加载模型
        model = vosk.Model(MODEL_PATH)
        logger.info("Vosk 模型加载成功")
        return True
    except Exception as e:
        logger.error(f"Vosk 模型加载失败: {e}")
        return False

def transcribe_audio_file(audio_path: str) -> Optional[str]:
    """
    转写音频文件
    
    Args:
        audio_path: 音频文件路径
        
    Returns:
        str: 转写结果，如果失败返回 None
    """
    if not is_speech_recognition_available():
        logger.warning("语音识别服务不可用")
        return "语音识别服务不可用，请检查 Vosk 模型"
    
    if not os.path.exists(audio_path):
        logger.error(f"音频文件不存在: {audio_path}")
        return "音频文件不存在"
    
    try:
        # 检查文件格式并尝试修复
        if not is_valid_wav_file(audio_path):
            logger.info(f"音频文件不是标准WAV格式，尝试格式转换: {audio_path}")
            
            # 首先尝试使用FFmpeg转换
            converted_path = convert_audio_to_wav(audio_path)
            
            # 如果FFmpeg失败，尝试使用pydub
            if not converted_path and PYDUB_AVAILABLE:
                logger.info("FFmpeg转换失败，尝试使用pydub")
                converted_path = convert_audio_with_pydub(audio_path)
            
            if converted_path:
                audio_path = converted_path
                logger.info(f"音频格式转换成功: {audio_path}")
            else:
                logger.warning("音频格式转换失败，尝试直接处理")
        
        # 优先使用 pydub 进行音频格式转换
        if PYDUB_AVAILABLE:
            logger.info(f"使用 pydub 处理音频文件: {audio_path}")
            result = transcribe_with_pydub(audio_path)
            if result and not result.startswith("语音识别失败"):
                return result
            else:
                logger.warning("pydub 处理失败，回退到 wave 模块")
                return transcribe_with_wave(audio_path)
        else:
            logger.warning("pydub 不可用，尝试直接使用 wave 模块")
            return transcribe_with_wave(audio_path)
            
    except Exception as e:
        logger.error(f"语音识别失败: {e}")
        return f"语音识别失败: {str(e)}"


def transcribe_with_pydub(audio_path: str) -> Optional[str]:
    """
    使用 pydub 进行音频格式转换和识别
    """
    try:
        # 使用 pydub 加载音频文件，它能自动识别多种格式
        audio = AudioSegment.from_file(audio_path)
        
        logger.info(f"原始音频信息: 采样率={audio.frame_rate}, 声道={audio.channels}, 时长={len(audio)}ms")
        
        # 将音频转换为 Vosk 所需的格式：16kHz, 16-bit, 单声道 WAV
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        audio = audio.set_sample_width(2)  # 16-bit
        
        logger.info(f"转换后音频信息: 采样率={audio.frame_rate}, 声道={audio.channels}")
        
        # 将转换后的音频导出到内存中的 WAV 缓冲区
        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_buffer.seek(0)  # 将缓冲区指针重置到开头
        
        # 加载 Vosk 模型
        model = vosk.Model(MODEL_PATH)
        
        # 创建识别器
        rec = vosk.KaldiRecognizer(model, 16000)
        
        full_transcript = ""
        chunk_size = 4000
        
        while True:
            data = wav_buffer.read(chunk_size)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                if text:
                    full_transcript += text + " "
                    logger.info(f"识别到文本片段: {text}")
            else:
                # 中间结果，可以用于实时显示
                partial_result = json.loads(rec.PartialResult())
                partial_text = partial_result.get("partial", "")
                if partial_text:
                    logger.debug(f"部分识别结果: {partial_text}")
        
        # 获取最终结果
        final_result = json.loads(rec.FinalResult())
        final_text = final_result.get("text", "")
        if final_text:
            full_transcript += final_text
            logger.info(f"最终识别结果: {final_text}")
        
        transcript = full_transcript.strip()
        
        if transcript:
            logger.info(f"语音识别成功: {transcript}")
            return transcript
        else:
            logger.warning("语音识别结果为空")
            return "语音识别结果为空，请检查录音质量"
            
    except Exception as e:
        logger.error(f"pydub 语音识别失败: {e}")
        logger.error("请确保已安装 ffmpeg/libav-tools 且在系统 PATH 中")
        return f"语音识别失败: {str(e)}"


def transcribe_with_wave(audio_path: str) -> Optional[str]:
    """
    使用 wave 模块进行识别（备用方法）
    """
    try:
        # 加载模型
        model = vosk.Model(MODEL_PATH)
        
        # 创建识别器
        rec = vosk.KaldiRecognizer(model, 16000)
        
        # 读取音频文件
        wf = wave.open(audio_path, 'rb')
        
        # 检查音频格式
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        
        logger.info(f"音频文件信息: 声道={channels}, 位深={sample_width}, 采样率={frame_rate}")
        
        # 更宽松的格式检查
        if channels != 1:
            logger.warning(f"音频不是单声道 (当前: {channels} 声道)，尝试继续处理")
        if sample_width != 2:
            logger.warning(f"音频不是16位 (当前: {sample_width*8} 位)，尝试继续处理")
        if frame_rate != 16000:
            logger.warning(f"音频不是16kHz (当前: {frame_rate} Hz)，尝试继续处理")
        
        full_transcript = ""
        chunk_size = 4000
        
        while True:
            data = wf.readframes(chunk_size)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                if text:
                    full_transcript += text + " "
                    logger.info(f"识别到文本片段: {text}")
            else:
                # 中间结果，可以用于实时显示
                partial_result = json.loads(rec.PartialResult())
                partial_text = partial_result.get("partial", "")
                if partial_text:
                    logger.debug(f"部分识别结果: {partial_text}")
        
        # 获取最终结果
        final_result = json.loads(rec.FinalResult())
        final_text = final_result.get("text", "")
        if final_text:
            full_transcript += final_text
            logger.info(f"最终识别结果: {final_text}")
        
        wf.close()
        
        transcript = full_transcript.strip()
        
        if transcript:
            logger.info(f"语音识别成功: {transcript}")
            return transcript
        else:
            logger.warning("语音识别结果为空")
            return "语音识别结果为空，请检查录音质量"
            
    except Exception as e:
        logger.error(f"wave 语音识别失败: {e}")
        return f"语音识别失败: {str(e)}"


def is_valid_wav_file(file_path: str) -> bool:
    """
    检查文件是否是有效的WAV格式
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否是有效的WAV文件
    """
    try:
        with open(file_path, 'rb') as f:
            # 检查RIFF头
            header = f.read(12)
            if len(header) < 12:
                return False
            
            # 检查RIFF标识
            if header[:4] != b'RIFF':
                logger.warning(f"文件缺少RIFF头: {file_path}")
                return False
            
            # 检查WAVE标识
            if header[8:12] != b'WAVE':
                logger.warning(f"文件不是WAVE格式: {file_path}")
                return False
            
            # 尝试用wave模块打开
            with wave.open(file_path, 'rb') as wf:
                wf.getparams()  # 尝试读取参数
                return True
                
    except Exception as e:
        logger.warning(f"WAV文件验证失败: {e}")
        return False


def convert_audio_to_wav(input_path: str) -> Optional[str]:
    """
    使用FFmpeg将音频文件转换为WAV格式
    
    Args:
        input_path: 输入音频文件路径
        
    Returns:
        str: 转换后的WAV文件路径，失败返回None
    """
    try:
        # 创建临时输出文件
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "converted.wav")
        
        # 使用FFmpeg进行转换
        cmd = [
            'ffmpeg', '-i', input_path,
            '-acodec', 'pcm_s16le',  # 16位PCM编码
            '-ar', '16000',          # 16kHz采样率
            '-ac', '1',              # 单声道
            '-y',                    # 覆盖输出文件
            output_path
        ]
        
        logger.info(f"执行音频转换命令: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30  # 30秒超时
        )
        
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(f"音频转换成功: {input_path} -> {output_path}")
            return output_path
        else:
            logger.error(f"FFmpeg转换失败: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        logger.error("音频转换超时")
        return None
    except FileNotFoundError:
        logger.error("FFmpeg未找到，请确保已安装FFmpeg")
        return None
    except Exception as e:
        logger.error(f"音频转换异常: {e}")
        return None


def convert_audio_with_pydub(input_path: str) -> Optional[str]:
    """
    使用pydub将音频文件转换为WAV格式（备用方法）
    
    Args:
        input_path: 输入音频文件路径
        
    Returns:
        str: 转换后的WAV文件路径，失败返回None
    """
    if not PYDUB_AVAILABLE:
        logger.warning("pydub不可用，无法进行格式转换")
        return None
        
    try:
        # 创建临时输出文件
        temp_dir = tempfile.mkdtemp()
        output_path = os.path.join(temp_dir, "converted.wav")
        
        # 使用pydub加载和转换
        audio = AudioSegment.from_file(input_path)
        
        # 转换为Vosk所需的格式
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        audio = audio.set_sample_width(2)  # 16-bit
        
        # 导出为WAV
        audio.export(output_path, format="wav")
        
        if os.path.exists(output_path):
            logger.info(f"pydub音频转换成功: {input_path} -> {output_path}")
            return output_path
        else:
            logger.error("pydub音频转换失败：输出文件不存在")
            return None
            
    except Exception as e:
        logger.error(f"pydub音频转换异常: {e}")
        return None