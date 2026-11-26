import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path_factory, monkeypatch):
    """Tests sehen nie die echten Vorlagen unter ~/.config."""
    config = tmp_path_factory.mktemp("config")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    return config
