import time

from kaggle_environments import make
from kaggle_environments.utils import structify

import utils
from luxbot.agent import agent  # CONFIG - MANUALLY IMPORT BOT

# from bots.v40f import agent  # CONFIG - MANUALLY IMPORT BOT
# CONFIG - REPLAY AND CORRESPONDING ID
REPLAY_LIVE = True

if REPLAY_LIVE:
    file_replay_json = utils.file_run_replay_json
else:
    paths = utils.pathdl.glob('*.json')
    file_replay_json = max(paths, key=lambda p: p.stat().st_ctime)

render_kwargs = {
    'mode': 'html',
    'width': 1200,
    'height': 800,
}


def replay_match(path, step=0):
    """Replay game to a specific step - necessary for recreating stateful values."""
    match = utils.read_json(path)
    # env = make("halite", configuration=match['configuration'], steps=match['steps'])
    env = make("lux_ai_2021", configuration={"seed": 562124210, "loglevel": 2, "annotations": True}, debug=True)
    steps = env.run([agent, "simple_agent"])
    if 'TeamNames' not in match['info']:
        myid = 0
    else:
        myid = [pid for pid, name in enumerate(match['info']['TeamNames']) if name == "Ready Salted"][0]
    config = env.configuration
    # env already done - can write out full replay
    t = env.render(**render_kwargs)
    utils.write_html(t, 'live_replay.html')
    # If agent carries state across turns, need to run through all steps, or can directly index into a step otherwise
    # check that we are correct player
    # print('My Id: ', board.current_player_id, board.current_player)
    print(f'Running for:\n\t{path}\n\t{agent.__module__}\n\tID = {myid}\n')
    for step in range(360):
        state = match['steps'][step][0]  # list of length 1 for each step
        obs = state['observation']  # these are observations at this step
        obs['player'] = myid  # change the player to the one we want to inspect
        obs = structify(obs)  # turn the dict's into structures with attributes
        icon = '\\|/-'[(obs.step+1) % 4]
        t0 = time.time()
        ret = agent(obs, config)
        act_time = time.time() - t0
        print(f'{icon} step+1: {obs.step +1} StepTime:{round(act_time,2)}', end="\r", flush=True)


if __name__ == '__main__':
    replay_match(file_replay_json)
