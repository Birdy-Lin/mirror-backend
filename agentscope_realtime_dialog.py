"""
基于 AgentScope 框架的实时对话示例
实现 ASR (语音识别) -> LLM (大语言模型) -> TTS (文本转语音) 的完整流程
"""

import asyncio
import threading
import queue
import os
import tempfile
import json
import requests
from typing import Optional

# AgentScope 导入（可选，仅在需要时使用）
try:
    import agentscope
    # 尝试导入 AgentScope 的模型和代理（如果可用）
    try:
        from agentscope.models import (
            DashScopeChatModel,
            DashScopeRealtimeTTSModel,
            OpenAIChatModel,
        )
        from agentscope.agents import ReActAgent, UserAgent
        from agentscope.formatters import DashScopeChatFormatter
        AGENTSCOPE_AVAILABLE = True
    except ImportError:
        # 如果从 models 导入失败，尝试从顶层导入
        try:
            from agentscope import (
                DashScopeChatModel,
                DashScopeRealtimeTTSModel,
                OpenAIChatModel,
                ReActAgent,
                UserAgent,
                DashScopeChatFormatter,
            )
            AGENTSCOPE_AVAILABLE = True
        except ImportError:
            AGENTSCOPE_AVAILABLE = False
            # 定义占位类，避免后续代码报错
            DashScopeChatModel = None
            DashScopeRealtimeTTSModel = None
            OpenAIChatModel = None
            ReActAgent = None
            UserAgent = None
            DashScopeChatFormatter = None
except ImportError:
    AGENTSCOPE_AVAILABLE = False
    # 定义占位类
    DashScopeChatModel = None
    DashScopeRealtimeTTSModel = None
    OpenAIChatModel = None
    ReActAgent = None
    UserAgent = None
    DashScopeChatFormatter = None

import pyaudio
import wave


# ==================== 配置信息 ====================
# 从环境变量读取 API Key（推荐方式）
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "your_dashscope_api_key")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your_openai_api_key")

# API Key 配置（所有服务使用相同的 API Key，硬编码）
API_KEY = "u57Q2uOqbIHG3FAw_dZ-8kQhcGnElTd_urQk7HYl35w6STjLjsrxhIyXETc3_neq1Gmn5ooD54P0gg_5-WkWRg"

# ASR 配置（Paraformer Tongyi 语音识别）
ASR_API_KEY = API_KEY
ASR_PROJECT_ID = "5dsCrIuS7UpWEFcseCMSP4"
ASR_EASYLLM_ID = "TVQVM0yL0MJi2bVdrnSJN"
ASR_API_URL = f"https://www.sophnet.com/api/open-apis/projects/{ASR_PROJECT_ID}/easyllms/speechtotext/transcriptions"

# TTS 配置（文本转语音）
TTS_API_KEY = API_KEY  # 使用相同的 API Key
TTS_PROJECT_ID = "5dsCrIuS7UpWEFcseCMSP4"  # 使用相同的 Project ID
TTS_EASYLLM_ID = "TVQVM0yL0MJi2bVdrnSJN"  # 使用相同的 EasyLLM ID
# TTS API URL - 根据实际 API 文档调整
# 如果返回 404，可能需要使用不同的端点格式
# 可能的格式：
# 1. texttospeech/synthesize
# 2. text-to-speech/synthesize  
# 3. tts/synthesize
# 4. 或者使用与 ASR 类似的格式但不同的路径
TTS_API_URL = f"https://www.sophnet.com/api/open-apis/projects/{TTS_PROJECT_ID}/easyllms/texttospeech/synthesize"

# LLM 配置（大语言模型）
LLM_API_KEY = API_KEY  # 使用相同的 API Key
LLM_MODEL = "DeepSeek-V3.2-Fast"  # 模型名称
LLM_API_URL = "https://www.sophnet.com/api/open-apis/v1/chat/completions"
LLM_EASYLLM_ID = "2fTGI1iCsDk13YPAQC50AO"  # EasyLLM ID

# 兼容性配置（保留原有配置）
USE_DASHSCOPE_LLM = os.getenv("USE_DASHSCOPE_LLM", "false").lower() == "true"  # 默认使用自定义 LLM
USE_CUSTOM_LLM = os.getenv("USE_CUSTOM_LLM", "true").lower() == "true"  # 默认使用自定义 LLM

# TTS 配置
TTS_MODEL = "qwen3-tts-flash-realtime"
TTS_VOICE = "Cherry"  # 可选: Cherry, 等

# 音频配置
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 640  # 20ms 的音频数据
FORMAT = pyaudio.paInt16


# ==================== 音频处理类 ====================

