"""データの置き場所を、環境変数か設定ファイルから読む。

優先順: 環境変数 > 設定ファイル（KIYO_CONFIG で指定、なければリポジトリ直下の config.toml）。
  KIYO_DATA_DIR         本文の置き場所（bodies/<誌>/<ID>.txt）
  KIYO_CORRECTIONS_DIR  補正入力の置き場所（<誌>/<ID>.json）。省略時は KIYO_DATA_DIR/corrections
"""
import os, tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYS = {'data_dir': 'KIYO_DATA_DIR', 'corrections_dir': 'KIYO_CORRECTIONS_DIR'}


def _file():
    p = Path(os.environ.get('KIYO_CONFIG', REPO / 'config.toml'))
    if p.exists():
        with p.open('rb') as f:
            return tomllib.load(f).get('paths', {})
    return {}


def get(name):
    env = os.environ.get(KEYS[name])
    if env:
        return Path(env).expanduser()
    v = _file().get(name)
    if v:
        return Path(v).expanduser()
    if name == 'data_dir':
        raise SystemExit('KIYO_DATA_DIR か config.toml の [paths] data_dir を指定してください')
    return get('data_dir') / 'corrections'


def body_path(rel):
    """マニフェストの「本文ファイル」列（data_dir からの相対パス）を実際のパスにする。"""
    return get('data_dir') / rel


def corrections_path(journal, pid):
    return get('corrections_dir') / journal / f'{pid}.json'
