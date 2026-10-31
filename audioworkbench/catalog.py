"""One registry drives navigation, settings, validation and processing."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    key: str
    title: str
    default: object
    kind: str = 'number'
    low: float = 0
    high: float = 100
    step: float = 1
    options: tuple = ()
    unit: str = ''


def num(key, title, default, low, high, step=1, unit=''):
    return Param(key, title, default, 'number', low, high, step, unit=unit)


def choice(key, title, options, default=None):
    return Param(key, title, default if default is not None else options[0][1], 'choice', options=tuple(options))


def flag(key, title, default=False):
    return Param(key, title, default, 'bool')


@dataclass(frozen=True)
class Tool:
    id: str
    title: str
    group: str
    icon: str
    description: str
    engine: str
    params: tuple = ()
    changes_time: bool = False
    analysis: bool = False

    def defaults(self):
        return {p.key: p.default for p in self.params}


V_MODELS = [('MDX HQ 3 · 已验证', 'UVR-MDX-NET-Inst_HQ_3.onnx'),
            ('MelBand RoFormer · 高质量候选 / 按需下载', 'vocals_mel_band_roformer.ckpt')]
R_MODELS = [('Reverb HQ · 已验证', 'Reverb_HQ_By_FoxJoy.onnx'),
            ('BS RoFormer · 高质量候选 / 按需下载', 'deverb_bs_roformer_8_384dim_10depth.ckpt')]
DEVICE = choice('device', '推理设备', [('CPU · 通用', 'cpu'), ('CUDA · NVIDIA GPU', 'cuda')])
STRENGTH = num('strength', '处理强度', 55, 0, 100, 1, '%')
DENOISE = choice('engine', '去噪引擎', [('DeepFilterNet3 · AI', 'deepfilter'), ('频谱去噪 · 轻量', 'spectral')])
LUFS = num('lufs', '目标响度', -16, -30, -9, 1, ' LUFS')
TOOLS = [
    Tool('podcast', '口播优化', '自动流程', 'mic', '去噪、去混响、齿音和动态，一次完成口播清理。', 'DeepFilterNet · FFmpeg',
         (DENOISE, STRENGTH, flag('dereverb', '先减轻混响'), flag('polish', '均衡 / 齿音 / 压缩', True), LUFS)),
    Tool('chain', '自定义处理链', '自动流程', 'workflow', '添加并排序工具，整条处理链只生成临时结果。', '组合引擎'),
    Tool('denoise', '语音去噪', '清理修复', 'audio-lines', '减少持续底噪，保留人声细节。', 'DeepFilterNet · noisereduce', (DENOISE, STRENGTH)),
    Tool('dereverb', '去混响', '清理修复', 'waves', '减轻房间拖尾和空旷感；不等同于通话 AEC。', 'Audio Separator',
         (choice('model', '去混响模型', R_MODELS), DEVICE)),
    Tool('hum', '电流嗡声', '清理修复', 'zap-off', '抑制 50 / 60 Hz 电源噪声及其谐波。', 'FFmpeg bandreject',
         (choice('frequency', '电源频率', [('50 Hz', 50), ('60 Hz', 60)]), num('harmonics', '谐波级数', 4, 1, 8), num('q', '陷波 Q 值', 20, 2, 60))),
    Tool('rumble', '低频风噪', '清理修复', 'wind', '高通抑制低频隆隆声；无法恢复被风噪遮蔽的语音。', 'FFmpeg highpass',
         (num('cutoff', '截止频率', 90, 20, 400, 5, ' Hz'),)),
    Tool('declick', '咔嗒修复', '清理修复', 'sparkles', '修复短促脉冲、咔嗒与局部爆点。', 'FFmpeg adeclick',
         (num('threshold', '检测阈值', 2, 1, 10, .1),)),
    Tool('declip', '削波修复', '清理修复', 'scan-line', '对过载削波进行插值修复，不能保证还原原声。', 'FFmpeg adeclip',
         (num('threshold', '修复阈值', 10, 1, 100, 1),)),
    Tool('dc', '直流偏移', '清理修复', 'move-horizontal', '移除波形直流偏移与极低频漂移。', 'FFmpeg highpass'),
    Tool('vocals', '人声与伴奏', '音源分离', 'users', '分别生成可试听的人声与伴奏音轨。', 'Audio Separator',
         (choice('model', '分离模型', V_MODELS), DEVICE)),
    Tool('stems', '乐器分轨', '音源分离', 'music-2', '分离人声、鼓、贝斯及其他乐器。', 'Audio Separator · Demucs',
         (choice('model', '分轨模型', [('HTDemucs · 四轨 / 按需下载', 'htdemucs.yaml'), ('HTDemucs 6s · 六轨 / 按需下载', 'htdemucs_6s.yaml')]), DEVICE)),
    Tool('eq', '均衡器', '音色动态', 'sliders-horizontal', '三段可调频率的参数均衡器。', 'FFmpeg equalizer',
         (num('low_hz', '低频中心', 120, 30, 500, 10, ' Hz'), num('low_gain', '低频增益', 0, -18, 18, .5, ' dB'),
          num('mid_hz', '中频中心', 1200, 200, 6000, 50, ' Hz'), num('mid_gain', '中频增益', 0, -18, 18, .5, ' dB'),
          num('high_hz', '高频中心', 6000, 2000, 16000, 100, ' Hz'), num('high_gain', '高频增益', 0, -18, 18, .5, ' dB'))),
    Tool('filters', '高低通滤波', '音色动态', 'filter', '按频率范围保留声音。', 'FFmpeg biquad',
         (num('highpass', '高通截止', 70, 10, 4000, 10, ' Hz'), num('lowpass', '低通截止', 16000, 500, 22000, 100, ' Hz'))),
    Tool('deess', '齿音控制', '音色动态', 'speech', '减轻尖锐的 s、sh 等高频齿音。', 'FFmpeg deesser', (num('amount', '抑制强度', 20, 0, 100, 1, '%'),)),
    Tool('compress', '动态压缩', '音色动态', 'minimize-2', '缩小音量差异，让说话轻重更均匀。', 'FFmpeg acompressor',
         (num('threshold', '阈值', -18, -60, 0, 1, ' dB'), num('ratio', '压缩比', 3, 1, 20, .5),
          num('attack', '启动', 15, .1, 200, .1, ' ms'), num('release', '释放', 150, 10, 2000, 10, ' ms'), num('makeup', '补偿增益', 0, 0, 18, .5, ' dB'))),
    Tool('limit', '峰值限幅', '音色动态', 'panel-top', '限制采样峰值，防止进一步过载。', 'FFmpeg alimiter', (num('ceiling', '采样峰值上限', -1.5, -12, 0, .1, ' dBFS'),)),
    Tool('gate', '噪声门', '音色动态', 'door-open', '在小音量段衰减底噪，过强会切断尾音。', 'FFmpeg agate',
         (num('threshold', '开门阈值', -40, -80, -6, 1, ' dB'), num('ratio', '衰减比', 4, 1, 20), num('release', '释放', 180, 10, 2000, 10, ' ms'))),
    Tool('loudness', '响度标准化', '音色动态', 'gauge', '两遍测量并调整整体响度。', 'FFmpeg loudnorm', (LUFS, num('peak', '真峰值目标', -1.5, -9, 0, .1, ' dBTP'))),
    Tool('gain', '音量增益', '音色动态', 'volume-2', '按分贝调整音量，可选峰值保护。', 'FFmpeg volume',
         (num('gain', '增益', 0, -36, 24, .5, ' dB'), flag('protect', '限制峰值到 -1 dBFS', True))),
    Tool('stereo', '立体声宽度', '音色动态', 'headphones', '调整中置与侧向声的比例和左右平衡。', 'FFmpeg stereotools',
         (num('width', '宽度', 100, 0, 200, 5, '%'), num('balance', '平衡 · 左 / 右', 0, -100, 100, 5))),
    Tool('crop', '裁剪片段', '剪辑时间', 'scissors', '保留工作区选定的时间范围。', 'FFmpeg atrim', changes_time=True),
    Tool('split', '等长分割', '剪辑时间', 'columns-3', '按指定时长拆分为多段音轨。', 'FFmpeg atrim',
         (num('seconds', '每段长度', 30, 1, 3600, 1, ' 秒'),), True),
    Tool('concat', '音频拼接', '剪辑时间', 'combine', '按左侧素材顺序拼接，每段先统一为 48 kHz 双声道。', 'FFmpeg concat',
         (num('gap', '片段间静音', 0, 0, 10, .1, ' 秒'),), True),
    Tool('fade', '淡入淡出', '剪辑时间', 'triangle', '柔化音频开头与结尾。', 'FFmpeg afade',
         (num('fade_in', '淡入', .3, 0, 20, .1, ' 秒'), num('fade_out', '淡出', .5, 0, 20, .1, ' 秒'))),
    Tool('trim', '首尾静音', '剪辑时间', 'between-horizontal-start', '仅裁剪开头和结尾的低音量段。', 'FFmpeg silenceremove',
         (num('threshold', '静音阈值', -45, -80, -15, 1, ' dB'),), True),
    Tool('pauses', '缩短停顿', '剪辑时间', 'fold-horizontal', '检测长静音并保留指定长度；会改变时间轴。', 'FFmpeg silencedetect · NumPy',
         (num('threshold', '静音阈值', -40, -80, -15, 1, ' dB'), num('minimum', '长停顿阈值', .8, .2, 10, .1, ' 秒'), num('keep', '保留长度', .3, 0, 3, .05, ' 秒')), True),
    Tool('speed', '变速不变调', '剪辑时间', 'fast-forward', '改变播放速度，保留音高。', 'FFmpeg · Rubber Band',
         (num('speed', '速度倍率', 1.1, .25, 4, .05, ' ×'),), True),
    Tool('pitch', '变调不变速', '剪辑时间', 'arrow-up-down', '按半音升降音高，保留时长。', 'FFmpeg · Rubber Band',
         (num('semitones', '音高偏移', 0, -12, 12, .5, ' 半音'),)),
    Tool('reverse', '倒放', '剪辑时间', 'undo-2', '反转整个选定片段。', 'FFmpeg areverse'),
    Tool('channels', '声道处理', '格式交付', 'split', '选择左声道、右声道、合并单声道或交换左右。', 'FFmpeg pan',
         (choice('mode', '声道模式', [('合并为单声道', 'mono'), ('仅左声道', 'left'), ('仅右声道', 'right'), ('交换左右', 'swap'), ('反转右声道相位', 'invert')]),)),
    Tool('convert', '格式转换', '格式交付', 'file-audio', '生成临时音频，在确认导出时选择格式、采样率和位深。', 'FFmpeg'),
    Tool('extract', '视频音轨提取', '格式交付', 'film', '可选择视频中的音轨，导出为独立音频。', 'FFmpeg'),
    Tool('analysis', '响度与峰值', '分析字幕', 'chart-no-axes-combined', '测量 LUFS、真峰值、动态范围、削波与静音比例。', 'FFmpeg EBU R128 · NumPy', analysis=True),
    Tool('spectrum', '频谱图', '分析字幕', 'chart-area', '查看声音随时间变化的频率分布。', 'FFmpeg showspectrumpic', analysis=True),
    Tool('silence', '静音检测', '分析字幕', 'scan', '列出符合阈值的静音区间。', 'FFmpeg silencedetect',
         (num('threshold', '静音阈值', -40, -80, -15, 1, ' dB'), num('minimum', '最短静音', .4, .1, 10, .1, ' 秒')), analysis=True),
    Tool('vad', '语音活动检测', '分析字幕', 'scan-face', '用 Silero VAD 标记人声片段，不识别说话人身份。', 'Silero VAD · ONNX',
         (num('threshold', '检测阈值', .5, .1, .9, .05),), analysis=True),
    Tool('transcribe', '转写与字幕', '分析字幕', 'captions', '离线转写、编辑时间戳和文本，确认后导出 SRT / TXT。', 'faster-whisper',
         (choice('model', '识别模型', [('Tiny · 快速预览', 'tiny'), ('Small · 均衡', 'small'), ('Large v3 · 高质量', 'large-v3'), ('Large v3 Turbo · 速度优先', 'turbo')], 'small'),
          choice('language', '语言', [('自动检测', 'auto'), ('中文', 'zh'), ('英语', 'en'), ('日语', 'ja'), ('韩语', 'ko')]), DEVICE,
          flag('translate', '翻译为英语'), flag('vad', '跳过非语音区域', True),
          choice('download_source','模型下载源',[('Hugging Face · 官方','official'),('HF-Mirror · 第三方镜像','mirror')]),
          Param('model_path','本地 CTranslate2 模型目录（可选）','','path')), analysis=True),
]
BY_ID = {t.id: t for t in TOOLS}
GROUPS = list(dict.fromkeys(t.group for t in TOOLS))
COMMON = ['podcast', 'denoise', 'dereverb', 'vocals', 'loudness', 'transcribe']


def validate(tool_id, values):
    tool = BY_ID[tool_id]
    result = tool.defaults()
    unknown = set(values) - set(result) - ({'steps'} if tool_id == 'chain' else set())
    if unknown: raise ValueError(f'未知参数：{unknown}')
    result.update(values)
    for p in tool.params:
        v = result[p.key]
        if p.kind == 'number':
            import math
            if not isinstance(v, (int, float)) or not math.isfinite(v) or not p.low <= v <= p.high:
                raise ValueError(f'{p.title}超出范围')
        elif p.kind == 'choice' and v not in [x[1] for x in p.options]: raise ValueError(f'{p.title}无效')
        elif p.kind == 'bool' and type(v) is not bool: raise ValueError(f'{p.title}无效')
        elif p.kind == 'path' and not isinstance(v,str): raise ValueError(f'{p.title}无效')
    return result
