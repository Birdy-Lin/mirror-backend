"""
豆包端到端实时语音大模型 - 简化版
专注于实时对话功能
"""

import websocket
import json
import struct
import uuid
import threading
import time
import pyaudio
import numpy as np

# ==================== 配置 ====================
APP_ID = "9217093544"
ACCESS_KEY = "0ccP_ECF8esWV05HqkjtwvvaOyCEjtDh"
WS_URL = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
RESOURCE_ID = "volc.speech.dialog"
APP_KEY = "PlgvMymc7f3tQnJ6"

MODEL_VERSION = "O"
SPEAKER = "zh_female_vv_jupiter_bigtts"

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK = 640  # 20ms
TTS_SAMPLE_RATE = 24000

# ==================== 协议编码 ====================

def encode_event(event_id, session_id=None, connect_id=None, payload=None):
    """编码事件消息 - 严格按照文档示例"""
    # Header: [protocol_version(4bit)|header_size(4bit)] [message_type(4bit)|flags(4bit)] [serialization(4bit)|compression(4bit)] [reserved]
    header = bytes([0x11, 0x14, 0x10, 0x00])  # 0x14 = message_type(0b0001) | flags(0b0100=有event)
    
    # Optional字段 - 严格按照顺序
    optional = struct.pack('>I', event_id)  # Event ID (4 bytes, 必须)
    
    # Connect ID (仅Connect类事件，可选，但文档示例中没有)
    # 根据文档示例，StartConnection事件不包含connect_id
    # if connect_id:
    #     connect_id_bytes = connect_id.encode('utf-8')
    #     optional += struct.pack('>I', len(connect_id_bytes)) + connect_id_bytes
    
    # Session ID (仅Session类事件，必须)
    if session_id:
        session_id_bytes = session_id.encode('utf-8')
        optional += struct.pack('>I', len(session_id_bytes)) + session_id_bytes
    
    # Payload
    if payload is None:
        payload = {}
    if isinstance(payload, dict):
        # 使用ensure_ascii=False，但确保长度计算正确
        payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    else:
        payload_bytes = payload
    
    # Payload size + payload (必须最后)
    payload_size = struct.pack('>I', len(payload_bytes))
    
    return header + optional + payload_size + payload_bytes


def encode_audio(session_id, audio_data):
    """编码音频消息"""
    # Header: Audio-only request, no event
    header = bytes([0x11, 0x20, 0x00, 0x00])  # 0x20 = message_type(0b0010) | flags(0b0000=无event)
    
    # Session ID
    session_id_bytes = session_id.encode('utf-8')
    optional = struct.pack('>I', len(session_id_bytes)) + session_id_bytes
    
    # Payload size + audio data
    payload_size = struct.pack('>I', len(audio_data))
    
    return header + optional + payload_size + audio_data


def decode_message(data):
    """解码消息"""
    if len(data) < 4:
        return None
    
    pos = 4
    event_id = None
    session_id = None
    payload = None
    
    # Event ID
    if len(data) >= pos + 4:
        event_id = struct.unpack('>I', data[pos:pos+4])[0]
        pos += 4
    
    # Session ID (如果有)
    if len(data) >= pos + 4:
        session_id_size = struct.unpack('>I', data[pos:pos+4])[0]
        pos += 4
        if session_id_size > 0 and len(data) >= pos + session_id_size:
            session_id = data[pos:pos+session_id_size].decode('utf-8')
            pos += session_id_size
    
    # Payload
    if len(data) >= pos + 4:
        payload_size = struct.unpack('>I', data[pos:pos+4])[0]
        pos += 4
        if len(data) >= pos + payload_size:
            payload = data[pos:pos+payload_size]
            # 尝试解析JSON
            try:
                payload = json.loads(payload.decode('utf-8'))
            except:
                pass  # 保持为bytes（音频数据）
    
    return {'event_id': event_id, 'session_id': session_id, 'payload': payload}


# ==================== 客户端 ====================

