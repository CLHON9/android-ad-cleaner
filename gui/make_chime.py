"""生成客户端提示音 gui/web/chime.wav：两个柔和的音（E5 → A5，上行四度），总长不到 1 秒。
执行完成、暂停生效、需要机主解锁时播放。改音色改这里，重新运行：python3 gui/make_chime.py
只用标准库；44.1 kHz、16 位、单声道。"""
import math
import struct
import wave
from pathlib import Path

RATE = 44100
PEAK = 0.28             # 约 -11 dBFS：系统音量正常时听得清，不刺耳
NOTES = ((0.00, 659.26, 1.0, 0.09),    # (开始秒, 频率, 相对音量, 衰减秒)：E5，收得快，和第二个音分开
         (0.16, 880.00, 0.9, 0.22))    # A5，稍轻、留得长，尾音柔
LENGTH = 0.85
ATTACK = 0.008          # 起音 8 毫秒：去掉「咔」声，又不至于发闷


def note(t, freq, decay):
    if t < 0:
        return 0.0
    attack = 0.5 - 0.5 * math.cos(math.pi * min(t / ATTACK, 1.0))
    body = math.exp(-t / decay)
    shine = 0.10 * math.exp(-t / 0.06)          # 二次泛音很快退掉，只留一点木琴似的亮
    return attack * (body * math.sin(2 * math.pi * freq * t) + shine * math.sin(4 * math.pi * freq * t))


def render():
    n = int(RATE * LENGTH)
    raw = [sum(gain * note(i / RATE - start, freq, decay) for start, freq, gain, decay in NOTES) for i in range(n)]
    for i in range(int(RATE * 0.12)):           # 结尾 120 毫秒淡出到 0
        raw[n - 1 - i] *= i / (RATE * 0.12)
    top = max(abs(x) for x in raw)
    return [x / top * PEAK for x in raw]


def main():
    out = Path(__file__).resolve().parent / "web" / "chime.wav"
    samples = render()
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", round(x * 32767)) for x in samples))
    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
    print(f"{out}  {len(samples) / RATE:.2f} 秒  峰值 {20 * math.log10(max(abs(x) for x in samples)):.1f} dBFS"
          f"  RMS {20 * math.log10(rms):.1f} dBFS  {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
