# Root conftest for the pytest session.
#
# The src-layout package (`chronosync`) and the top-level `synthetic` package
# are made importable through `[tool.pytest.ini_options] pythonpath` in
# pyproject.toml. This file exists so that pytest treats the repository root
# as the rootdir and picks up that configuration consistently.
