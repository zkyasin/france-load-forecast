from importlib.metadata import version


def test_package_is_installed() -> None:
    assert version("france-load-forecast") == "0.0.0"
