import CryptoJS from 'crypto-js';

// --- 配置 ---
const API_HOST = 'iat.cn-huabei-1.xf-yun.com';
const API_PATH = '/v1';
const TARGET_SAMPLE_RATE = 16000;

export interface XunfeiASRConfig {
  appId: string;
  apiKey: string;
  apiSecret: string;
  onMessage: (text: string, isLast: boolean) => void;
  onError: (error: string) => void;
  onClose: () => void;
}

export class XunfeiRecorder {
  private config: XunfeiASRConfig;
  private socket: WebSocket | null = null;
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private scriptProcessor: ScriptProcessorNode | null = null;
  
  // --- State for frame management ---
  private isRecording = false;
  private frameStatus = 0; // 0 for first, 1 for intermediate, 2 for last
  private sequence = 1;

  constructor(config: XunfeiASRConfig) {
    this.config = config;
  }

  private getAuthorizationUrl(): string {
    const date = new Date().toUTCString();
    const signatureOrigin = `host: ${API_HOST}\ndate: ${date}\nGET ${API_PATH} HTTP/1.1`;
    const signature = CryptoJS.HmacSHA256(signatureOrigin, this.config.apiSecret).toString(CryptoJS.enc.Base64);
    
    const authorization = `api_key="${this.config.apiKey}", algorithm="hmac-sha256", headers="host date request-line", signature="${signature}"`;
    const encodedAuthorization = btoa(authorization);
    
    return `wss://${API_HOST}${API_PATH}?authorization=${encodedAuthorization}&date=${encodeURIComponent(date)}&host=${API_HOST}`;
  }
  
  public async start() {
    if (this.isRecording) return;
    
    this.frameStatus = 0;
    this.sequence = 1;

    const url = this.getAuthorizationUrl();
    this.socket = new WebSocket(url);

    this.socket.onopen = () => {
      console.log('Xunfei WebSocket connected.');
      this.startAudioCapture();
    };

    this.socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.code !== 0) {
            this.config.onError(`Server error: ${data.message} (code: ${data.code}, sid: ${data.sid})`);
            this.stop();
            return;
        }

        if (data.data && data.data.result) {
            const result = this.parseResult(data.data.result.text);
            this.config.onMessage(result.text, result.isLast);
        }
    };

    this.socket.onerror = (event) => {
      console.error('Xunfei WebSocket error:', event);
      this.config.onError('WebSocket connection error.');
      this.stop();
    };

    this.socket.onclose = (event: CloseEvent) => {
      console.log(`Xunfei WebSocket closed. Code: ${event.code}, Reason: ${event.reason}`);
      this.stop();
      this.config.onClose();
    };
  }

  public stop() {
    // Prevent multiple stop calls or stopping a non-started recorder
    if (!this.audioContext && !this.isRecording) return;

    this.isRecording = false;

    // Send the final frame if the connection is still open
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        const lastFrame = {
            header: { app_id: this.config.appId, status: 2 },
            payload: {
                audio: {
                    encoding: "raw",
                    sample_rate: 16000,
                    status: 2,
                    audio: ""
                }
            }
        };
        this.socket.send(JSON.stringify(lastFrame));
        console.log("Sent last frame.");
    }

    // Stop and clean up audio resources
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }
    if (this.scriptProcessor) {
      this.scriptProcessor.disconnect();
      this.scriptProcessor = null;
    }
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close();
      this.audioContext = null;
    }
  }

  private async startAudioCapture() {
    try {
        this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        this.audioContext = new AudioContext();
        
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        const bufferSize = 4096;
        
        this.scriptProcessor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);
        
        this.scriptProcessor.onaudioprocess = (e) => {
            if (!this.isRecording) return;
            const pcmData = this.processAudio(e.inputBuffer);
            this.sendAudio(pcmData);
        };
        
        source.connect(this.scriptProcessor);
        this.scriptProcessor.connect(this.audioContext.destination);
        
        this.isRecording = true;
        // Do NOT send the first frame here. Wait for actual audio data.
    } catch (error) {
        console.error("Error capturing audio: ", error);
        this.config.onError("无法访问麦克风，请检查权限。");
        this.stop();
    }
  }

  private processAudio(audioBuffer: AudioBuffer): Int16Array {
    const rawData = audioBuffer.getChannelData(0);
    const sourceSampleRate = this.audioContext?.sampleRate || 48000;
    
    // Resample
    const ratio = sourceSampleRate / TARGET_SAMPLE_RATE;
    const newLength = Math.round(rawData.length / ratio);
    const result = new Int16Array(newLength);
    let offsetResult = 0;
    let offsetBuffer = 0;

    while (offsetResult < newLength) {
        const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
        let accum = 0, count = 0;
        for (let i = offsetBuffer; i < nextOffsetBuffer && i < rawData.length; i++) {
            accum += rawData[i];
            count++;
        }
        // Convert to 16-bit PCM
        result[offsetResult] = Math.max(-1, Math.min(1, accum / count)) * 0x7FFF;
        offsetResult++;
        offsetBuffer = nextOffsetBuffer;
    }
    return result;
  }
  
  private sendAudio(pcmData: Int16Array) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;

    const audioBase64 = this.int16ArrayToBase64(pcmData);
    let frame = {};

    switch (this.frameStatus) {
        case 0: // First audio frame
            frame = {
                header: { app_id: this.config.appId, status: this.frameStatus },
                parameter: {
                    iat: {
                        domain: "slm",      // For multilingual models
                        language: "mul_cn",
                        accent: "mandarin",
                        eos: 5000,          // 5s of silence to end speech
                        vinfo: 1,           // Include VAD info in results
                        result: { encoding: "utf8", compress: "raw", format: "json" }
                    }
                },
                payload: {
                    audio: {
                        encoding: "raw", sample_rate: 16000, channels: 1, bit_depth: 16,
                        seq: this.sequence,
                        status: this.frameStatus,
                        audio: audioBase64,
                    }
                }
            };
            this.frameStatus = 1; // Transition to intermediate frames
            break;

        case 1: // Intermediate audio frames
            frame = {
                header: { app_id: this.config.appId, status: this.frameStatus },
                payload: {
                    audio: {
                        encoding: "raw",
                        sample_rate: 16000,
                        status: this.frameStatus,
                        audio: audioBase64,
                    }
                }
            };
            break;
    }
    
    this.socket.send(JSON.stringify(frame));
    this.sequence++;
  }

  private int16ArrayToBase64(buffer: Int16Array): string {
    let binary = '';
    for (let i = 0; i < buffer.length; i++) {
        const val = buffer[i];
        binary += String.fromCharCode(val & 0xFF, (val >> 8) & 0xFF);
    }
    return btoa(binary);
  }

  private parseResult(textBase64: string): { text: string, isLast: boolean } {
    const decoded = atob(textBase64);
    const result = JSON.parse(decoded);
    
    let text = "";
    result.ws.forEach((word: any) => {
        text += word.cw.map((char: any) => char.w).join('');
    });

    const isLast = result.ls; // ls segment indicates the last result of a sentence
    return { text, isLast };
  }
}