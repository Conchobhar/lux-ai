"""
- Persist current working directory of bot as a version under bots/ for reference and replaying bots locally.
- Create tar.gz for submission.
"""
import os
import sys
import shutil
import tarfile
from pathlib import Path
import logging
import argparse

BOT_NAME = 'luxbot'

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger()
root_path = Path(__file__).parents[0]
parser = argparse.ArgumentParser(description='Imortalize current state of bot and package for submission.')
parser.add_argument('version', metavar='v', type=str,
                    help='version id to identify. This will be used to create a module under bots/')
args = parser.parse_args()

version_path = root_path / 'bots' / args.version
source_path = root_path / BOT_NAME


if __name__ == '__main__':
    if os.path.isdir(version_path):
        i = input(f"Warning - Bot version `{args.version}` already exists. Overwrite? Y/N: ")
        if i != 'Y':
            logger.info("Exiting.")
            exit()
        else:
            logger.info('Overwriting old version...')
            shutil.rmtree(version_path)
    shutil.copytree(source_path, version_path)
    with tarfile.open(root_path / 'submission.tar.gz', "w:gz") as tar:
        tar.add(version_path, arcname='.')
