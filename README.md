# Lux AI Challenge
https://www.kaggle.com/c/lux-ai-2021/

Contains development enviornment for building bots. The current `luxbot` contains the 
simple starter kit bot.

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
