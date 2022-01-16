from typing import Dict, List

from .constants import Constants
from .game_map import Position, MapZone
from .game_constants import GAME_CONSTANTS

UNIT_TYPES = Constants.UNIT_TYPES
RESOURCE_TYPES = Constants.RESOURCE_TYPES

class Player:
    def __init__(self, team):
        self.team = team
        self.research_points = 0
        self.units: List[Unit] = []
        self.cities: Dict[str, City] = {}
        self.citytiles: List[CityTile] = []
        self.city_tile_count = 0

    def researched_coal(self) -> bool:
        return self.research_points >= GAME_CONSTANTS["PARAMETERS"]["RESEARCH_REQUIREMENTS"]["COAL"]

    def researched_uranium(self) -> bool:
        return self.research_points >= GAME_CONSTANTS["PARAMETERS"]["RESEARCH_REQUIREMENTS"]["URANIUM"]


class City:
    def __init__(self, teamid, cityid, fuel, light_upkeep):
        self.cityid = cityid
        self.team = teamid
        self.fuel = fuel
        self.citytiles: List[CityTile] = []
        self.light_upkeep = light_upkeep

    def __repr__(self):
        return f"C({self.cityid} fuel:{self.fuel} nights left:{(self.fuel//self.light_upkeep)})"

    def add_city_tile(self, x, y, cooldown, playerid):
        ct = CityTile(self, x, y, cooldown, playerid)
        self.citytiles.append(ct)
        return ct

    def get_light_upkeep(self):
        return self.light_upkeep

    def get_time_to_expiration(self):
        # fuel // costPerNightTurn
        pass

    def will_not_survive_night(self):
        return (self.fuel / self.light_upkeep) <= 10

    def is_worth_saving(self, night_left):
        return ((night_left * self.light_upkeep) - self.fuel) <= 100


class CityTile:
    def __init__(self, city, x, y, cooldown, playerid):
        self.cityid = city.cityid
        self.city = city
        self.team = city.team  # What player does this belong to?
        self.pos = Position(x, y)
        self.cooldown = cooldown
        self.playerid = playerid  # What player generated this?
        self.zone: MapZone = None

    def is_player_citytile(self):
        return self.team == self.playerid

    def __repr__(self):
        return f"({self.cityid} p:{self.pos} cd:{int(self.cooldown)})"

    def can_act(self) -> bool:
        """
        Whether or not this unit can research or build
        """
        return self.cooldown < 1

    def research(self) -> str:
        """
        returns command to ask this tile to research this turn
        """
        return "r {} {}".format(self.pos.x, self.pos.y)

    def build_worker(self) -> str:
        """
        returns command to ask this tile to build a worker this turn
        """
        return "bw {} {}".format(self.pos.x, self.pos.y)

    def build_cart(self) -> str:
        """
        returns command to ask this tile to build a cart this turn
        """
        return "bc {} {}".format(self.pos.x, self.pos.y)


class Cargo:
    def __init__(self):
        self.wood = 0
        self.coal = 0
        self.uranium = 0

    def sum_total(self):
        return self.wood + self.coal + self.uranium

    def __str__(self) -> str:
        return f"Cargo | Wood: {self.wood}, Coal: {self.coal}, Uranium: {self.uranium}"

    def __getitem__(self, item):
        if item == RESOURCE_TYPES.WOOD:
            return self.wood
        if item == RESOURCE_TYPES.COAL:
            return self.coal
        if item == RESOURCE_TYPES.URANIUM:
            return self.uranium


class UnitLog:
    city = None
    citytile = None
    resource_cell = None
    prospective_action = None
    set_action = None
    set_cell = None
    task = None  # Task assignment loop
    cell_target = None  # Task assignment loop
    action = None  # Task assignment loop
    cell_next = None  # Task assignment loop
    max_safe_distance = None  # Est. how far unit can travel before expiring
    zone_assigned: MapZone = None
    zone_closest: MapZone = None
    zone_gather_cell: 'Cell' = None


class Unit:
    def __init__(self, teamid, u_type, unitid, x, y, cooldown, wood, coal, uranium):
        self.pos = Position(x, y)
        self.team = teamid
        self.id = unitid
        self.type = u_type
        self.cooldown = cooldown
        self.cargo = Cargo()
        self.cargo.wood = wood
        self.cargo.coal = coal
        self.cargo.uranium = uranium
        self.log = UnitLog()

    def __repr__(self):
        return f"U({self.type} {self.id})"

    def is_worker(self) -> bool:
        return self.type == UNIT_TYPES.WORKER

    def is_cart(self) -> bool:
        return self.type == UNIT_TYPES.CART

    def fuel(self):
        return self.cargo.wood + self.cargo.coal*10 + self.cargo.uranium*40

    def is_fuel_efficient(self):
        return self.fuel() >= 500

    def light_upkeep(self):
        return 4 if self.type == 0 else 10

    def will_not_survive_night(self, remaining_night):
        return (self.fuel() / self.light_upkeep()) <= remaining_night  # TODO +prospective fuel from harvesting

    def get_cargo_space_left(self):
        """
        get cargo space left in this unit
        """
        spaceused = self.cargo.wood + self.cargo.coal + self.cargo.uranium
        if self.type == UNIT_TYPES.WORKER:
            return GAME_CONSTANTS["PARAMETERS"]["RESOURCE_CAPACITY"]["WORKER"] - spaceused
        else:
            return GAME_CONSTANTS["PARAMETERS"]["RESOURCE_CAPACITY"]["CART"] - spaceused

    def can_afford_to_build(self):
        return (self.cargo.wood + self.cargo.coal + self.cargo.uranium) \
               >= GAME_CONSTANTS["PARAMETERS"]["CITY_BUILD_COST"]

    def can_build_on_this_cell(self, game_map) -> bool:
        """
        whether or not the unit can build where it is right now
        """
        cell = game_map.get_cell_by_pos(self.pos)
        if not cell.has_resource() and self.can_act() and self.can_afford_to_build():
            return True
        return False

    def can_act(self) -> bool:
        """
        whether or not the unit can move or not. This does not check for potential collisions into other units or enemy cities
        """
        return self.cooldown < 1

    def move(self, dir) -> str:
        """
        return the command to move unit in the given direction
        """
        return "m {} {}".format(self.id, dir)

    def transfer(self, dest_id, resourceType, amount) -> str:
        """
        return the command to transfer a resource from a source unit to a destination unit as specified by their ids
        """
        return "t {} {} {} {}".format(self.id, dest_id, resourceType, amount)

    def build_city(self) -> str:
        """
        return the command to build a city right under the worker
        """
        return "bcity {}".format(self.id)

    def pillage(self) -> str:
        """
        return the command to pillage whatever is underneath the worker
        """
        return "p {}".format(self.id)
