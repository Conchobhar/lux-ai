import logging
import math
import random
import sys
from enum import Enum
import itertools
from typing import Dict

from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES
from lux.game_objects import Unit, City, CityTile, Position
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
from tools import Log, LogEntry

DIRECTIONS = Constants.DIRECTIONS()
global game, myagent, log


class Task(Enum):
    GATHER = 1
    BUILD = 2
    DEPOSIT = 3
    WANDER = 4


# Unit action 2 direction it will move to perform
action2direction = {
    'n': 'n',
    'e': 'e',
    's': 's',
    'w': 'w',
    'c': 'c',
    'bcity': 'c',
    'p': 'c',
    't': 'c',
}


def get_command_from_action(unit, action):
    if action in ('n', 'e', 's', 'w', 'c'):
        return unit.move(action)
    if action == 'bcity':
        return unit.build_city()
    if action == 'p':
        return unit.pillage()
    if action == 't':
        return unit.transfer(...)  # TODO


def pos2cell(pos: Position) -> Cell:
    return game.map.get_cell_by_pos(pos)


def group_units_by_requested_cells(units2cells: Dict[Unit, list[Cell]]):
    cell2units = {}
    for u, c in units2cells.items():
        if c in cell2units:
            cell2units[c].append(u)
        else:
            cell2units[c] = [u, ]
    return cell2units


