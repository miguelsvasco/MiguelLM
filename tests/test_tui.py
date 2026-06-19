import array

from miguel_lm.tui import mouth_envelope


def _pcm(values):
    return array.array("h", values).tobytes()


def test_mouth_envelope_empty_without_audio():
    assert mouth_envelope(b"", 24000) == []
    assert mouth_envelope(_pcm([100, -100]), 0) == []


def test_mouth_envelope_tracks_loud_then_quiet():
    sr = 24000
    loud = [12000 if i % 2 else -12000 for i in range(int(sr * 0.24))]
    quiet = [0] * int(sr * 0.24)
    env = mouth_envelope(_pcm(loud + quiet), sr)
    assert env, "expected envelope samples"
    # Peak-normalized: loud windows near 1.0, trailing silence at 0.0.
    assert max(env) == 1.0
    assert env[0] > 0.5
    assert env[-1] == 0.0
