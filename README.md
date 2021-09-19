# Lux AI Challenge
https://www.kaggle.com/c/lux-ai-2021/

Contains development enviornment for building bots. The current `luxbot` contains the 
simple starter kit bot.

Modify utils/base.py

# Structure 
`luxbot` - Actively developed bot

`bots` - Space for persisting bot versions

`utils` -  Code used by scripts

`create-bot.py` - Persist current version of `luxbot` and package as a submission.tar.gz :
```bash
$ python ./create-bot.py version_id
```

`run-game.py` -  Run bots against each other. Configuration done in script.

`replay-game.py` - Replay a previous game from its json. Configuration done in script.

# Debugging
The agent (live or in a replay) should halt at set breakpoints. However
`kaggle_environments/agent.py` will play an agent under the following IO redirect context:
```python
with StringIO() as out_buffer, StringIO() as err_buffer, redirect_stdout(out_buffer), redirect_stderr(err_buffer):
    ...
```
Which will also redirect for example the output from PyCharms debug console. For the purpose of local debugging you can 
disable the redirect with this edit of the context in the source module file:
```python
with StringIO() as out_buffer, StringIO() as err_buffer: #, redirect_stdout(out_buffer), redirect_stderr(err_buffer):
    ...
```

