"""
豆包端到端实时语音大模型API接入示例
基于WebSocket二进制协议实现语音对话
"""

import websocket
import json
import struct
import uuid
import threading
import time
import pyaudio
import wave
import io
import numpy as np
import sys

# ==================== 配置信息 ====================
# 请填入您的认证信息
APP_ID = "9217093544"
ACCESS_KEY = "0ccP_ECF8esWV05HqkjtwvvaOyCEjtDh"

# WebSocket连接信息
WS_URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
RESOURCE_ID = "volc.speech.dialog"
APP_KEY = "PlgvMymc7f3tQnJ6"

# 模型配置
MODEL_VERSION = "O"  # 可选: O, SC, 1.2.1.0, 2.2.0.0
SPEAKER = "zh_female_vv_jupiter_bigtts"  # O版本音色

# 音频配置
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 640  # 20ms的音频数据
FORMAT = pyaudio.paInt16

# ==================== 协议编码 ====================

def encode_message(event_id, session_id=None, connect_id=None, payload=None, message_type=0b0001, has_event=True):
    """
    编码WebSocket二进制消息
    
    Args:
        event_id: 事件ID
        session_id: 会话ID（Session类事件使用）
        connect_id: 连接ID（Connect类事件使用）
        payload: 负载数据（bytes或dict）
        message_type: 消息类型，0b0001=文本事件，0b0010=音频事件
        has_event: 是否包含event字段
    """
    # Header (4 bytes)
    # Byte 0: Protocol Version (0b0001) | Header Size (0b0001)
    header_byte0 = 0b00010001
    
    # Byte 1: Message Type | Message type specific flags
    # Message type specific flags = 0b0100 (携带事件ID)
    if has_event:
        header_byte1 = (message_type << 4) | 0b0100
    else:
        header_byte1 = (message_type << 4) | 0b0000
    
    # Byte 2: Serialization (0b0001=JSON) | Compression (0b0000=无压缩)
    header_byte2 = 0b00010000
    
    # Byte 3: Reserved
    header_byte3 = 0x00
    
    header = bytes([header_byte0, header_byte1, header_byte2, header_byte3])
    
    # Optional字段
    optional = b''
    
    # Event ID (4 bytes, 如果has_event=True)
    if has_event:
        optional += struct.pack('>I', event_id)
    
    # Connect ID (Connect类事件使用，如StartConnection/FinishConnection)
    if connect_id:
        connect_id_bytes = connect_id.encode('utf-8')
        optional += struct.pack('>I', len(connect_id_bytes))
        optional += connect_id_bytes
    
    # Session ID (Session类事件使用，如StartSession/FinishSession)
    if session_id:
        session_id_bytes = session_id.encode('utf-8')
        optional += struct.pack('>I', len(session_id_bytes))
        optional += session_id_bytes
    
    # Payload
    if payload is None:
        payload = {}
    
    if isinstance(payload, dict):
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    elif isinstance(payload, str):
        payload_bytes = payload.encode('utf-8')
    else:
        payload_bytes = payload
    
    # Payload Size (4 bytes)
    payload_size = struct.pack('>I', len(payload_bytes))
    
    # 完整消息
    message = header + optional + payload_size + payload_bytes
    return message


def encode_audio_message(session_id, audio_data):
    """
    编码音频消息 (TaskRequest事件)
    """
    # Header for audio
    header_byte0 = 0b00010001
    header_byte1 = (0b0010 << 4) | 0b0000  # Audio-only request, no event
    header_byte2 = 0b00000000  # Raw data, no compression
    header_byte3 = 0x00
    
    header = bytes([header_byte0, header_byte1, header_byte2, header_byte3])
    
    # Session ID
    if session_id:
        session_id_bytes = session_id.encode('utf-8')
        optional = struct.pack('>I', len(session_id_bytes)) + session_id_bytes
    else:
        optional = b''
    
    # Payload size and audio data
    payload_size = struct.pack('>I', len(audio_data))
    
    message = header + optional + payload_size + audio_data
    return message


