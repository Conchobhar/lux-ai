class LogEntry:
    """Log values for each ship. Like a dictionary, without the ['fluff']"""

    def __init__(self):
        self.role = 'NEW'
        self.role_suspended = None
        self.target_cell = None   # Where ship wants to move based on role
        self.spot = None            # assigned harvest spot
        self.yard = None            # nearerst yard
        self.squad = None
        self.p_action = None
        self.p_point = None
        self.set_action = None
        self.set_point = None
        self.last_action = None
        self.frustration = 0
        self.is_frustrated = False
        self.adj_allies = 0
        self.adj_threats = 0
        self.track_id = None
        self.resetable_names = ['p_action', 'p_point', 'set_action', 'set_point', ]

    def reset_turn_values(self):
        """Reset values that don't carry across turns."""
        for name in self.resetable_names:
            setattr(self, name, None)

    def __str__(self):
        return f"R:{self.role} S:{self.spot} p_a:{self.p_action} p_p:{self.p_point}"


class Log(dict):
    """Super log to keep track of information across all ships.
    Keys are ships. Values are a LogEntry()"""

    def __init__(self):
        super().__init__()
        # Keep a reference to me - necessary to extract `next_actions`
        self.board = None
        self.me = None
        self.harvest_spot_values = None
        self.enemy_targ_ids = None
        self.id2obj = None  # Map game id's to the objects regenerated each turn
        self.squadrons = []

    @property
    def spots(self):  # Assigned harvest spots
        return [x.spot for x in self.values() if x.spot is not None]

    @property
    def p_points(self):  # Potential next turn positions
        return [x.p_point for x in self.values() if x.p_point is not None]

    @property
    def set_points(self):  # Assigned next turn positions
        return [x.set_point for x in self.values() if x.set_point is not None]

    @property
    def set_actions(self):  # Assigned actions
        return [x.set_action for x in self.values() if x.set_action is not None]