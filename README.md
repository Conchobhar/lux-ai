# Lux AI Challenge
https://www.kaggle.com/c/lux-ai-2021/

Contains development enviornment for building bots.

The current `luxbot` contains the 
simple [starter kit bot](https://github.com/Lux-AI-Challenge/Lux-Design-2021/tree/master/kits/python) wiht
some slight refactoring.

Paths defined in `utils/base.py` need configured to the users' environment.

# Structure 
`luxbot` - Actively developed bot

`bots` - Space for persisting luxbot versions

`utils` -  Code used by scripts

`replays_active` - Stores the last replay saved. Drag this into a browser to view

`create-bot.py` - Persist current version of `luxbot` and package as a submission.tar.gz :
```bash
$ python ./create-bot.py version_id
```

`run-game.py` -  Run bots against each other. Configuration done in script

`replay-game.py` - Replay a previous game from its json. Configuration done in script

# Debugging
The agent (live or in a replay) should halt at set breakpoints. However
`kaggle_environments/agent.py` will play an agent under the following IO redirect context and try/except block:
```python
with StringIO() as out_buffer, StringIO() as err_buffer, redirect_stdout(out_buffer), redirect_stderr(err_buffer):
    try:
        start = perf_counter()
        action = self.agent(*args)
    except Exception as e:
        traceback.print_exc(file=err_buffer)
        action = e
    ...
```
Which will also redirect for example the output from PyCharms debug console. For the purpose of local debugging you can 
disable the redirect and exception catch with this edit in the source module file:
```python
with StringIO() as out_buffer, StringIO() as err_buffer: #, redirect_stdout(out_buffer), redirect_stderr(err_buffer):
    # try:
    start = perf_counter()
    action = self.agent(*args)
    # except Exception as e:
    #     traceback.print_exc(file=err_buffer)
    #     action = e
    # Allow up to 1k log characters per step which is ~1MB per 600 step episode
```
