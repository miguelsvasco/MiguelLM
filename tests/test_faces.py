from miguel_lm import faces


def test_face_renders_for_every_emotion():
    for emotion in faces.EMOTIONS:
        art = faces.render(emotion)
        assert isinstance(art, str) and art
        assert len(art.splitlines()) >= 5  # framed, multi-line


def test_speaking_toggles_mouth_open_and_closed():
    closed = faces.render("normal", frame=0, speaking=True)
    opened = faces.render("normal", frame=1, speaking=True)
    assert closed != opened


def test_unknown_emotion_falls_back_to_normal():
    assert faces.render("bogus-emotion") == faces.render("normal")
