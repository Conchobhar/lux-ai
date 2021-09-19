import os
import json
from pathlib import Path

# Configure me!
# pathroot = Path(f'{os.environ["USERPROFILE"]}') / 'PycharmProjects' / 'lux-ai'
pathroot = Path(__file__).parents[1]  # Root location of this project
pathdl = Path(f'{os.environ["USERPROFILE"]}') / 'Downloads'  # Download location of replays

file_run_replay_html = pathroot / 'replays_active' / 'run_replay.html'
file_live_replay_html = pathroot / 'replays_active' / 'live_replay.html'
file_run_replay_json = pathroot / 'replays_active' / 'run_replay.json'


def write_html(run_html, file):
    with open(file, 'w') as f:
        f.write(run_html)


def write_json(run_json, file):
    with open(file, 'w') as f:
        f.write(run_json)


def read_json(file):
    with open(file, 'r', encoding='utf-8') as f:
        j = json.loads(f.read())
    return j