def decode_message(data):
    """
    解码WebSocket二进制消息
    """
    if len(data) < 4:
        return None
    
    try:
        # 解析Header
        header_byte0 = data[0]
        header_byte1 = data[1]
        header_byte2 = data[2]  # 修复：应该是data[2]而不是data[2]
        
        protocol_version = (header_byte0 >> 4) & 0x0F
        message_type = (header_byte1 >> 4) & 0x0F
        serialization = (header_byte2 >> 4) & 0x0F
        flags = header_byte1 & 0x0F
        
        pos = 4
        
        # 解析Optional字段
        event_id = None
        session_id = None
        
        # 根据消息类型判断是否有event字段
        # 0b1001 = Full-server response (文本事件，有event)
        # 0b1011 = Audio-only response (音频事件，有event)
        # 0b1111 = Error information (错误事件，有event)
        if flags & 0b0100:  # 有event字段
            if len(data) >= pos + 4:
                event_id = struct.unpack('>I', data[pos:pos+4])[0]
                pos += 4
        
        # Session ID (只有Session类事件才有)
        # 检查是否还有足够的数据
        if len(data) >= pos + 4:
            session_id_size = struct.unpack('>I', data[pos:pos+4])[0]
            pos += 4
            if session_id_size > 0 and len(data) >= pos + session_id_size:
                try:
                    session_id = data[pos:pos+session_id_size].decode('utf-8')
                    pos += session_id_size
                except:
                    # Session ID解码失败，跳过
                    pos += session_id_size
        
        # Payload
        if len(data) >= pos + 4:
            payload_size = struct.unpack('>I', data[pos:pos+4])[0]
            pos += 4
            
            # 验证payload大小是否合理
            remaining_data = len(data) - pos
            if payload_size > remaining_data:
                # payload大小不匹配，可能是分帧或者协议错误
                print(f"⚠️  Payload大小不匹配: 声明={payload_size}, 实际剩余={remaining_data}, 总长度={len(data)}")
                # 使用实际剩余的数据
                payload_size = remaining_data
            
            if payload_size > 0 and len(data) >= pos + payload_size:
                payload = data[pos:pos+payload_size]
                
                # 根据序列化方式解析
                if serialization == 0b0001:  # JSON
                    try:
                        payload = json.loads(payload.decode('utf-8'))
                    except:
                        # JSON解析失败，保持原始bytes
                        pass
                # 0b0000: Raw (音频数据)，保持为bytes
                
                return {
                    'event_id': event_id,
                    'session_id': session_id,
                    'message_type': message_type,
                    'payload': payload
                }
        
        return None
    except Exception as e:
        print(f"⚠️  解码消息时出错: {e}, 数据长度: {len(data)}")
        return None


# ==================== WebSocket客户端 ====================

