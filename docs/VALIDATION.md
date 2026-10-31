# 验证记录 · 2026-11-01

平台：当前 Windows 工作区；主环境 Python 3.11.16 / PySide6 6.12.0。测试未使用用户真实录音。

## 已通过

`tests/test_toolbox.py`：7 个测试方法，包含 28 项基础工具的逐项子测试，以及额外的流程、导出和生命周期断言。

- 基础修复、均衡、动态、剪辑、变速 / 变调、频谱和信号分析均实际调用 FFmpeg 或信号算法。
- 轻量去噪、口播流程、自定义处理链、多素材拼接。
- WAV / FLAC / MP3 / AAC / Ogg / ZIP 导出；无确认前不写入导出目录；拒绝覆盖原文件；已有目标需要明确允许覆盖。
- 取消导出删除临时文件；异常参数与无效选区被拒绝。
- 相同输入 / 参数复用会话缓存；只导出一条分离音轨不会误标记全部音轨已保存。
- 多音轨视频选择、MKV 音轨替换、变更时间轴结果拒绝直接替换。
- 活跃会话锁保护、异常退出遗留清理、正常关闭删除临时文件，保留原文件与明确导出文件。

`tests/gui_toolbox.py`：真实 Qt 窗口、信号、工作线程、播放器与导出动作。

- 37 项功能均可打开对应设置；功能面板分类、搜索和选择正常。
- 三秒选区预览、播放位置推进、A/B 切换、参数修改使导出暂时失效。
- 完整处理、应用下一步、撤销与重做。
- 实际打开导出对话框，经测试选择保存路径后创建一个 WAV 文件，没有额外音频输出。
- 1340×860、1100×740 窗口截图已检查，修复了暗色系统配色和 Qt 无按钮数字框的显示问题。
- 关闭后临时会话目录不存在，原文件与明确导出文件仍然存在。

## 实际 AI 推理

使用 Windows SAPI 生成英文测试语音，取四秒片段。结果检查有效采样、轨道清单和非空识别，不代表主观音质排名。

| 功能 | 测试模型 | 结果 |
|---|---|---|
| AI 去噪 | DeepFilterNet3 | 有效音频输出 |
| 去混响 | Reverb_HQ_By_FoxJoy.onnx | No Reverb 音轨输出 |
| 人声分离 | UVR-MDX-NET-Inst_HQ_3.onnx | Vocals + Instrumental 输出 |
| 乐器分轨 | htdemucs.yaml | Bass / Drums / Other / Vocals 四轨输出 |
| 语音活动 | Silero VAD ONNX | 语音区间输出 |
| 转写 | faster-whisper Tiny | 带时间戳英文转写输出 |
| 转写 | faster-whisper Small | 带时间戳英文转写输出 |

官方 Hugging Face 下载连接曾超时。已显式使用 HF-Mirror 下载公开 Whisper 权重并完成推理；程序提供下载源选择和本地目录输入，优先使用已有缓存，未关闭 TLS 校验。

## 尚未验证 / 不承诺

- MelBand / BS RoFormer 两个候选模型、HTDemucs 六轨、Whisper Large-v3 / Turbo：有实际引擎调用路径，但未在本轮下载和运行。
- GPU 推理、超长录音压力测试、真实中文口播和复杂背景音乐的听感评估尚未完成。
- 本版不包含实时 AEC、目标说话人提取或身份识别；没有为这些能力创建不可用工具卡片。
- 波形和统计是信号描述；测试不生成“音质提升百分比”或模型优劣排名。

## 复现

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_toolbox.py -v
.venv/Scripts/python.exe -u tests/gui_toolbox.py
.venv/Scripts/python.exe -u tests/ai_toolbox.py denoise dereverb vocals stems
.venv/Scripts/python.exe -u tests/ai_toolbox.py vad
.venv/Scripts/python.exe -u tests/ai_toolbox.py transcribe --speech-model small
```

测试音频位于系统临时目录并在结束时清理。文档目录仅保留验证摘要、机器可读测试结果和界面截图。
