#!/usr/bin/env python3

try:
    import tomllib
except ImportError:
    tomllib = None


def fallback_version(raw):
    in_poetry_section = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped == '[tool.poetry]':
            in_poetry_section = True
            continue
        if in_poetry_section and stripped.startswith('['):
            break
        if in_poetry_section and stripped.startswith('version'):
            return stripped.split('=', 1)[1].strip().strip('"\'')
    raise RuntimeError('Could not find tool.poetry.version')


with open('pyproject.toml', 'rb') as f:
    raw_bytes = f.read()

if tomllib:
    cfg = tomllib.loads(raw_bytes.decode())
    print(cfg['tool']['poetry']['version'])
else:
    try:
        import toml
        cfg = toml.loads(raw_bytes.decode())
        print(cfg['tool']['poetry']['version'])
    except ImportError:
        print(fallback_version(raw_bytes.decode()))
