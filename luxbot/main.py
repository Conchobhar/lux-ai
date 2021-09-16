from typing import Dict
from agent import agent
import sys


if __name__ == "__main__":
    
    def read_input():
        """
        Reads input from stdin
        """
        try:
            return input()
        except EOFError as eof:
            raise SystemExit(eof)
    step = 0

    class Observation(Dict[str, any]):
        def __init__(self, player=0) -> None:
            super().__init__()
            self.player = player
            self.updates = []
            self.step = 0
    observation = Observation()
    player_id = None
    while True:
        inputs = read_input()
        observation.updates.append(inputs)
        
        if step == 0:
            player_id = int(observation.updates[0])
            observation.player = player_id
        if inputs == "D_DONE":
            actions = agent(observation, None)
            observation.updates = []
            step += 1
            observation.step = step
            # print(f"STEP: {step}", file=sys.stderr)
            print(",".join(actions))
            print("D_FINISH")