class MyAgent:

    def __init__(self, game_state):
        self.g = game_state
        self.player = game_state.players[game_state.id]
        self.opponent = game_state.players[(game_state.id + 1) % 2]
        self.height = game_state.map.height
        self.width = game_state.map.width
        self.resource_cells: set[Cell] = set()
        self.potential_city_cells: set[Cell] = set()
        self.worker_add_this_turn = 0
        self.num_workers = 0
        self.num_cities = 0
        self.reserved_cells: Dict[Cell, Unit] = {}
        self.set_actions: Dict[Unit, str] = {}
        self.set_cells: Dict[Unit, Cell] = {}

    def time_to_night(self):
        cycle_length = GAME_CONSTANTS['PARAMETERS']['DAY_LENGTH'] + GAME_CONSTANTS['PARAMETERS']['NIGHT_LENGTH']
        return GAME_CONSTANTS['PARAMETERS']['DAY_LENGTH'] - (self.g.turn % cycle_length)

    def is_night(self):
        return self.time_to_night() < 1

    def potential_worker_count(self):
        possible_workers = len(self.get_citytiles(self.player)) - len(self.player.units)
        return possible_workers - self.worker_add_this_turn

    def set_research(self):
        if self.num_cities >= 3:
            actable_citytiles = [ct for ct in self.get_citytiles(self.player) if ct.can_act()]
            num_researchers = len(actable_citytiles) // 2
            for citytile in actable_citytiles[0:num_researchers]:
                self.set_commands.append(citytile.research())
                self.set_researchers.append(citytile)


    def map_workers_to_city_tiles(self):
        import itertools
        unassigned_workers = ([u for u in self.player.units if u.is_worker()])
        if self.num_cities > 0 and self.num_workers > 0:
            while len(unassigned_workers) > 0:
                for cid, city in self.player.cities.items():
                    pairs = list(itertools.product(city.citytiles, unassigned_workers))
                    citytile, unit = min(pairs, key=lambda pair: pair[0].pos.distance_to(pair[1].pos))
                    unit.log.citytile = citytile
                    unit.log.city = city
                    unassigned_workers.remove(unit)
                    if len(unassigned_workers) == 0:
                        break

    @staticmethod
    def get_citytiles(player) -> list[CityTile]:
        return [ct for _, city in player.cities.items() for ct in city.citytiles]

    def get_nearest_city_and_tile(self, unit: Unit) -> (City, CityTile):
        city2closest_citytile = {}
        for _, city in self.player.cities.items():
            city2closest_citytile[city] = min([ct for ct in city.citytiles],
                                              key=lambda ct: unit.pos.distance_to(ct.pos))
        return min(city2closest_citytile.items(), key=lambda x: unit.pos.distance_to(x[1].pos))

    def determine_task(self, worker: Unit) -> Task:
        is_day = not self.is_night()
        if is_day:
            if worker.get_cargo_space_left() > 0 and len(self.resource_cells) > 0:
                return Task.GATHER
            if worker.log.city is not None:
                if worker.log.city.will_not_survive_night():
                    return Task.DEPOSIT
            if worker.can_afford_to_build():
                return Task.BUILD
        if (not is_day) and (self.num_cities > 0):
            return Task.DEPOSIT
        else:
            print(f"WARNING: Catch all task returned.")
            return Task.WANDER

    def get_resource_cells_by_worth(self, unit: Unit) -> Dict[Cell, float]:
        rc2worth = {}
        for rc in self.resource_cells:
            # TODO - value by gather radius
            rc2worth[rc] = (rc.resource.amount / (unit.pos.distance_to(rc.pos) + 1))
        return rc2worth

    def determine_target_cell_for_task(self, unit: Unit, task: Task) -> Cell:
        if task == Task.GATHER:
            cell = max(self.get_resource_cells_by_worth(unit).items(), key=lambda x: x[1])[0]
        elif task == Task.BUILD:  # Nearest empty tile adjacent resource
            cell = min([c for c in self.potential_city_cells], key=lambda c: unit.pos.distance_to(c.pos))
        elif task == Task.DEPOSIT:
            # get citys within radius
            # deposit in closest citytile for city with lowest resource
            cell = pos2cell(unit.log.citytile.pos)
        else:
            print(f"WARNING: unit {unit} found with task {task} without defined behaviour here.")
            cell = pos2cell(unit.pos)
        return cell

    def pathfind(self, unit: Unit, cell: Cell) -> DIRECTIONS:
        check_dirs = [
            DIRECTIONS.NORTH,
            DIRECTIONS.EAST,
            DIRECTIONS.SOUTH,
            DIRECTIONS.WEST,
            DIRECTIONS.CENTER,
        ]
        closest_dist = None  #
        closest_dir = None
        for direction in check_dirs:
            newpos = unit.pos.translate(direction, 1)
            if self.g.map.is_valid_position(newpos):
                not_reserved = pos2cell(newpos) not in self.set_cells.values()
                is_not_enemy_ct = pos2cell(newpos) not in self.opponent.citytiles
                if not_reserved and is_not_enemy_ct:
                    dist = cell.pos.distance_to(newpos)
                    if closest_dist is None or dist < closest_dist:
                        closest_dir = direction
                        closest_dist = dist
        if closest_dir is None:
            print(f"Alert: pathfinding defaulting to North for {unit}", file=sys.stderr)
            closest_dir = DIRECTIONS.NORTH  # TODO - Weight directions and pick least worst in this case.
        return closest_dir

    def determine_action_for_cell(self, unit: Unit, task: Task, cell: Cell) -> str:
        if not unit.pos.equals(cell.pos):
            action = self.pathfind(unit, cell)
        else:
            if task == Task.GATHER:
                action = self.pathfind(unit, cell)
            elif task == Task.BUILD:
                action = 'bcity'
            elif task == Task.DEPOSIT:
                closest_city_cell = min(self.get_citytiles(self.player), key=lambda c: unit.pos.distance_to(c.pos))
                action = self.pathfind(unit, pos2cell(closest_city_cell.pos))
            else:  # Task.WANDER
                action = random.choice(DIRECTIONS.get_all())
        return action

    def get_resource_cells(self):
        """Collect resource tiles. Ignore advanced materials if unobtainable so far."""
        resource_cells: list[Cell] = []
        for y in range(self.height):
            for x in range(self.width):
                cell = self.g.map.get_cell(x, y)
                if cell.has_resource():
                    consider_coal = cell.resource.type == Constants.RESOURCE_TYPES.COAL and not self.player.researched_coal()
                    consider_uranium = cell.resource.type == Constants.RESOURCE_TYPES.URANIUM and not self.player.researched_uranium()
                    if consider_coal or consider_uranium:
                        continue
                    else:
                        resource_cells.append(cell)
        return resource_cells

    def get_potential_city_cells(self):
        """Collect resource tiles. Ignore advanced materials if unobtainable so far."""
        cells: set[Cell] = set()
        for cell in self.resource_cells:
            cells |= {c for c in self.g.map.get_adjacent_cells(cell) if not c.has_resource() and not c.has_city_tile()}
        return cells

    def generate_stats(self):
        self.resource_cells = self.get_resource_cells()
        self.potential_city_cells = self.get_potential_city_cells()

    def confirm_commands(self, u, c):
        if u.can_act():  # Avoids warnings about units not able to act even when acting to stay still.
            self.set_commands.append(get_command_from_action(u, self.prospective_actions[u]))
            self.set_actions[u] = self.prospective_actions[u]
        self.set_cells[u] = c

    def get_actions(self, g):
        """Next
            - value resources by net harvest across all cells
            - spawn citytiles efficiently i.e. adjacent each other
                - limit cts by resources
                - create a map of valid locations to build
            - assign workers to specific cities
                - deposit considering ct time to expiration and unit distance
            - assign Zones() to contiguious resources
                - with centroid?
                - limit workers to Zones
                - go to nearest unsaturated zone
            - A* pathfind
        """
        turn = g.turn
        self.num_cities = len(self.player.cities)
        self.num_workers = len([u for u in self.player.units if u.is_worker()])
        self.generate_stats()
        self.map_workers_to_city_tiles()
        self.set_commands = []
        self.set_research()
        # self.produce_workers()
        self.reserved_cells: Dict[Cell] = {}
        self.set_actions: Dict[Unit] = {}
        self.set_cells: Dict[Unit] = {}
        self.set_researchers: list[CityTile] = []
        self.prospective_actions: Dict[Unit] = {}
        """
        Get task for worker
        gather
            go to resource spot
            +  resource potential
            -  distance to resource
            -- zone is saturated
        """
        # Determine unit actions
        nonactable_worker_units = [u for u in self.player.units if u.is_worker() and not u.can_act()]
        for unit in nonactable_worker_units:
            if pos2cell(unit.pos).citytile is None:
                self.prospective_actions[unit] = 'c'
                self.confirm_commands(unit, pos2cell(unit.pos))
        actable_worker_units = [u for u in self.player.units if u.is_worker() and u.can_act()]
        action_iter = 0
        while len(self.set_actions) < len(actable_worker_units):
            action_iter += 1
            if action_iter > 24:
                raise Exception(f"action resolution iteration > 24 - probable infinite loop")
            unassigned_worker_units = [u for u in actable_worker_units if u not in self.set_actions]
            self.prospective_actions = {}
            units2prospective_cell: Dict[Unit] = {}
            for unit in unassigned_worker_units:
                task = self.determine_task(unit)
                cell_target = self.determine_target_cell_for_task(unit, task)
                action = self.determine_action_for_cell(unit, task, cell_target)
                cell_next = pos2cell(unit.pos.translate(action2direction[action], 1))
                self.prospective_actions[unit] = action
                units2prospective_cell[unit] = cell_next

            # ACTION CONFLICT RESOLUTION
            # Confirm non-conflicting actions. Record set actions in ship log to keep track of
            # how many ships actions are finalized. Resolve actions outwards from shipyards.
            cell2units = group_units_by_requested_cells(units2prospective_cell)
            for cell, units in cell2units.items():
                if cell.citytile is None:  # Give spot to highest priority ship
                    unit = min(units, key=lambda u: u.cargo.wood)
                    self.confirm_commands(unit, cell)
                else:
                    for unit in units:
                        self.confirm_commands(unit, cell)

        # Determine worker building
        self.worker_add_this_turn = 0
        should_build = self.potential_worker_count() > 0
        if should_build:
            for citytile in self.get_citytiles(self.player):
                if citytile.can_act() and self.potential_worker_count() > 0 and citytile not in self.set_researchers:
                    self.set_commands.append(citytile.build_worker())
                    self.worker_add_this_turn += 1

        # you can add debug annotations using the functions in the annotate object
        # actions.append(annotate.circle(0, 0))
        return self.set_commands


def agent(obs, config):
    global game, myagent, log
    # Initalize game else update
    if obs.step == 0:
        game = Game(obs)
        myagent = MyAgent(game)
        log = Log()
    else:
        game.update(obs.updates)
    print(f'Turn:{obs.step}', file=sys.stderr)
    actions = myagent.get_actions(game)
    return actions
