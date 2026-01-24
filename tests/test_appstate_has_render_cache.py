import core


def test_appstate_has_render_cache_default():
    st = core.AppState()
    assert isinstance(st.render_cache, dict)
    assert st.render_cache == {}
