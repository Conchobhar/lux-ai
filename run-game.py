import cProfile
import utils
from kaggle_environments import make
from luxbot.agent import agent as live_agent
from bots.v3_1.agent import agent as previous_agent

TIMEOUT = 0
if TIMEOUT == 0:
    print('Timeout set to 0.')
SEED = 139762171  # Small map - corner trees
env = make("lux_ai_2021", debug=True,
           configuration={
               "seed": SEED, "loglevel": 2, "annotations": True, "actTimeout": TIMEOUT},)
steps = env.run([live_agent, previous_agent])
render_kwargs = {
    'width': 1200,
    'height': 800,
}


def main():
    run_html = env.render(mode = 'html', **render_kwargs)
    run_json = env.render(mode = 'json', **render_kwargs)
    utils.write_html(run_html, utils.file_run_replay_html)
    utils.write_json(run_json, utils.file_run_replay_json)


if __name__ == '__main__':
    main()
