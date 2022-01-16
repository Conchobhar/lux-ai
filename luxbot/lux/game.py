import sys
from .constants import Constants
from .game_map import GameMap, Cell
from .game_objects import Player, Unit, City, CityTile
from . import annotate


INPUT_CONSTANTS = Constants.INPUT_CONSTANTS


class Game:
    def __init__(self, obs):
        """
        initialize state
        """
        self.id = obs.player  # int(obs['updates'][0])
        self.players = [Player(0), Player(1)]
        self.turn = -1
        # get some other necessary initial input
        mapinfo = obs.updates[1].split(" ")
        self.map_width = int(mapinfo[0])
        self.map_height = int(mapinfo[1])
        self.map = GameMap(self.map_width, self.map_height)
        self.update(obs, init=True)
        self.players_initial_positions = [p.citytiles[0].pos for p in self.players]
        self.player_origin = self.players_initial_positions[self.id]
        self.opponent_origin = self.players_initial_positions[0 if self.id == 1 else 1]
        # What axis is the map symmetric about?
        self.symmetric_axis = 'x' if self.player_origin.y == self.opponent_origin.y else 'y'
        self.map.generate_zones(self.id, self.players_initial_positions[self.id])
        # At turn 0, only one citytile. We use this to define the initial positions of the players.

    def cell_is_my_citytile(self, cell: Cell):
        return cell.citytile is not None and cell.citytile.team == self.id

    @staticmethod
    def _end_turn():
        print("D_FINISH")

    def _reset_player_states(self):
        self.players[0].units = []
        self.players[0].cities = {}
        self.players[0].citytiles = []
        self.players[0].city_tile_count = 0
        self.players[1].units = []
        self.players[1].cities = {}
        self.players[1].citytiles = []
        self.players[1].city_tile_count = 0

    def update(self, obs, init=False):
        """
        update state
        """
        self.map = GameMap(self.map_width, self.map_height)
        self.turn = obs.step
        self._reset_player_states()

        for update in obs.updates:
            if update == "D_DONE":
                break
            strs = update.split(" ")
            input_identifier = strs[0]
            if input_identifier == INPUT_CONSTANTS.RESEARCH_POINTS:
                team = int(strs[1])
                self.players[team].research_points = int(strs[2])
            elif input_identifier == INPUT_CONSTANTS.RESOURCES:
                r_type = strs[1]
                x = int(strs[2])
                y = int(strs[3])
                amt = int(float(strs[4]))
                self.map.setResource(r_type, x, y, amt)
            elif input_identifier == INPUT_CONSTANTS.UNITS:
                unittype = int(strs[1])
                team = int(strs[2])
                unitid = strs[3]
                x = int(strs[4])
                y = int(strs[5])
                cooldown = float(strs[6])
                wood = int(strs[7])
                coal = int(strs[8])
                uranium = int(strs[9])
                unit = Unit(team, unittype, unitid, x, y, cooldown, wood, coal, uranium)
                self.players[team].units.append(unit)
                self.map.get_cell(x, y).unit = unit
            elif input_identifier == INPUT_CONSTANTS.CITY:
                team = int(strs[1])
                cityid = strs[2]
                fuel = float(strs[3])
                lightupkeep = float(strs[4])
                self.players[team].cities[cityid] = City(team, cityid, fuel, lightupkeep)
            elif input_identifier == INPUT_CONSTANTS.CITY_TILES:
                team = int(strs[1])
                cityid = strs[2]
                x = int(strs[3])
                y = int(strs[4])
                cooldown = float(strs[5])
                city = self.players[team].cities[cityid]
                citytile = city.add_city_tile(x, y, cooldown, self.id)
                self.players[team].citytiles.append(citytile)
                self.map.get_cell(x, y).citytile = citytile
                self.players[team].city_tile_count += 1
            elif input_identifier == INPUT_CONSTANTS.ROADS:
                x = int(strs[1])
                y = int(strs[2])
                road = float(strs[3])
                self.map.get_cell(x, y).road = road

        if not init:  # Need to have generated players_initial_positions in the init update before using this
            self.map.generate_zones(self.id, self.players_initial_positions[self.id])
