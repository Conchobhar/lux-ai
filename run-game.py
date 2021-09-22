import utils
from kaggle_environments import make
from luxbot.agent import agent

TIMEOUT = 0
if TIMEOUT == 0:
    print('Timeout set to 0.')
env = make("lux_ai_2021", debug=True,
           configuration={
               "seed": 562124210, "loglevel": 2, "annotations": True, "actTimeout": TIMEOUT},)
steps = env.run([agent, "simple_agent"])
render_kwargs = {
    'width': 1200,
    'height': 800,
}

if __name__ == '__main__':
    run_html = env.render(mode = 'html', **render_kwargs)
    run_json = env.render(mode = 'json', **render_kwargs)
    utils.write_html(run_html, utils.file_run_replay_html)
    utils.write_json(run_json, utils.file_run_replay_json)
