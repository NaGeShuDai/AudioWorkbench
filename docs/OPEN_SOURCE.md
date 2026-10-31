# 开源方案与模型选型

版本：AudioWorkbench 工具箱，2026-11-01。以真实可运行、适合离线文件处理、可切换模型为选型标准，不宣称某个模型在所有素材上最好。

| 功能 | 选定实现 | 原因 / 模型 |
|---|---|---|
| 原生桌面 | PySide6 / Qt | 原生布局、播放器、工作线程、HiDPI SVG |
| 基础音频、滤镜、封装 | FFmpeg（imageio-ffmpeg 随附构建） | 已实际检查本机构建的滤镜和编码器 |
| 变速 / 变调 | FFmpeg rubberband 滤镜 | 本机构建包含 Rubber Band，不用改变采样率假装独立变调 |
| AI 去噪 | DeepFilterNet 0.5.6 / DeepFilterNet3 | 已有 Windows 隔离环境；适合语音去噪 |
| 轻量去噪 | noisereduce 3.0.3 | 不下载权重，分块处理 |
| 人声 / 伴奏 | Audio Separator 0.48.0 | 默认 UVR-MDX-NET-Inst_HQ_3.onnx；输出两条音轨 |
| 人声分离高质量候选 | Audio Separator / MelBand RoFormer | vocals_mel_band_roformer.ckpt；按需下载，非默认性能承诺 |
| 去混响 | Audio Separator | 默认 Reverb_HQ_By_FoxJoy.onnx，明确选择 No Reverb 音轨 |
| 去混响候选 | Audio Separator / BS RoFormer | deverb_bs_roformer_8_384dim_10depth.ckpt；按需下载 |
| 乐器分轨 | Audio Separator / HTDemucs | htdemucs.yaml 四轨；可选 htdemucs_6s.yaml 六轨 |
| 转写 | faster-whisper 1.2.1 / CTranslate2 | Tiny、Small、Large-v3、Turbo；支持 CPU INT8、可选 CUDA FP16 |
| 人声区间 | faster-whisper 所集成的 Silero VAD ONNX | 无需额外安装另一套 torch 环境 |
| 统计与信号数组 | NumPy、SoundFile、SciPy | 浮点中间数据，采样有效性和长度检查 |
| 图标 | Lucide 0.468.0 | 统一线宽和青绿色，无需生成位图，缩放保持清晰 |

## 原始项目与文档

- https://github.com/Rikorose/DeepFilterNet
- https://github.com/nomadkaraoke/python-audio-separator
- https://github.com/facebookresearch/demucs
- https://github.com/SYSTRAN/faster-whisper
- https://github.com/snakers4/silero-vad
- https://github.com/timsainb/noisereduce
- https://ffmpeg.org/ffmpeg-filters.html
- https://breakfastquay.com/rubberband/
- https://doc.qt.io/qtforpython-6/
- https://github.com/lucide-icons/lucide/tree/0.468.0

## 模型管理与安装策略

主界面不导入 PyTorch，AI 工作进程在独立环境执行。DeepFilterNet 固定兼容的 torch / torchaudio 2.2.2；分离和语音环境各自安装，不互相覆盖依赖。当前安装的精确依赖见根目录 `*.lock.txt`。

默认使用 CPU。选择 CUDA 后如对应引擎没有 GPU 能力，会报错，不自动声称使用了 GPU。完整的 GPU 环境安装不在当前一键安装器中。

模型权重持久保留；输入音频和模型输出只进入系统临时会话。每个任务的模型配置和诊断日志也仅在临时会话内。官网下载失败时转写界面允许用户明确选择第三方镜像，或使用本地模型目录；不关闭 TLS 证书验证。

## 功能边界

- 去混响属于单文件处理；真正通话 AEC 通常需要播放参考音轨和实时设备链路。本版不混淆这两种能力。
- 低频风噪是高通抑制，不宣称能复原被严重风噪覆盖的细节。
- 削波修复是算法估计，不是原始信号恢复保证。
- 不直接引入 Resemble Enhance，避免当前原生 Windows 依赖不兼容造成默认流程不可用。
- 不直接引入需要受限模型访问的说话人识别 / diarization，也不冒充音源分离已经具备身份识别能力。
- 高质量模型候选保留可选入口；实际应使用同段真实素材进行响度匹配试听，考虑保真、残留、耗时和内存。

## 许可

代码库许可和具体模型权重许可分别适用。Lucide 上游许可随图标保留。FFmpeg 编译选项、Rubber Band、Qt 及模型的许可要求不能因本项目通过子进程调用而忽略。当前是本地开发工具，不提供未经许可审查的商业分发声明。
