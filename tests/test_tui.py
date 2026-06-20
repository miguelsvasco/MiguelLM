import array

from miguel_lm.tui import face_fits, mouth_envelope


def _pcm(values):
    return array.array("h", values).tobytes()


def test_mouth_envelope_empty_without_audio():
    assert mouth_envelope(b"", 24000) == []
    assert mouth_envelope(_pcm([100, -100]), 0) == []


def test_face_fits_only_when_both_panes_have_room():
    # Face pane 46 wide, chat needs at least 36: cutoff at 82 columns.
    assert face_fits(82, 46, 36) is True
    assert face_fits(81, 46, 36) is False
    # A wider avatar pane pushes the cutoff out.
    assert face_fits(82, 60, 36) is False


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