class SimpleDialogClient:
    def __init__(self):
        self.ws = None
        self.session_id = str(uuid.uuid4())
        self.connect_id = str(uuid.uuid4())
        self.connected = False
        self.session_started = False
        self.conversation_count = 0
        
        # 音频
        self.audio_input = None
        self.audio_output = None
        self.input_stream = None
        self.output_stream = None
        
    def on_open(self, ws):
        print("✓ WebSocket连接已建立")
        self.connected = True
        
        # 发送StartConnection (Connect类事件，不需要connect_id字段，payload为空)
        msg = encode_event(1, payload={})
        ws.send(msg, websocket.ABNF.OPCODE_BINARY)
        print("✓ 已发送 StartConnection")
        
        time.sleep(0.1)
        
        # 发送StartSession
        payload = {
            "dialog": {"extra": {"model": MODEL_VERSION}},
            "tts": {
                "speaker": SPEAKER,
                "audio_config": {
                    "channel": 1,
                    "format": "pcm_s16le",
                    "sample_rate": 24000
                }
            }
        }
        msg = encode_event(100, session_id=self.session_id, payload=payload)
        ws.send(msg, websocket.ABNF.OPCODE_BINARY)
        print("✓ 已发送 StartSession")
    
    def on_message(self, ws, message):
        if not isinstance(message, bytes):
            return
        
        decoded = decode_message(message)
        if not decoded:
            return
        
        event_id = decoded.get('event_id')
        payload = decoded.get('payload', {})
        
        # 处理事件
        if event_id == 50:  # ConnectionStarted
            print("✓ 连接已启动")
        elif event_id == 150:  # SessionStarted
            print(f"✓ 会话已启动: {payload.get('dialog_id', '')}")
            self.session_started = True
        elif event_id == 152:  # SessionFinished
            self.session_started = False
        elif event_id == 153:  # SessionFailed
            print(f"✗ 会话失败: {payload.get('error', '')}")
        elif event_id == 350:  # TTSSentenceStart
            text = payload.get('text', '')
            if text:
                print(f"💬 {text}")
        elif event_id == 352:  # TTSResponse (音频)
            if isinstance(payload, bytes) and self.output_stream:
                try:
                    self.output_stream.write(payload)
                except:
                    pass
        elif event_id == 359:  # TTSEnded
            self.conversation_count += 1
            print(f"\n[已完成 {self.conversation_count}/2 轮对话]\n")
        elif event_id == 450:  # ASRInfo
            print("🎤 检测到您开始说话...")
        elif event_id == 451:  # ASRResponse
            results = payload.get('results', [])
            for r in results:
                text = r.get('text', '')
                if text and not r.get('is_interim', False):
                    print(f"您说: {text}")
        elif event_id == 459:  # ASREnded
            print("✓ 识别完成")
        elif event_id == 550:  # ChatResponse
            content = payload.get('content', '')
            if content:
                print(f"🤖 {content}")
        elif event_id == 599:  # DialogCommonError
            print(f"✗ 错误: {payload.get('message', '')}")
        else:
            if event_id:
                print(f"[事件 {event_id}]")
    
    def on_error(self, ws, error):
        print(f"✗ WebSocket错误: {error}")
    
    def on_close(self, ws, *args):
        print("连接已关闭")
        self.connected = False
        self.session_started = False
    
    def connect(self):
        headers = {
            "X-Api-App-ID": APP_ID,
            "X-Api-Access-Key": ACCESS_KEY,
            "X-Api-Resource-Id": RESOURCE_ID,
            "X-Api-App-Key": APP_KEY,
            "X-Api-Connect-Id": self.connect_id
        }
        
        self.ws = websocket.WebSocketApp(
            WS_URL,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.run_forever()
    
    def init_audio(self):
        """初始化音频输入输出"""
        self.audio_input = pyaudio.PyAudio()
        self.audio_output = pyaudio.PyAudio()
        
        # 输入流
        self.input_stream = self.audio_input.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        
        # 输出流
        self.output_stream = self.audio_output.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=TTS_SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK
        )
        print("✓ 音频设备已初始化")
    
    def cleanup_audio(self):
        """清理音频资源"""
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        if self.audio_input:
            self.audio_input.terminate()
        if self.audio_output:
            self.audio_output.terminate()
    
    def start_dialog(self, max_rounds=2):
        """开始实时对话"""
        # 初始化音频
        self.init_audio()
        
        # 等待会话启动
        print("等待会话启动...")
        timeout = 10
        while not self.session_started and timeout > 0:
            time.sleep(0.5)
            timeout -= 0.5
        
        if not self.session_started:
            print("✗ 会话启动失败")
            return
        
        print(f"\n{'='*50}")
        print(f"开始实时对话（将进行 {max_rounds} 轮）")
        print("请对着麦克风说话...")
        print(f"{'='*50}\n")
        
        # 音频输入线程
        def audio_input_loop():
            while self.session_started and self.conversation_count < max_rounds:
                try:
                    audio_data = self.input_stream.read(CHUNK, exception_on_overflow=False)
                    if self.session_started:
                        msg = encode_audio(self.session_id, audio_data)
                        self.ws.send(msg, websocket.ABNF.OPCODE_BINARY)
                    time.sleep(0.02)
                except:
                    break
        
        audio_thread = threading.Thread(target=audio_input_loop, daemon=True)
        audio_thread.start()
        
        # 等待对话完成
        while self.conversation_count < max_rounds and self.session_started:
            time.sleep(0.5)
        
        print(f"\n✓ 已完成 {self.conversation_count} 轮对话")
        
        # 结束会话
        if self.session_started:
            msg = encode_event(102, session_id=self.session_id, payload={})
            self.ws.send(msg, websocket.ABNF.OPCODE_BINARY)
            time.sleep(0.5)
        
        self.cleanup_audio()


# ==================== 主程序 ====================

def main():
    print("="*50)
    print("豆包实时语音对话 - 简化版")
    print("="*50)
    print(f"模型: {MODEL_VERSION}, 音色: {SPEAKER}\n")
    
    client = SimpleDialogClient()
    
    # WebSocket线程
    ws_thread = threading.Thread(target=client.connect, daemon=True)
    ws_thread.start()
    
    time.sleep(2)
    
    if not client.connected:
        print("✗ 连接失败")
        return
    
    # 开始对话
    try:
        client.start_dialog(max_rounds=2)
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        if client.ws:
            client.ws.close()
        print("\n程序结束")


if __name__ == "__main__":
    main()

