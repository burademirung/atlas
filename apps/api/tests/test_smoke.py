import atlas_api


def test_package_exposes_version() -> None:
    assert isinstance(atlas_api.__version__, str)
    assert atlas_api.__version__