class AudioRecorder:
    """音频录制器 - 用于 ASR 输入"""
    
    def __init__(self, sample_rate=SAMPLE_RATE, channels=CHANNELS, chunk=CHUNK):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.is_recording = False
        self.audio_queue = queue.Queue()
    
    def start_recording(self):
        """开始录音"""
        if self.is_recording:
            return
        
        self.is_recording = True
        self.stream = self.audio.open(
            format=FORMAT,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        
        # 在单独线程中录制
        threading.Thread(target=self._record_loop, daemon=True).start()
    
    def _record_loop(self):
        """录音循环"""
        while self.is_recording:
            try:
                data = self.stream.read(self.chunk, exception_on_overflow=False)
                self.audio_queue.put(data)
            except Exception as e:
                print(f"录音错误: {e}")
                break
    
    def stop_recording(self):
        """停止录音"""
        self.is_recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
    
    def get_audio_chunk(self, timeout=0.1):
        """获取音频块"""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_audio_buffer(self, duration=1.0):
        """获取指定时长的音频缓冲区"""
        buffer = b""
        target_size = int(self.sample_rate * duration * 2)  # 2 bytes per sample
        
        while len(buffer) < target_size and self.is_recording:
            chunk = self.get_audio_chunk(timeout=0.1)
            if chunk:
                buffer += chunk
        
        return buffer if len(buffer) > 0 else None
    
    def cleanup(self):
        """清理资源"""
        self.stop_recording()
        self.audio.terminate()


class AudioPlayer:
    """音频播放器 - 用于 TTS 输出"""
    
    def __init__(self, sample_rate=SAMPLE_RATE, channels=CHANNELS, chunk=CHUNK):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk = chunk
        self.audio = pyaudio.PyAudio()
        self.stream = None
    
    def play_audio(self, audio_data: bytes):
        """播放音频数据"""
        if not self.stream:
            self.stream = self.audio.open(
                format=FORMAT,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.chunk
            )
        
        # 分块播放，避免阻塞
        chunk_size = self.chunk * 2  # 2 bytes per sample
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            if chunk:
                self.stream.write(chunk)
    
    def cleanup(self):
        """清理资源"""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self.audio.terminate()


# ==================== ASR 处理类 ====================

class ParaformerASR:
    """Paraformer Tongyi 语音识别服务"""
    
    def __init__(
        self,
        api_key: str,
        project_id: str,
        easyllm_id: str,
        api_url: Optional[str] = None
    ):
        self.api_key = api_key
        self.project_id = project_id
        self.easyllm_id = easyllm_id
        self.api_url = api_url or f"https://www.sophnet.com/api/open-apis/projects/{project_id}/easyllms/speechtotext/transcriptions"
    
    def transcribe_from_url(self, audio_url: str) -> Optional[str]:
        """
        使用音频 URL 进行语音识别
        
        Args:
            audio_url: 公网可访问的音频文件链接
            
        Returns:
            识别出的文本，失败返回 None
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "audio_url": audio_url,
                "easyllm_id": self.easyllm_id
            }
            
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            # 解析返回结果，根据实际 API 响应格式调整
            if isinstance(result, dict):
                # 尝试常见的响应字段
                text = result.get("text") or result.get("transcription") or result.get("result")
                if text:
                    return text
                # 如果有嵌套结构
                if "data" in result:
                    data = result["data"]
                    text = data.get("text") or data.get("transcription") or data.get("result")
                    if text:
                        return text
            
            print(f"[ASR] API 返回格式异常: {result}")
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"[ASR] 请求错误: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[ASR] 响应内容: {e.response.text}")
            return None
        except Exception as e:
            print(f"[ASR] 识别错误: {e}")
            return None
    
    def transcribe_from_file(self, audio_file_path: str) -> Optional[str]:
        """
        使用本地音频文件进行语音识别
        
        Args:
            audio_file_path: 本地音频文件路径
            
        Returns:
            识别出的文本，失败返回 None
        """
        try:
            if not os.path.exists(audio_file_path):
                print(f"[ASR] 文件不存在: {audio_file_path}")
                return None
            
            headers = {
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # 准备 multipart/form-data
            # 根据 curl 示例，data 字段是 JSON 字符串，类型为 application/json
            data_json = json.dumps({"easyllm_id": self.easyllm_id})
            
            # 打开文件
            with open(audio_file_path, "rb") as audio_file:
                # 使用 requests 的 multipart/form-data 格式
                # data 字段：JSON 字符串，content-type 为 application/json
                # audio_file 字段：文件，content-type 为 audio/wav
                files = {
                    "data": (None, data_json, "application/json"),
                    "audio_file": (
                        os.path.basename(audio_file_path),
                        audio_file,
                        "audio/wav"
                    )
                }
                
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    files=files,
                    timeout=30
                )
            
            response.raise_for_status()
            result = response.json()
            
            # 解析返回结果
            if isinstance(result, dict):
                text = result.get("text") or result.get("transcription") or result.get("result")
                if text:
                    return text
                if "data" in result:
                    data = result["data"]
                    text = data.get("text") or data.get("transcription") or data.get("result")
                    if text:
                        return text
            
            print(f"[ASR] API 返回格式异常: {result}")
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"[ASR] 请求错误: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[ASR] 响应内容: {e.response.text}")
            return None
        except Exception as e:
            print(f"[ASR] 识别错误: {e}")
            return None
    
    def transcribe_from_bytes(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2
    ) -> Optional[str]:
        """
        使用音频字节数据进行语音识别
        
        Args:
            audio_data: PCM 音频数据（bytes）
            sample_rate: 采样率，默认 16000
            channels: 声道数，默认 1（单声道）
            sample_width: 采样位宽（字节），默认 2（16bit）
            
        Returns:
            识别出的文本，失败返回 None
        """
        # 将音频数据保存为临时 WAV 文件
        temp_file = None
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False
            ) as temp_file:
                temp_path = temp_file.name
                
                # 写入 WAV 文件
                with wave.open(temp_path, 'wb') as wav_file:
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(sample_width)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(audio_data)
            
            # 使用文件进行识别
            result = self.transcribe_from_file(temp_path)
            
            return result
            
        except Exception as e:
            print(f"[ASR] 处理音频数据错误: {e}")
            return None
        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except:
                    pass


# 全局 ASR 实例
_asr_instance: Optional[ParaformerASR] = None


def get_asr_instance() -> ParaformerASR:
    """获取 ASR 实例（单例模式）"""
    global _asr_instance
    if _asr_instance is None:
        _asr_instance = ParaformerASR(
            api_key=ASR_API_KEY,
            project_id=ASR_PROJECT_ID,
            easyllm_id=ASR_EASYLLM_ID,
            api_url=ASR_API_URL
        )
    return _asr_instance


def simple_asr_from_audio(audio_data: bytes) -> Optional[str]:
    """
    从音频数据识别文本（使用 Paraformer ASR）
    
    Args:
        audio_data: PCM 音频数据（bytes）
        
    Returns:
        识别出的文本，失败返回 None
    """
    asr = get_asr_instance()
    return asr.transcribe_from_bytes(
        audio_data,
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        sample_width=2  # 16bit = 2 bytes
    )


# ==================== TTS 处理类 ====================

class ParaformerTTS:
    """
    Paraformer Tongyi 文本转语音服务
    
    注意：根据您提供的示例，TTS API 端点可能与 ASR 不同。
    当前实现假设端点为 texttospeech/synthesize，如果实际端点不同，请修改 TTS_API_URL。
    """
    
    def __init__(
        self,
        api_key: str,
        project_id: str,
        easyllm_id: str,
        api_url: Optional[str] = None
    ):
        self.api_key = api_key
        self.project_id = project_id
        self.easyllm_id = easyllm_id
        self.api_url = api_url or f"https://www.sophnet.com/api/open-apis/projects/{project_id}/easyllms/texttospeech/synthesize"
    
    def synthesize_from_text(self, text: str) -> Optional[bytes]:
        """
        将文本转换为语音
        
        Args:
            text: 要转换的文本
            
        Returns:
            音频数据（bytes），失败返回 None
        """
        if not text or not text.strip():
            return None
        
        # #region agent log
        import json
        import time
        log_path = r"d:\HuaweiMoveData\Users\鸟\Desktop\mindmirror\.cursor\debug.log"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A",
                    "location": "ParaformerTTS.synthesize_from_text:entry",
                    "message": "TTS request starting",
                    "data": {
                        "api_url": self.api_url,
                        "api_key_prefix": self.api_key[:20] + "..." if len(self.api_key) > 20 else self.api_key,
                        "project_id": self.project_id,
                        "easyllm_id": self.easyllm_id,
                        "text_length": len(text)
                    },
                    "timestamp": int(time.time() * 1000)
                }) + "\n")
        except: pass
        # #endregion
        
        try:
            # 尝试多种可能的端点格式
            base_url = f"https://www.sophnet.com/api/open-apis/projects/{self.project_id}/easyllms"
            # 尝试更多可能的端点格式，包括不同的路径结构
            possible_urls = [
                # 标准格式变体
                f"{base_url}/texttospeech/synthesize",  # 当前尝试的
                f"{base_url}/text-to-speech/synthesize",  # 带连字符
                f"{base_url}/tts/synthesize",  # 简化版
                f"{base_url}/synthesize",  # 最简化
                f"{base_url}/texttospeech",  # 无synthesize
                f"{base_url}/text-to-speech",  # 无synthesize，带连字符
                # 可能TTS使用与ASR相同的端点但不同的方法或参数
                f"https://www.sophnet.com/api/open-apis/projects/{self.project_id}/easyllms/speechtotext/transcriptions",  # 尝试ASR端点（可能TTS也用它）
                # 可能在不同的路径下
                f"https://www.sophnet.com/api/open-apis/projects/{self.project_id}/texttospeech/synthesize",
                f"https://www.sophnet.com/api/open-apis/projects/{self.project_id}/tts/synthesize",
                f"https://www.sophnet.com/api/open-apis/v1/texttospeech/synthesize",
                f"https://www.sophnet.com/api/open-apis/v1/tts/synthesize",
                # 可能使用easyllm_id作为路径的一部分
                f"{base_url}/{self.easyllm_id}/synthesize",
                f"{base_url}/{self.easyllm_id}/texttospeech",
            ]
            
            # 尝试不同的请求格式
            # 格式1: JSON (当前使用的)
            headers_json = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            data_json = {
                "text": text,
                "easyllm_id": self.easyllm_id
            }
            
            # 格式2: multipart/form-data (类似ASR)
            headers_multipart = {
                "Authorization": f"Bearer {self.api_key}"
            }
            data_multipart = {
                "data": json.dumps({"text": text, "easyllm_id": self.easyllm_id})
            }
            
            response = None
            successful_url = None
            successful_method = None
            
            # 先尝试使用ASR端点但使用TTS参数（因为用户提供的TTS示例和ASR一样）
            asr_endpoint = f"https://www.sophnet.com/api/open-apis/projects/{self.project_id}/easyllms/speechtotext/transcriptions"
            
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "F",
                        "location": "ParaformerTTS.synthesize_from_text:try_asr_endpoint_with_tts_params",
                        "message": "Trying ASR endpoint with TTS parameters (user provided same curl for both)",
                        "data": {
                            "url": asr_endpoint,
                            "method": "multipart/form-data",
                            "params": {"text": text, "easyllm_id": self.easyllm_id}
                        },
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except: pass
            # #endregion
            
            try:
                # 尝试使用ASR端点，但参数使用text而不是audio_file
                files = {
                    "data": (None, json.dumps({"text": text, "easyllm_id": self.easyllm_id}), "application/json")
                }
                test_response = requests.post(
                    asr_endpoint,
                    headers=headers_multipart,
                    files=files,
                    timeout=30
                )
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "F",
                            "location": "ParaformerTTS.synthesize_from_text:asr_endpoint_with_tts_params_response",
                            "message": "ASR endpoint with TTS params response",
                            "data": {
                                "status_code": test_response.status_code,
                                "response_text": test_response.text[:500] if test_response.text else None
                            },
                            "timestamp": int(time.time() * 1000)
                        }) + "\n")
                except: pass
                # #endregion
                
                if test_response.status_code == 200:
                    response = test_response
                    successful_url = asr_endpoint
                    successful_method = "multipart"
            except Exception as e:
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "F",
                            "location": "ParaformerTTS.synthesize_from_text:asr_endpoint_exception",
                            "message": "ASR endpoint exception",
                            "data": {"error": str(e)},
                            "timestamp": int(time.time() * 1000)
                        }) + "\n")
                except: pass
                # #endregion
                pass
            
            # 再尝试当前URL的multipart格式（因为ASR使用multipart）
            if not response or response.status_code != 200:
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "B",
                            "location": "ParaformerTTS.synthesize_from_text:try_multipart",
                            "message": "Trying multipart/form-data format (like ASR)",
                            "data": {
                                "url": self.api_url,
                                "method": "multipart/form-data"
                            },
                            "timestamp": int(time.time() * 1000)
                        }) + "\n")
                except: pass
                # #endregion
                
                try:
                    # 尝试multipart格式（类似ASR）
                    files = {
                        "data": (None, json.dumps({"text": text, "easyllm_id": self.easyllm_id}), "application/json")
                    }
                    test_response = requests.post(
                        self.api_url,
                        headers=headers_multipart,
                        files=files,
                        timeout=30
                    )
                    # #region agent log
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "B",
                                "location": "ParaformerTTS.synthesize_from_text:multipart_response",
                                "message": "Multipart format response",
                                "data": {
                                    "status_code": test_response.status_code,
                                    "response_text": test_response.text[:500] if test_response.text else None
                                },
                                "timestamp": int(time.time() * 1000)
                            }) + "\n")
                    except: pass
                    # #endregion
                    
                    if test_response.status_code == 200:
                        response = test_response
                        successful_url = self.api_url
                        successful_method = "multipart"
                except Exception as e:
                    # #region agent log
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "B",
                                "location": "ParaformerTTS.synthesize_from_text:multipart_exception",
                                "message": "Multipart format exception",
                                "data": {"error": str(e)},
                                "timestamp": int(time.time() * 1000)
                            }) + "\n")
                    except: pass
                    # #endregion
                    pass
            
            # 如果multipart失败，尝试不同的URL
            if not response or response.status_code != 200:
                for test_url in possible_urls:
                    if test_url == self.api_url:
                        continue  # 已经试过了
                    
                    # #region agent log
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "A",
                                "location": "ParaformerTTS.synthesize_from_text:try_alternative_url",
                                "message": "Trying alternative URL",
                                "data": {"url": test_url, "method": "JSON"},
                                "timestamp": int(time.time() * 1000)
                            }) + "\n")
                    except: pass
                    # #endregion
                    
                    try:
                        test_response = requests.post(
                            test_url,
                            headers=headers_json,
                            json=data_json,
                            timeout=30
                        )
                        # #region agent log
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps({
                                    "sessionId": "debug-session",
                                    "runId": "run1",
                                    "hypothesisId": "A",
                                    "location": "ParaformerTTS.synthesize_from_text:alternative_url_response",
                                    "message": "Alternative URL response",
                                    "data": {
                                        "url": test_url,
                                        "status_code": test_response.status_code,
                                        "response_text": test_response.text[:500] if test_response.text else None
                                    },
                                    "timestamp": int(time.time() * 1000)
                                }) + "\n")
                        except: pass
                        # #endregion
                        
                        if test_response.status_code == 200:
                            response = test_response
                            successful_url = test_url
                            successful_method = "JSON"
                            # 更新API URL
                            self.api_url = test_url
                            break
                    except Exception as e:
                        # #region agent log
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps({
                                    "sessionId": "debug-session",
                                    "runId": "run1",
                                    "hypothesisId": "A",
                                    "location": "ParaformerTTS.synthesize_from_text:alternative_url_exception",
                                    "message": "Alternative URL exception",
                                    "data": {"url": test_url, "error": str(e)},
                                    "timestamp": int(time.time() * 1000)
                                }) + "\n")
                        except: pass
                        # #endregion
                        continue
            
            # 如果所有尝试都失败，使用原始URL和JSON格式
            if not response:
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A,B,C,D,E",
                            "location": "ParaformerTTS.synthesize_from_text:before_request",
                            "message": "Request details before sending (fallback)",
                            "data": {
                                "url": self.api_url,
                                "headers": {k: (v[:20] + "..." if len(v) > 20 else v) if k == "Authorization" else v for k, v in headers_json.items()},
                                "request_body": data_json,
                                "method": "POST"
                            },
                            "timestamp": int(time.time() * 1000)
                        }) + "\n")
                except: pass
                # #endregion
                
                response = requests.post(
                    self.api_url,
                    headers=headers_json,
                    json=data_json,
                    timeout=30
                )
            
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A,B,C,D,E",
                        "location": "ParaformerTTS.synthesize_from_text:after_request",
                        "message": "Response received",
                        "data": {
                            "status_code": response.status_code,
                            "response_headers": dict(response.headers),
                            "response_text": response.text[:1000] if response.text else None,
                            "response_content_type": response.headers.get("Content-Type", ""),
                            "response_size": len(response.content) if response.content else 0
                        },
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except: pass
            # #endregion
            
            response.raise_for_status()
            
            # 检查响应类型
            content_type = response.headers.get("Content-Type", "")
            
            if "application/json" in content_type:
                # 如果返回 JSON，可能包含音频 URL 或 base64 编码的音频
                result = response.json()
                
                # 尝试解析不同的响应格式
                if isinstance(result, dict):
                    # 情况1: 直接包含音频数据（base64）
                    audio_data = result.get("audio_data") or result.get("audio") or result.get("data")
                    if audio_data:
                        # 如果是 base64 编码
                        if isinstance(audio_data, str):
                            import base64
                            try:
                                return base64.b64decode(audio_data)
                            except:
                                pass
                        # 如果已经是 bytes
                        if isinstance(audio_data, bytes):
                            return audio_data
                    
                    # 情况2: 包含音频 URL
                    audio_url = result.get("audio_url") or result.get("url")
                    if audio_url:
                        # 下载音频文件
                        audio_response = requests.get(audio_url, timeout=30)
                        audio_response.raise_for_status()
                        return audio_response.content
                    
                    # 情况3: 嵌套结构
                    if "data" in result:
                        data_obj = result["data"]
                        audio_data = data_obj.get("audio_data") or data_obj.get("audio")
                        if audio_data:
                            if isinstance(audio_data, str):
                                import base64
                                try:
                                    return base64.b64decode(audio_data)
                                except:
                                    pass
                            if isinstance(audio_data, bytes):
                                return audio_data
                    
                    print(f"[TTS] API 返回格式异常: {result}")
                    return None
            else:
                # 如果直接返回音频数据（二进制）
                return response.content
            
        except requests.exceptions.RequestException as e:
            # #region agent log
            try:
                error_data = {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "status_code": None,
                    "response_text": None
                }
                if hasattr(e, 'response') and e.response is not None:
                    error_data["status_code"] = e.response.status_code
                    error_data["response_text"] = e.response.text[:1000] if e.response.text else None
                    error_data["response_headers"] = dict(e.response.headers) if e.response.headers else None
                
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A,B,C,D,E",
                        "location": "ParaformerTTS.synthesize_from_text:exception",
                        "message": "Request exception caught",
                        "data": error_data,
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except: pass
            # #endregion
            
            print(f"[TTS] 请求错误: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[TTS] 响应内容: {e.response.text[:500]}")  # 只打印前500字符
            return None
        except Exception as e:
            print(f"[TTS] 合成错误: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def synthesize_to_file(self, text: str, output_path: str) -> bool:
        """
        将文本转换为语音并保存到文件
        
        Args:
            text: 要转换的文本
            output_path: 输出文件路径（如 output.wav）
            
        Returns:
            成功返回 True，失败返回 False
        """
        audio_data = self.synthesize_from_text(text)
        
        if not audio_data:
            return False
        
        try:
            # 保存音频数据
            with open(output_path, "wb") as f:
                f.write(audio_data)
            return True
        except Exception as e:
            print(f"[TTS] 保存文件错误: {e}")
            return False


# 全局 TTS 实例
_tts_instance: Optional[ParaformerTTS] = None


def get_tts_instance() -> ParaformerTTS:
    """获取 TTS 实例（单例模式）"""
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = ParaformerTTS(
            api_key=TTS_API_KEY,
            project_id=TTS_PROJECT_ID,
            easyllm_id=TTS_EASYLLM_ID,
            api_url=TTS_API_URL
        )
    return _tts_instance


def simple_tts_from_text(text: str) -> Optional[bytes]:
    """
    从文本生成音频（使用 Paraformer TTS）
    
    Args:
        text: 要转换的文本
        
    Returns:
        音频数据（bytes），失败返回 None
    """
    tts = get_tts_instance()
    return tts.synthesize_from_text(text)


# ==================== LLM 处理类 ====================

class ParaformerLLM:
    """
    Paraformer 大语言模型服务（兼容 OpenAI API 格式）
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "DeepSeek-V3.2-Fast",
        api_url: Optional[str] = None,
        system_prompt: str = "你是一个友好的AI助手，请用简洁、自然的语言回答用户的问题。"
    ):
        self.api_key = api_key
        self.model = model
        self.api_url = api_url or "https://www.sophnet.com/api/open-apis/v1/chat/completions"
        self.system_prompt = system_prompt
        self.conversation_history = []  # 对话历史
    
    def chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Optional[str]:
        """
        发送聊天消息并获取回复
        
        Args:
            user_message: 用户消息
            system_prompt: 系统提示词（如果为 None，使用默认的）
            temperature: 温度参数，控制随机性
            max_tokens: 最大生成 token 数
            stream: 是否流式返回（当前实现不支持流式）
            
        Returns:
            AI 回复文本，失败返回 None
        """
        if not user_message or not user_message.strip():
            return None
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # 构建消息列表
            messages = []
            
            # 添加系统提示词
            sys_prompt = system_prompt or self.system_prompt
            if sys_prompt:
                messages.append({
                    "role": "system",
                    "content": sys_prompt
                })
            
            # 添加对话历史
            messages.extend(self.conversation_history)
            
            # 添加当前用户消息
            messages.append({
                "role": "user",
                "content": user_message
            })
            
            # 构建请求数据
            data = {
                "messages": messages,
                "model": self.model
            }
            
            if temperature is not None:
                data["temperature"] = temperature
            
            if max_tokens is not None:
                data["max_tokens"] = max_tokens
            
            if stream:
                data["stream"] = True
            
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=60
            )
            
            response.raise_for_status()
            result = response.json()
            
            # 解析响应（OpenAI 兼容格式）
            if isinstance(result, dict):
                choices = result.get("choices", [])
                if choices and len(choices) > 0:
                    message = choices[0].get("message", {})
                    content = message.get("content", "")
                    
                    if content:
                        # 更新对话历史
                        self.conversation_history.append({
                            "role": "user",
                            "content": user_message
                        })
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": content
                        })
                        
                        return content
                
                print(f"[LLM] API 返回格式异常: {result}")
                return None
            else:
                print(f"[LLM] API 返回格式异常: {result}")
                return None
            
        except requests.exceptions.RequestException as e:
            print(f"[LLM] 请求错误: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[LLM] 响应内容: {e.response.text[:500]}")
            return None
        except Exception as e:
            print(f"[LLM] 聊天错误: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []
    
    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self.system_prompt = prompt


# 全局 LLM 实例
_llm_instance: Optional[ParaformerLLM] = None


def get_llm_instance() -> ParaformerLLM:
    """获取 LLM 实例（单例模式）"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ParaformerLLM(
            api_key=LLM_API_KEY,
            model=LLM_MODEL,
            api_url=LLM_API_URL
        )
    return _llm_instance


def simple_llm_chat(user_message: str, system_prompt: Optional[str] = None) -> Optional[str]:
    """
    发送聊天消息并获取回复（使用 Paraformer LLM）
    
    Args:
        user_message: 用户消息
        system_prompt: 系统提示词（可选）
        
    Returns:
        AI 回复文本，失败返回 None
    """
    llm = get_llm_instance()
    return llm.chat(user_message, system_prompt=system_prompt)


# ==================== AgentScope 实时对话类 ====================

class RealtimeDialogAgent:
    """基于 AgentScope 的实时对话代理"""
    
    def __init__(
        self,
        dashscope_api_key: str,
        openai_api_key: Optional[str] = None,
        use_dashscope_llm: bool = True,
        llm_model: str = "qwen-max",
        tts_model: str = "qwen3-tts-flash-realtime",
        tts_voice: str = "Cherry",
        sys_prompt: str = "你是一个友好的AI助手，请用简洁、自然的语言回答用户的问题。"
    ):
        # 初始化 LLM 模型
        self.use_custom_llm = USE_CUSTOM_LLM
        
        if self.use_custom_llm:
            # 使用自定义的 Paraformer LLM
            # 延迟初始化，避免循环导入
            self.custom_llm = None  # 将在首次使用时初始化
            self.llm_model = None
            self.formatter = None
        elif use_dashscope_llm:
            # 使用 AgentScope 的 DashScope LLM
            self.llm_model = DashScopeChatModel(
                api_key=dashscope_api_key,
                model_name=llm_model,
                stream=True,
            )
            self.formatter = DashScopeChatFormatter()
            self.custom_llm = None
        else:
            # 使用 AgentScope 的 OpenAI LLM
            if not openai_api_key:
                raise ValueError("使用 OpenAI 时需要提供 openai_api_key")
            self.llm_model = OpenAIChatModel(
                api_key=openai_api_key,
                model_name=llm_model,
            )
            self.formatter = None
            self.custom_llm = None
        
        # 初始化 TTS 模型
        # 优先使用自定义的 Paraformer TTS，如果没有配置则使用 DashScope
        self.use_custom_tts = os.getenv("USE_CUSTOM_TTS", "false").lower() == "true"
        
        if self.use_custom_tts:
            # 使用自定义的 Paraformer TTS
            # 延迟初始化，避免循环导入
            self.custom_tts = None  # 将在首次使用时初始化
            self.tts_model = None  # 不使用 AgentScope 的 TTS
        else:
            # 使用 AgentScope 的 DashScope TTS
            if not AGENTSCOPE_AVAILABLE or DashScopeRealtimeTTSModel is None:
                raise ImportError("AgentScope 未正确安装或 DashScopeRealtimeTTSModel 不可用。请安装: pip install agentscope")
            self.tts_model = DashScopeRealtimeTTSModel(
                api_key=dashscope_api_key,
                model_name=tts_model,
                voice=tts_voice,
            )
            self.custom_tts = None
        
        # 创建对话代理（使用 ReActAgent）
        # 如果使用自定义 LLM 或 TTS，则不传入相应模型，后续手动处理
        if self.use_custom_llm:
            # 使用自定义 LLM，不创建 AgentScope 的 Agent
            self.agent = None
            self.user_agent = None
        else:
            if not AGENTSCOPE_AVAILABLE or ReActAgent is None or UserAgent is None:
                raise ImportError("AgentScope 未正确安装或 ReActAgent/UserAgent 不可用。请安装: pip install agentscope")
            self.agent = ReActAgent(
                name="Assistant",
                sys_prompt=sys_prompt,
                model=self.llm_model,
                formatter=self.formatter,
                tts_model=self.tts_model if not self.use_custom_tts else None,
            )
            # 创建用户代理（用于模拟用户输入）
            self.user_agent = UserAgent("User")
        
        # 音频处理
        self.recorder = AudioRecorder()
        self.player = AudioPlayer()
        
        # 运行状态
        self.is_running = False
    
    async def process_text_input(self, text: str):
        """处理文本输入：LLM -> TTS"""
        if not text or not text.strip():
            return
        
        print(f"\n[用户] {text}")
        
        try:
            reply_text = None
            
            if self.use_custom_llm:
                # 使用自定义的 Paraformer LLM
                if self.custom_llm is None:
                    # 延迟初始化，避免循环导入
                    self.custom_llm = get_llm_instance()
                
                print("[LLM] 正在生成回复...")
                loop = asyncio.get_event_loop()
                reply_text = await loop.run_in_executor(
                    None,
                    self.custom_llm.chat,
                    text
                )
                
                if reply_text:
                    print(f"[助手] {reply_text}")
                else:
                    print("[LLM] 生成回复失败")
                    return
            else:
                # 使用 AgentScope 的对话流程
                # 创建用户消息
                user_msg = self.user_agent(text)
                
                # 获取助手回复
                assistant_msg = await self.agent(user_msg)
                
                # 提取回复文本
                reply_text = assistant_msg.get_text_content() if hasattr(assistant_msg, 'get_text_content') else str(assistant_msg)
                print(f"[助手] {reply_text}")
            
            # TTS 处理
            if reply_text:
                if self.use_custom_tts:
                    # 使用自定义的 Paraformer TTS
                    if self.custom_tts is None:
                        # 延迟初始化，避免循环导入
                        self.custom_tts = get_tts_instance()
                    
                    print("[TTS] 正在合成语音...")
                    loop = asyncio.get_event_loop()
                    audio_data = await loop.run_in_executor(
                        None,
                        self.custom_tts.synthesize_from_text,
                        reply_text
                    )
                    
                    if audio_data:
                        print("[TTS] 播放回复音频")
                        self.player.play_audio(audio_data)
                    else:
                        print("[TTS] 音频合成失败")
                else:
                    # 使用 AgentScope 的 TTS（可能已经自动播放）
                    # 如果 TTS 没有自动播放，手动处理音频
                    if hasattr(assistant_msg, 'audio') and assistant_msg.audio:
                        self.player.play_audio(assistant_msg.audio)
        
        except Exception as e:
            print(f"处理错误: {e}")
            import traceback
            traceback.print_exc()
    
    async def process_audio_input(self, audio_data: bytes):
        """处理音频输入：ASR -> LLM -> TTS"""
        # 1. ASR: 音频转文本
        print("\n[ASR] 正在识别语音...")
        
        # 在异步环境中运行同步的 ASR 调用
        loop = asyncio.get_event_loop()
        user_text = await loop.run_in_executor(
            None,
            simple_asr_from_audio,
            audio_data
        )
        
        if not user_text or not user_text.strip():
            print("[ASR] 未识别到有效文本，请重试")
            return
        
        print(f"[ASR] 识别结果: {user_text}")
        
        # 2. LLM + TTS: 处理文本并生成回复
        await self.process_text_input(user_text)
    
    async def realtime_conversation_loop(self, use_audio_input: bool = False):
        """实时对话循环"""
        print("=" * 50)
        print("基于 AgentScope 的实时对话系统")
        print("=" * 50)
        
        if use_audio_input:
            print("模式: 语音输入 (使用 Paraformer ASR)")
            print("开始录音，按 Ctrl+C 停止...")
            print("提示: 说话后等待约1秒，系统会自动识别并回复")
            self.recorder.start_recording()
        else:
            print("模式: 文本输入")
            print("输入 'quit' 或 'exit' 退出")
        
        print("=" * 50)
        
        self.is_running = True
        
        try:
            if use_audio_input:
                # 音频输入模式
                while self.is_running:
                    # 收集 1 秒的音频
                    audio_buffer = self.recorder.get_audio_buffer(duration=1.0)
                    if audio_buffer:
                        await self.process_audio_input(audio_buffer)
                    await asyncio.sleep(0.1)
            else:
                # 文本输入模式
                loop = asyncio.get_event_loop()
                
                while self.is_running:
                    # 在单独线程中获取用户输入，避免阻塞事件循环
                    user_input = await loop.run_in_executor(
                        None, 
                        input, 
                        "\n[您] "
                    )
                    
                    if user_input.lower() in ['quit', 'exit', '退出']:
                        break
                    
                    if user_input.strip():
                        await self.process_text_input(user_input)
        
        except KeyboardInterrupt:
            print("\n\n收到停止信号，正在关闭...")
        finally:
            self.is_running = False
            self.cleanup()
            print("对话已结束")
    
    def start(self, use_audio_input: bool = False):
        """启动实时对话"""
        try:
            asyncio.run(self.realtime_conversation_loop(use_audio_input=use_audio_input))
        except Exception as e:
            print(f"启动错误: {e}")
            import traceback
            traceback.print_exc()
            self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        self.is_running = False
        self.recorder.cleanup()
        self.player.cleanup()


# ==================== 主程序 ====================

def main():
    """主函数"""
    print("基于 AgentScope 框架的实时对话示例")
    print("=" * 50)
    
    # 检查 API Key
    if DASHSCOPE_API_KEY == "your_dashscope_api_key":
        print("\n警告: 请设置 DASHSCOPE_API_KEY 环境变量")
        print("或在代码中直接配置 API Key")
        print("\n示例:")
        print("  export DASHSCOPE_API_KEY='your_key'")
        print("  或")
        print("  在代码中修改 DASHSCOPE_API_KEY 变量")
        
        use_default = input("\n是否使用默认配置继续? (y/n): ").strip().lower()
        if use_default != 'y':
            return
    
    print("\n请选择运行模式:")
    print("1. 文本输入模式 (推荐，LLM + TTS)")
    print("2. 语音输入模式 (需要集成 ASR 服务)")
    
    choice = input("\n请输入选项 (1 或 2，默认 1): ").strip() or "1"
    
    # 创建对话代理
    agent = RealtimeDialogAgent(
        dashscope_api_key=DASHSCOPE_API_KEY,
        openai_api_key=OPENAI_API_KEY if not USE_DASHSCOPE_LLM else None,
        use_dashscope_llm=USE_DASHSCOPE_LLM,
        llm_model=LLM_MODEL,
        tts_model=TTS_MODEL,
        tts_voice=TTS_VOICE,
        sys_prompt="你是一个友好的AI助手，请用简洁、自然的语言回答用户的问题。"
    )
    
    # 启动对话
    agent.start(use_audio_input=(choice == "2"))


if __name__ == "__main__":
    main()