class RealtimeDialogClient:
    def __init__(self):
        self.ws = None
        self.session_id = str(uuid.uuid4())
        self.connect_id = str(uuid.uuid4())
        self.connected = False
        self.session_started = False
        self.audio_input_stream = None
        self.audio_output_stream = None
        self.audio_output = None
        self.conversation_count = 0  # 对话轮次计数
        self.waiting_for_response = False  # 是否等待模型回复
        self.current_audio_buffer = []  # 当前音频缓冲区
        
    def on_message(self, ws, message):
        """处理接收到的消息"""
        if isinstance(message, bytes):
            try:
                decoded = decode_message(message)
                if decoded:
                    self.handle_server_event(decoded)
                else:
                    # 如果解码失败，可能是音频数据分帧，尝试直接处理
                    print(f"⚠️  消息解码失败，数据长度: {len(message)}")
            except Exception as e:
                print(f"⚠️  处理消息时出错: {e}")
                # 尝试直接作为音频数据处理（可能是TTSResponse）
                if len(message) > 100:  # 可能是音频数据
                    try:
                        # 尝试解析为音频响应
                        self.handle_audio_response(message)
                    except:
                        pass
    
    def on_error(self, ws, error):
        """处理错误"""
        print(f"WebSocket错误: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """连接关闭"""
        print("WebSocket连接已关闭")
        self.connected = False
        self.session_started = False
    
    def on_open(self, ws):
        """连接打开"""
        print("WebSocket连接已建立")
        self.connected = True
        
        # 发送StartConnection事件
        self.send_start_connection()
        
        # 等待一下再发送StartSession
        time.sleep(0.1)
        self.send_start_session()
    
    def handle_server_event(self, event):
        """处理服务器事件"""
        event_id = event.get('event_id')
        payload = event.get('payload', {})
        
        if event_id == 50:  # ConnectionStarted
            print("✓ 连接已启动")
        elif event_id == 51:  # ConnectionFailed
            print(f"✗ 连接失败: {payload.get('error', '')}")
        elif event_id == 150:  # SessionStarted
            print(f"✓ 会话已启动, dialog_id: {payload.get('dialog_id', '')}")
            self.session_started = True
        elif event_id == 152:  # SessionFinished
            print("会话已结束")
            self.session_started = False
        elif event_id == 153:  # SessionFailed
            print(f"✗ 会话失败: {payload.get('error', '')}")
        elif event_id == 350:  # TTSSentenceStart
            print(f"开始合成音频: {payload.get('text', '')}")
        elif event_id == 351:  # TTSSentenceEnd
            print("分句结束")
        elif event_id == 352:  # TTSResponse
            # 音频数据（Raw格式）
            if isinstance(payload, bytes):
                self.handle_audio_response(payload)
            else:
                print(f"⚠️  TTSResponse payload不是bytes类型: {type(payload)}")
        elif event_id == 359:  # TTSEnded
            print("音频合成结束")
            # 一轮对话完成
            self.waiting_for_response = False
            self.conversation_count += 1
            print(f"\n[对话轮次: {self.conversation_count}/2]")
        elif event_id == 450:  # ASRInfo
            print(f"检测到用户说话, question_id: {payload.get('question_id', '')}")
        elif event_id == 451:  # ASRResponse
            results = payload.get('results', [])
            for result in results:
                text = result.get('text', '')
                is_interim = result.get('is_interim', False)
                if text:
                    print(f"识别结果{'[临时]' if is_interim else ''}: {text}")
        elif event_id == 459:  # ASREnded
            print("用户说话结束")
        elif event_id == 550:  # ChatResponse
            content = payload.get('content', '')
            if content:
                print(f"模型回复: {content}")
        elif event_id == 559:  # ChatEnded
            print("模型回复结束")
        elif event_id == 154:  # UsageResponse
            usage = payload.get('usage', {})
            print(f"用量信息: {usage}")
        else:
            print(f"未知事件 ID={event_id}, payload={payload}")
    
    def handle_audio_response(self, audio_data):
        """处理音频响应并实时播放"""
        # 保存音频数据到缓冲区
        self.current_audio_buffer.append(audio_data)
        
        # 实时播放PCM音频（24000Hz, 16bit, 单声道）
        if self.audio_output_stream:
            try:
                # 如果音频数据是32bit，需要转换为16bit
                # 先尝试直接播放（假设是16bit）
                self.audio_output_stream.write(audio_data)
            except Exception as e:
                print(f"播放音频时出错: {e}")
        
        # 同时保存到文件（可选）
        if not hasattr(self, 'audio_file'):
            self.audio_file = open('output.pcm', 'wb')
        self.audio_file.write(audio_data)
        self.audio_file.flush()
    
    def send_start_connection(self):
        """发送StartConnection事件（Connect类事件，使用connect_id）"""
        payload = {}
        message = encode_message(
            event_id=1, 
            connect_id=self.connect_id,  # Connect类事件使用connect_id
            payload=payload, 
            has_event=True
        )
        self.ws.send(message, websocket.ABNF.OPCODE_BINARY)
        print("已发送 StartConnection 事件")
    
    def send_start_session(self):
        """发送StartSession事件"""
        payload = {
            "dialog": {
                "extra": {
                    "model": MODEL_VERSION
                }
            },
            "tts": {
                "speaker": SPEAKER,
                "audio_config": {
                    "channel": 1,
                    "format": "pcm_s16le",  # 16bit PCM，小端序
                    "sample_rate": 24000
                }
            }
        }
        message = encode_message(
            event_id=100,
            session_id=self.session_id,  # Session类事件使用session_id
            payload=payload,
            has_event=True
        )
        self.ws.send(message, websocket.ABNF.OPCODE_BINARY)
        print("已发送 StartSession 事件")
    
    def send_audio(self, audio_data):
        """发送音频数据"""
        if not self.session_started:
            print("会话未启动，无法发送音频")
            return
        
        message = encode_audio_message(self.session_id, audio_data)
        self.ws.send(message, websocket.ABNF.OPCODE_BINARY)
    
    def send_finish_session(self):
        """发送FinishSession事件（Session类事件，使用session_id）"""
        if not self.ws or not self.connected:
            print("连接已关闭，无法发送FinishSession")
            return
        try:
            payload = {}
            message = encode_message(
                event_id=102, 
                session_id=self.session_id,  # Session类事件使用session_id
                payload=payload, 
                has_event=True
            )
            self.ws.send(message, websocket.ABNF.OPCODE_BINARY)
            print("已发送 FinishSession 事件")
        except Exception as e:
            print(f"发送FinishSession失败: {e}")
    
    def send_text_query(self, text):
        """发送文本查询"""
        if not self.session_started:
            print("会话未启动，无法发送文本")
            return
        
        payload = {
            "content": text
        }
        message = encode_message(
            event_id=501, 
            session_id=self.session_id,  # Session类事件
            payload=payload, 
            has_event=True
        )
        self.ws.send(message, websocket.ABNF.OPCODE_BINARY)
        print(f"已发送文本查询: {text}")
    
    def connect(self):
        """建立WebSocket连接"""
        headers = {
            "X-Api-App-ID": APP_ID,
            "X-Api-Access-Key": ACCESS_KEY,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-App-Key": APP_KEY,
            "X-Api-Connect-Id": self.connect_id
        }
        
        ws = websocket.WebSocketApp(
            WS_URL,
            header=headers,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        self.ws = ws
        ws.run_forever()
    
    def init_audio_output(self):
        """初始化音频输出流"""
        try:
            self.audio_output = pyaudio.PyAudio()
            # TTS输出：24000Hz, 16bit, 单声道
            self.audio_output_stream = self.audio_output.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=24000,  # TTS采样率
                output=True,
                frames_per_buffer=CHUNK
            )
            print("✓ 音频输出已初始化")
        except Exception as e:
            print(f"⚠️  无法初始化音频输出: {e}")
            print("   音频将保存到文件，但无法实时播放")
    
    def cleanup_audio_output(self):
        """清理音频输出资源"""
        if self.audio_output_stream:
            self.audio_output_stream.stop_stream()
            self.audio_output_stream.close()
            self.audio_output_stream = None
        if self.audio_output:
            self.audio_output.terminate()
            self.audio_output = None
        if hasattr(self, 'audio_file'):
            self.audio_file.close()
    
    def start_audio_input(self, max_conversations=2):
        """启动音频输入（麦克风）进行实时对话"""
        if not self.session_started:
            print("等待会话启动...")
            while not self.session_started:
                time.sleep(0.1)
        
        print(f"\n{'='*50}")
        print("开始实时对话")
        print(f"将进行 {max_conversations} 轮对话后自动结束")
        print("请对着麦克风说话，说完后等待模型回复...")
        print("按 Ctrl+C 可提前结束")
        print(f"{'='*50}\n")
        
        audio = pyaudio.PyAudio()
        
        try:
            self.audio_input_stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK
            )
            
            # 初始化音频输出
            self.init_audio_output()
            
            # 持续发送音频数据
            audio_thread = threading.Thread(
                target=self._audio_input_loop,
                args=(audio,),
                daemon=True
            )
            audio_thread.start()
            
            # 等待对话完成
            while self.conversation_count < max_conversations and self.session_started:
                time.sleep(0.5)
            
            print(f"\n已完成 {self.conversation_count} 轮对话，准备结束...")
            
        except KeyboardInterrupt:
            print("\n用户中断")
        finally:
            if self.audio_input_stream:
                self.audio_input_stream.stop_stream()
                self.audio_input_stream.close()
            audio.terminate()
            self.cleanup_audio_output()
    
    def _audio_input_loop(self, audio):
        """音频输入循环（在单独线程中运行）"""
        while self.session_started and self.conversation_count < 2:
            try:
                audio_data = self.audio_input_stream.read(CHUNK, exception_on_overflow=False)
                self.send_audio(audio_data)
                time.sleep(0.02)  # 20ms间隔
            except Exception as e:
                print(f"音频输入错误: {e}")
                break


# ==================== 硬件检测 ====================

def list_audio_devices():
    """列出所有音频设备"""
    print("\n" + "=" * 50)
    print("音频设备列表")
    print("=" * 50)
    
    try:
        audio = pyaudio.PyAudio()
        device_count = audio.get_device_count()
        
        print(f"\n找到 {device_count} 个音频设备:\n")
        
        input_devices = []
        output_devices = []
        
        for i in range(device_count):
            device_info = audio.get_device_info_by_index(i)
            device_name = device_info.get('name', 'Unknown')
            max_input_channels = device_info.get('maxInputChannels', 0)
            max_output_channels = device_info.get('maxOutputChannels', 0)
            default_sample_rate = device_info.get('defaultSampleRate', 0)
            
            device_type = []
            if max_input_channels > 0:
                device_type.append("输入")
                input_devices.append((i, device_name))
            if max_output_channels > 0:
                device_type.append("输出")
                output_devices.append((i, device_name))
            
            device_type_str = "/".join(device_type) if device_type else "未知"
            
            print(f"设备 {i}: {device_name}")
            print(f"  类型: {device_type_str}")
            print(f"  输入通道: {max_input_channels}, 输出通道: {max_output_channels}")
            print(f"  默认采样率: {default_sample_rate} Hz")
            print()
        
        # 显示默认设备
        try:
            default_input = audio.get_default_input_device_info()
            default_output = audio.get_default_output_device_info()
            print(f"默认输入设备: {default_input['name']} (索引: {default_input['index']})")
            print(f"默认输出设备: {default_output['name']} (索引: {default_output['index']})")
        except Exception as e:
            print(f"无法获取默认设备信息: {e}")
        
        audio.terminate()
        
        return input_devices, output_devices
        
    except Exception as e:
        print(f"❌ 无法列出音频设备: {e}")
        return [], []


def test_microphone(duration=3, device_index=None):
    """测试麦克风是否正常工作"""
    print("\n" + "=" * 50)
    print("麦克风测试")
    print("=" * 50)
    
    try:
        audio = pyaudio.PyAudio()
        
        # 获取设备信息
        if device_index is None:
            try:
                device_info = audio.get_default_input_device_info()
                device_index = device_info['index']
                device_name = device_info['name']
            except:
                print("❌ 无法获取默认输入设备，尝试使用设备索引 0")
                device_index = 0
                device_name = "设备 0"
        else:
            try:
                device_info = audio.get_device_info_by_index(device_index)
                device_name = device_info['name']
            except:
                device_name = f"设备 {device_index}"
        
        print(f"使用设备: {device_name} (索引: {device_index})")
        print(f"测试时长: {duration} 秒")
        print("请对着麦克风说话...\n")
        
        # 打开音频流
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )
        
        print("开始录音...")
        frames = []
        max_volume = 0
        min_volume = float('inf')
        
        for i in range(0, int(SAMPLE_RATE / CHUNK * duration)):
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                
                # 计算音量（RMS）
                audio_data = np.frombuffer(data, dtype=np.int16)
                volume = np.sqrt(np.mean(audio_data**2))
                max_volume = max(max_volume, volume)
                min_volume = min(min_volume, volume)
                
                # 显示实时音量条
                volume_bar = "█" * int(volume / 1000)
                print(f"\r音量: {volume:.0f} {volume_bar:<20}", end="", flush=True)
                
            except Exception as e:
                print(f"\n❌ 读取音频数据时出错: {e}")
                break
        
        stream.stop_stream()
        stream.close()
        audio.terminate()
        
        print("\n\n测试结果:")
        print(f"  最大音量: {max_volume:.0f}")
        print(f"  最小音量: {min_volume:.0f}")
        print(f"  平均音量: {np.sqrt(np.mean([np.mean(np.frombuffer(f, dtype=np.int16)**2) for f in frames])):.0f}")
        
        if max_volume < 100:
            print("⚠️  警告: 检测到的音量很低，可能麦克风未正常工作或未连接")
            print("   建议: 检查麦克风连接和系统音量设置")
            return False
        elif max_volume > 1000:
            print("✓ 麦克风工作正常，检测到有效音频输入")
            return True
        else:
            print("⚠️  麦克风可能工作，但音量较低")
            return True
            
    except OSError as e:
        print(f"❌ 无法打开麦克风: {e}")
        print("   可能原因:")
        print("   1. 麦克风未连接")
        print("   2. 麦克风被其他程序占用")
        print("   3. 权限问题（Windows/Mac可能需要授权）")
        return False
    except Exception as e:
        print(f"❌ 麦克风测试失败: {e}")
        return False


def test_speaker(duration=2, device_index=None):
    """测试扬声器是否正常工作"""
    print("\n" + "=" * 50)
    print("扬声器测试")
    print("=" * 50)
    
    try:
        audio = pyaudio.PyAudio()
        
        # 获取设备信息
        if device_index is None:
            try:
                device_info = audio.get_default_output_device_info()
                device_index = device_info['index']
                device_name = device_info['name']
            except:
                print("❌ 无法获取默认输出设备，尝试使用设备索引 0")
                device_index = 0
                device_name = "设备 0"
        else:
            try:
                device_info = audio.get_device_info_by_index(device_index)
                device_name = device_info['name']
            except:
                device_name = f"设备 {device_index}"
        
        print(f"使用设备: {device_name} (索引: {device_index})")
        print("正在播放测试音频...")
        
        # 生成测试音频（440Hz正弦波，A4音符）
        sample_rate = 24000  # 使用TTS输出采样率
        frequency = 440
        frames = []
        
        for i in range(int(sample_rate * duration)):
            # 生成正弦波，并添加淡入淡出
            t = float(i) / sample_rate
            fade = min(1.0, i / (sample_rate * 0.1), (sample_rate * duration - i) / (sample_rate * 0.1))
            value = int(32767 * 0.3 * fade * np.sin(2 * np.pi * frequency * t))
            frames.append(struct.pack('<h', value))
        
        audio_data = b''.join(frames)
        
        # 打开输出流
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            output=True,
            output_device_index=device_index,
            frames_per_buffer=CHUNK
        )
        
        # 播放音频
        chunk_size = CHUNK * 2  # 16bit = 2 bytes
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            stream.write(chunk)
        
        stream.stop_stream()
        stream.close()
        audio.terminate()
        
        print("✓ 测试音频播放完成")
        print("  如果您听到了440Hz的提示音，说明扬声器工作正常")
        return True
        
    except OSError as e:
        print(f"❌ 无法打开扬声器: {e}")
        print("   可能原因:")
        print("   1. 扬声器未连接")
        print("   2. 扬声器被其他程序占用")
        print("   3. 系统音量设置为静音")
        return False
    except Exception as e:
        print(f"❌ 扬声器测试失败: {e}")
        return False


def hardware_check():
    """完整的硬件检测流程"""
    print("\n" + "=" * 50)
    print("硬件检测开始")
    print("=" * 50)
    
    # 1. 列出音频设备
    input_devices, output_devices = list_audio_devices()
    
    if not input_devices:
        print("\n⚠️  警告: 未找到可用的输入设备（麦克风）")
    if not output_devices:
        print("\n⚠️  警告: 未找到可用的输出设备（扬声器）")
    
    # 2. 测试麦克风
    mic_ok = False
    if input_devices:
        user_input = input("\n是否测试麦克风? (y/n, 默认y): ").strip().lower()
        if user_input != 'n':
            mic_ok = test_microphone(duration=3)
        else:
            print("跳过麦克风测试")
            mic_ok = True  # 假设正常，因为用户选择跳过
    else:
        print("\n跳过麦克风测试（未找到输入设备）")
    
    # 3. 测试扬声器
    speaker_ok = False
    if output_devices:
        user_input = input("\n是否测试扬声器? (y/n, 默认y): ").strip().lower()
        if user_input != 'n':
            speaker_ok = test_speaker(duration=2)
        else:
            print("跳过扬声器测试")
            speaker_ok = True  # 假设正常，因为用户选择跳过
    else:
        print("\n跳过扬声器测试（未找到输出设备）")
    
    # 4. 总结
    print("\n" + "=" * 50)
    print("硬件检测总结")
    print("=" * 50)
    print(f"麦克风: {'✓ 正常' if mic_ok else '❌ 异常'}")
    print(f"扬声器: {'✓ 正常' if speaker_ok else '❌ 异常'}")
    
    if mic_ok and speaker_ok:
        print("\n✓ 硬件检测通过，可以开始使用语音对话功能")
        return True
    else:
        print("\n⚠️  硬件检测发现问题，建议先解决硬件问题再继续")
        if not mic_ok:
            print("   - 麦克风问题可能影响语音输入功能")
        if not speaker_ok:
            print("   - 扬声器问题可能影响音频播放功能")
        
        user_input = input("\n是否继续运行? (y/n, 默认y): ").strip().lower()
        return user_input != 'n'


# ==================== 主程序 ====================

def main():
    """主函数"""
    print("=" * 50)
    print("豆包端到端实时语音大模型API接入示例")
    print("=" * 50)
    print(f"APP ID: {APP_ID}")
    print(f"模型版本: {MODEL_VERSION}")
    print(f"音色: {SPEAKER}")
    print("=" * 50)
    
    # 硬件检测
    print("\n开始硬件检测...")
    if not hardware_check():
        print("\n程序退出")
        return
    
    print("\n" + "=" * 50)
    print("开始连接API服务")
    print("=" * 50)
    
    client = RealtimeDialogClient()
    
    # 在单独线程中运行WebSocket
    ws_thread = threading.Thread(target=client.connect, daemon=True)
    ws_thread.start()
    
    # 等待连接建立
    time.sleep(2)
    
    if not client.connected:
        print("连接失败，请检查配置")
        return
    
    # 等待会话启动
    max_wait = 10
    waited = 0
    while not client.session_started and waited < max_wait:
        time.sleep(0.5)
        waited += 0.5
    
    if not client.session_started:
        print("❌ 会话启动失败，请检查配置和网络连接")
        return
    
    print("\n✓ 会话已启动，可以开始对话\n")
    
    # 启动实时音频对话（两轮后自动结束）
    try:
        client.start_audio_input(max_conversations=2)
    except KeyboardInterrupt:
        print("\n用户中断对话")
    
    # 结束会话
    print("\n结束会话...")
    client.send_finish_session()
    time.sleep(1)
    
    if client.ws:
        client.ws.close()
    
    print("\n程序结束")


if __name__ == "__main__":
    main()

