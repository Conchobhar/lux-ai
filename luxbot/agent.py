import logging
import math
import sys
from enum import Enum
import itertools
from functools import lru_cache
from typing import Dict, List

import numpy

from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES, Astar
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
    KETTLE = 5
    SAFE_GATHER = 6


map_height_params = {
    12: {
        'ignore_coal_limit': 45,
        'ignore_uranium_limit': 195,
    },
    16: {
        'ignore_coal_limit': 40,
        'ignore_uranium_limit': 190,
    },
    24: {
        'ignore_coal_limit': 30,
        'ignore_uranium_limit': 175,
    },
    32: {
        'ignore_coal_limit': 20,
        'ignore_uranium_limit': 170,
    }
}


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


def group_units_by_requested_cells(units2cells: Dict[Unit, List[Cell]]):
    cell2units: Dict[Cell, List[Unit]] = {}
    for u, c in units2cells.items():
        if c in cell2units:
            cell2units[c].append(u)
        else:
            cell2units[c] = [u, ]
    return cell2units


class Clock:

    @staticmethod
    def time_to_night():
        cycle_length = GAME_CONSTANTS['PARAMETERS']['DAY_LENGTH'] + GAME_CONSTANTS['PARAMETERS']['NIGHT_LENGTH']
        return GAME_CONSTANTS['PARAMETERS']['DAY_LENGTH'] - (game.turn % cycle_length)

    def is_night(self):
        return self.time_to_night() < 1

    def remaining_night(self):
        return 10 if not self.is_night() else 10 + self.time_to_night()


clock = Clock()


class MyAgent:

    def __init__(self, game_state):
        self.g = game_state
        self.player = game_state.players[game_state.id]
        self.opponent = game_state.players[(game_state.id + 1) % 2]
        self.height = game_state.map.height
        self.width = game_state.map.width
        self.resource_cells: set[Cell] = set()
        self.potential_city_cells: set[Cell] = set()
        self.prospective_citytile_weights: Dict[Cell, float] = {}
        self.worker_add_this_turn = 0
        self.num_workers = 0
        self.num_cities = 0
        self.reserved_cells: Dict[Cell, Unit] = {}
        self.set_actions: Dict[Unit, str] = {}

    def potential_new_worker_count(self):
        possible_workers = len(self.get_citytiles(self.player)) - len(self.player.units)
        return possible_workers - self.worker_add_this_turn

    def set_research_and_build_commands(self):
        # Determine worker building
        self.worker_add_this_turn = 0
        should_build = self.potential_new_worker_count() > 0
        if should_build:
            sorted_citytiles = sorted(self.get_citytiles(self.player), key=lambda ct: ((len(ct.zone.opponent_units) if ct.zone else 0), ct.pos.distance_to(self.g.player_origin)), reverse=True)
            for citytile in sorted_citytiles:
                if citytile.can_act() and self.potential_new_worker_count() > 0:
                    self.set_builders.append(citytile)
                    self.set_commands.append(citytile.build_worker())
                    self.worker_add_this_turn += 1

        self.set_research_points = 0
        actable_citytiles = [ct for ct in self.get_citytiles(self.player) if ct.can_act() and (ct not in self.set_builders)]
        num_researchers = len(actable_citytiles) - self.potential_new_worker_count()
        for citytile in actable_citytiles[0:num_researchers]:
            if ((self.player.research_points + self.set_research_points) < 200) :
                self.set_commands.append(citytile.research())
                self.set_research_points += 1

    def zone_units(self):
        """Units are assigned to zones they can reach.
        Every unit has a nearest zone, but only those that potentialyl reach a zone will
        have an assigned one. Those assigned a zone are tracked by the zone itself."""

        # Update each zones list of opponent units
        for z in self.g.map.zones:
            z.opponent_units = [u for u in self.opponent.units if pos2cell(u.pos) in (z.cells | set(z.perimeter_cells))]
        zoneable_units = []
        # zone_radius_restriction = max([4, self.g.turn])  # Expand zone radius as game progresses
        zones = [z for z in self.g.map.zones if
                 (z.resource_type == RESOURCE_TYPES.WOOD or
                 (z.resource_type == RESOURCE_TYPES.COAL and not self.IGNORE_COAL) or
                 (z.resource_type == RESOURCE_TYPES.URANIUM and not self.IGNORE_URANIUM))]
        if len(zones) > 0:
            for unit in self.player.units:
                zone2cells = {}
                # Get closest zone by cells constituting that zone, then by distance to opponent origin
                for zone in zones:
                    if len(zone.vacant_cells) > 0:  # Try vacant cells
                        zone2cells[zone] = min(zone.vacant_cells, key=lambda c: unit.pos.distance_to(c.pos))
                    else:  # Then resort to resource cells
                        zone2cells[zone] = min(zone.resource_cells, key=lambda c: unit.pos.distance_to(c.pos))
                # Draw ties by minimum zone saturation
                unit.log.zone_closest = min(zone2cells, key=lambda z: (unit.pos.distance_to(zone2cells[z].pos), z.saturation))
                if any([(self.can_unit_survive_to_cell(unit, pos2cell(z.centroid))) and z.is_unit_assignable(unit)
                        for z in zones]):
                    zoneable_units.append(unit)
            every_zone_saturated = all([z.is_saturated for z in zones])
            assignment_iteration = 0
            initial_len_units = len(zoneable_units)
            while len(zoneable_units) > 0 and not every_zone_saturated:
                ignore_saturation = assignment_iteration > initial_len_units
                if ignore_saturation:
                    zones = sorted(zones, key=lambda z:z.saturation, reverse=True)
                for zone in [z for z in zones if (not z.is_saturated) or ignore_saturation]:  # sorted by distance to starting pos
                    # Assign units with cooldown as well for stability across turn assignments
                    potential_units = [u for u in zoneable_units
                                       if u.is_worker() and u.log.zone_assigned is None
                                       and self.can_unit_survive_to_cell(u, pos2cell(zone.centroid))]
                    if len(potential_units) > 0:
                        unit = min(potential_units, key=lambda u: u.pos.distance_to(zone.centroid))
                        unit.log.zone_assigned = zone
                        zone.assigned_units.append(unit)
                        zoneable_units.remove(unit)
                    else:
                        pass
                    assignment_iteration += 1
                    if len(zoneable_units) == 0:
                        break
                every_zone_saturated = all([z.is_saturated for z in zones])

            # Assign any leftovers to their closest zone
            for unit in zoneable_units:
                zone = min(zones, key=lambda z: unit.pos.distance_to(z.centroid))
                unit.log.zone_assigned = zone
                zone.assigned_units.append(unit)
                zoneable_units.remove(unit)

    def get_best_gather_cell_for_zone(self, unit, zone):
        """Assumes zone is logged for unit."""
        z = zone
        cell = None
        assigned_limit = True
        # Include player citiles as greedy spots for fuel efficient resources OR if for wood and player CT has opponent adj.
        if zone.is_enclaved_by_opponent:
            # If zone is fully controlled by opponent, find CT soon to expire.
            cell = min(zone.opponent_citytiles, key=lambda ct: (ct.citytile.city.fuel, unit.pos.distance_to(ct.pos)))
        elif z.is_enclaved and self.g.map.get_cell_by_pos(
                unit.pos) not in zone.cells and zone.resource_type == RESOURCE_TYPES.WOOD:
            cell = min(zone.player_citytiles, key=lambda ct: (ct.citytile.city.fuel, unit.pos.distance_to(ct.pos)))
        else:
            if z.resource_type == RESOURCE_TYPES.WOOD:
                ordered_cell_groups = [ z.vacant_cells, z.player_citytiles_with_adj_opponent_unit, z.resource_cells_not_adj_ct, z.resource_cells_adj_ct]
            else:  # Prioritize sitting on resource cells to maximize harvest rate from slower resources, only if > 1 rcs
                if len(zone.resource_cells) > 1:
                    ordered_cell_groups = [z.resource_cells_not_adj_ct, z.resource_cells_adj_ct,  z.vacant_cells, z.player_citytiles_with_adj_opponent_unit, z.player_citytiles]
                else:
                    ordered_cell_groups = [z.vacant_cells, z.player_citytiles_with_adj_opponent_unit, z.resource_cells_not_adj_ct, z.resource_cells_adj_ct]
            for _ in range(2): # Loop twice, once with restriction then remove.
                for zone_cells in ordered_cell_groups:
                    filtered_cells = [vc for vc in zone_cells if vc not in z.assigned_gather_cells] if assigned_limit else zone_cells
                    if len(filtered_cells) > 0:
                        cells = sorted(filtered_cells, key=lambda vc: (vc.pos.distance_to(unit.pos), vc.pos.distance_to(self.g.opponent_origin)))
                        for cell in cells:
                            if self.can_unit_survive_to_cell(unit, cell):
                                break
                        if cell is not None:
                            break
                assigned_limit = False  # If no free spaces left, remove restriction and guarantee a result.
            if cell is None:
                cell = min(sum(ordered_cell_groups, []), key=lambda vc: (vc.pos.distance_to(unit.pos), vc.pos.distance_to(self.g.opponent_origin)))
        return cell

    def map_workers_to_cells(self):
        import itertools
        # Map to cities to monitor for expiration and nearest citytile
        unassigned_workers = ([u for u in self.player.units if u.is_worker()])
        if self.num_cities > 0 and self.num_workers > 0:
            while len(unassigned_workers) > 0:
                for cid, city in self.player.cities.items():
                    pairs = list(itertools.product(city.citytiles, unassigned_workers))
                    citytile, unit = min(
                        pairs, key=lambda pair: (pair[0].pos.distance_to(pair[1].pos),
                                                 pair[1].fuel()))
                    unit.log.citytile = citytile
                    unit.log.city = city
                    unassigned_workers.remove(unit)
                    if len(unassigned_workers) == 0:
                        break
        unassigned_workers = ([u for u in self.player.units if u.is_worker()])
        # Map to resource spots. TODO ignore those enclaved by opp
        self.set_resource_cells = []
        if len(self.resource_cells) > 0 and self.num_workers > 0:
            u2rcbyw = {}  # unit 2 resourceCount by Weight
            for unit in unassigned_workers:  # get worth values for each cell for each unassigned unit
                u2rcbyw[unit] = self.get_resource_cells_by_worth(unit).items()
            while len(u2rcbyw) > 0:
                exploded = []
                for u, rcbyw in u2rcbyw.items():  # For cells not yet set, explode out full rows for each unit
                    exploded.extend([(u, rc, w) for u, (rc, w) in itertools.product([u, ], rcbyw) if
                                     rc not in self.set_resource_cells])
                if len(exploded) == 0:
                    break
                unit, rc, w = max(exploded, key=lambda triple: triple[2])  # assign best unit cell pairing by weight
                unit.log.resource_cell = rc
                del u2rcbyw[unit]
                self.set_resource_cells.append(rc)

    @staticmethod
    def get_citytiles(player) -> List[CityTile]:
        return [ct for _, city in player.cities.items() for ct in city.citytiles]

    def get_nearest_city_and_tile(self, unit: Unit) -> (City, CityTile):  # TODO not used
        city2closest_citytile = {}
        for _, city in self.player.cities.items():
            city2closest_citytile[city] = min([ct for ct in city.citytiles],
                                              key=lambda ct: unit.pos.distance_to(ct.pos))
        return min(city2closest_citytile.items(), key=lambda x: unit.pos.distance_to(x[1].pos))

    resource2unitsperturn = {
        'NA': 0,
        Constants.RESOURCE_TYPES.WOOD: 20,
        Constants.RESOURCE_TYPES.COAL: 5,
        Constants.RESOURCE_TYPES.URANIUM: 2,
    }
    resource2value = {
        'NA': 0,
        Constants.RESOURCE_TYPES.WOOD: 20/20,
        Constants.RESOURCE_TYPES.COAL: (25)/20,
        Constants.RESOURCE_TYPES.URANIUM: (30)/20,
    }

    def will_be_full_when_at_build_spot(self, worker: Unit, target_cell) -> bool:
        cell = pos2cell(worker.pos)
        resource_types = [rc.resource.type for rc in (self.g.map.get_adjacent_cells(cell) | {cell}) if rc.resource]
        main_type = 'NA'
        if len(resource_types) > 0:
            if RESOURCE_TYPES.WOOD in resource_types:
                main_type = RESOURCE_TYPES.WOOD
            elif RESOURCE_TYPES.COAL in resource_types:
                main_type = RESOURCE_TYPES.COAL
            else:
                assert(RESOURCE_TYPES.URANIUM in resource_types)
                main_type = RESOURCE_TYPES.URANIUM
        current_resource_type = main_type
        # Assume at most unit will traverse 2 additional steps and harvest along the way
        est_cargo = worker.cargo.sum_total() + self.resource2unitsperturn[current_resource_type] * min(2, worker.pos.distance_to(
            target_cell.pos))
        return est_cargo >= 100

    def get_potential_build_cell(self, unit: Unit) -> Cell:
        return min([c for c in self.potential_city_cells], key=lambda c: unit.pos.distance_to(c.pos))
        # return max(self.prospective_citytile_weights.items(),
        #            key=lambda p: p[1] / (unit.pos.distance_to(p[0].pos)**(1.4) + 1))[0]

    def is_harvestable(self, cell: Cell):
        if cell.resource is None:
            return False
        else:
            return (cell.resource.type == RESOURCE_TYPES.WOOD
                    or cell.resource.type == RESOURCE_TYPES.COAL and self.player.research_points >= 50
                    or cell.resource.type == RESOURCE_TYPES.URANIUM and self.player.research_points >= 200)

    @lru_cache(maxsize=1024)
    def can_unit_survive_to_cell(self, unit, target_cell):
        """Consider if unit can survive the next night cycle"""
        distance_total = unit.pos.distance_to(target_cell.pos)
        path = self.astar.search(pos2cell(unit.pos), target_cell, unit, limit=4)
        distance_from_harvesting = 0
        reserve = 0
        # Try to estimate additional steps unit gains by harvesting along way.
        # This is only really useful for night if a worker is on a CT (and hence has zero fuel)
        for cell in path:
            will_unit_harvest = self.is_harvestable(cell) or any(
                [self.is_harvestable(adj) for adj in self.g.map.get_adjacent_cells(cell)])
            if will_unit_harvest:
                reserve += 1
                distance_from_harvesting += 1
            else:
                reserve -= 1
            if reserve < 0:
                break
        return distance_total <= unit.log.max_safe_distance + distance_from_harvesting

    def determine_task_and_cell_zone(self, unit: Unit) -> (Task, Cell, 'MapZone'):
        zone = None
        if unit.log.zone_closest:
            if unit.log.zone_closest.is_enclaved and pos2cell(unit.pos) in unit.log.zone_closest.resource_cells:
                zone = unit.log.zone_closest
            else:
                zone = unit.log.zone_assigned if unit.log.zone_assigned else unit.log.zone_closest
            # BUILD
            if not clock.is_night():
                should_build = True  # (len(self.opponent.citytiles) > len(self.player.citytiles)) or (len(great_ct_spots) > 0)
                build_zone = None
                if len(unit.log.zone_closest.vacant_cells) > 0:
                    build_zone = unit.log.zone_closest
                elif unit.log.zone_assigned and len(unit.log.zone_assigned.vacant_cells) > 0:
                    build_zone = unit.log.zone_assigned
                if build_zone:
                    potential_build_cell = min(build_zone.vacant_cells,
                                               key=lambda c: (c.pos.distance_to(unit.pos),
                                                              c.pos.distance_to(self.g.opponent_origin, axis=self.g.symmetric_axis),
                                                              ))
                    if should_build and potential_build_cell and self.will_be_full_when_at_build_spot(unit, potential_build_cell):
                        return Task.BUILD, potential_build_cell, zone
            # DEPOSIT
            if unit.is_fuel_efficient():
                deposit_ct = None
                # Get largest city group that unit can make it to before it expires
                cities = []
                for c in self.player.cities.values():
                    ct = min(c.citytiles, key=lambda ct: ct.pos.distance_to(unit.pos))
                    if self.can_unit_survive_to_cell(unit, pos2cell(ct.pos)):
                        cities.append((c, ct,))
                cities = sorted(cities, key=lambda pair: len(pair[0].citytiles), reverse=True)
                if len(cities) > 0:
                    deposit_ct = cities[0][1]
                elif len(self.player.citytiles) > 0:
                    deposit_ct = min(self.player.citytiles, key=lambda ct: ct.pos.distance_to(unit.pos))
                if deposit_ct and (unit.pos.distance_to(deposit_ct.pos) < 10):
                    return Task.DEPOSIT, deposit_ct, zone
            # GATHER
            gather_cell = self.get_best_gather_cell_for_zone(unit, zone)
            if gather_cell:
                return Task.GATHER, gather_cell, zone
        if len(self.resource_locked_cells) > 0:
            potential_wander_cell = min(self.resource_locked_cells, key=lambda c: unit.pos.distance_to(c.pos))
            return Task.WANDER, potential_wander_cell, zone
        else:  # Do anything...
            if len(self.opponent.citytiles) > 0:
                cell = min(self.opponent.citytiles, key=lambda ct: unit.pos.distance_to(ct.pos))
            else:
                midpoint = Position(self.height // 2, self.width // 2)
                cell = self.g.map.get_cell_by_pos(midpoint)
            return Task.KETTLE, cell, zone

    def get_resource_cells_by_worth(self, unit: Unit) -> Dict[Cell, float]:
        rc2worth = {}
        for rc in self.resource_cells:
            rcs = {rc, } | self.g.map.get_adjacent_cells(rc)
            value_total = 0
            ct_count = 1
            for rc_adj in rcs:
                value = 0
                if rc_adj.resource:
                    value = rc_adj.resource.amount  # * self.resource2value[rc_adj.resource.type]
                elif rc_adj.citytile and rc_adj.citytile in self.player.citytiles:
                    ct_count += 2
                    value = 0

                value_total += value
            value_total /= ct_count
            # t2n = max(0, clock.time_to_night())
            rc2worth[rc] = value_total / (max(1, unit.pos.distance_to(rc.pos)))
        return rc2worth

    def _past_get_resource_cells_by_worth(self, unit: Unit) -> Dict[Cell, float]:
        rc2worth = {}
        for rc in self.resource_cells:
            # TODO - value by individual resources, devalue expiring trees
            rcs = {rc, } | self.g.map.get_adjacent_cells(rc)
            rc2worth[rc] = (sum([rc.resource.amount for rc in rcs if rc.resource]) / (unit.pos.distance_to(rc.pos) + 1))
        return rc2worth

    # [0] indexing raising type warning incorrectly
    # noinspection PyUnresolvedReferences
    def determine_target_cell_for_task(self, unit: Unit, task: Task) -> Cell:
        if task == Task.GATHER:
            if unit.log.resource_cell is not None:
                cell = unit.log.resource_cell
            else:  # If no cell was assigned initially, default to best cell for that unit
                cell = max(self.get_resource_cells_by_worth(unit).items(), key=lambda x: x[1])[0]
        elif task == Task.SAFE_GATHER:  # Go to nearest gather point
            if len(self.resource_cells) > 0:
                cell = min(self.resource_cells, key=lambda rc: unit.pos.distance_to(rc.pos))
            elif len(self.resource_locked_cells) > 0:
                cell = min(self.resource_locked_cells, key=lambda rc: unit.pos.distance_to(rc.pos))
        elif task == Task.BUILD:
            cell = self.get_potential_build_cell(unit)
        elif task == Task.DEPOSIT:
            cell = pos2cell(unit.log.citytile.pos)
        elif task == Task.WANDER:
            cell = min(self.resource_locked_cells, key=lambda c: unit.pos.distance_to(c.pos))
        elif task == Task.KETTLE:
            if len(self.opponent.citytiles) > 0:
                cell = min(self.opponent.citytiles, key=lambda c: unit.pos.distance_to(c.pos))
            else:
                cell = self.g.map[self.height // 2, self.width // 2]
        else:
            print(f"WARNING: unit {unit} found with task {task} without defined behaviour here.")
            cell = pos2cell(unit.pos)
        return cell

    def pathfind(self, initial_cell: Cell, task: Task, target_cell: Cell, unit: Unit) -> DIRECTIONS:
        if initial_cell == target_cell:
            return 'c'
        path = self.astar.search(pos2cell(initial_cell.pos), pos2cell(target_cell.pos), unit, limit=self.ASTAR_LIMIT)
        if len(path) > 0:
            # Annotate
            cell1 = initial_cell
            for cell in path:
                cell2 = cell
                self.set_commands.append(annotate.line(cell1.pos.x, cell1.pos.y, cell2.pos.x, cell2.pos.y))
                cell1 = cell2
            next_cell = path.popleft()
            return initial_cell.pos.direction_to(next_cell.pos)
        print(f"CAUTION: No path found! Trying any available spot")
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
            newpos = initial_cell.pos.translate(direction, 1)
            if self.g.map.is_valid_position(newpos):
                not_reserved = pos2cell(newpos) not in self.g.map.set_cells.values()
                not_enemy_ct = newpos not in [ct.pos for ct in self.opponent.citytiles]
                build_penalty = 1 if (task == Task.BUILD) and (pos2cell(newpos).citytile is not None) else 0
                # wait_penalty = 1.1 if (task == Task.BUILD) and (initial_cell != target_cell) else 0
                if not_reserved and not_enemy_ct:
                    dist = target_cell.pos.distance_to(newpos) + build_penalty
                    if closest_dist is None or dist < closest_dist:
                        closest_dir = direction
                        closest_dist = dist
        if closest_dir is None:
            print(f"Alert: pathfinding defaulting to North for {initial_cell}", file=sys.stderr)
            closest_dir = DIRECTIONS.NORTH  # TODO - Weight directions and pick least worst in this case.
        return closest_dir

    def determine_action_for_cell(self, unit: Unit, task: Task, cell: Cell) -> (str, Cell):
        if not unit.pos.equals(cell.pos):
            action = self.pathfind(pos2cell(unit.pos), task, cell, unit)
        else:
            if task == Task.GATHER:
                action = self.pathfind(pos2cell(unit.pos), task, cell, unit)
            elif task == Task.BUILD:
                action = 'bcity'
            elif task == Task.DEPOSIT:
                action = self.pathfind(pos2cell(unit.pos), task, cell, unit)
            else:  # Task.WANDER
                action = self.pathfind(pos2cell(unit.pos), task, cell, unit)
        return action, pos2cell(unit.pos.translate(action2direction[action], 1))

    def setup_resource_cells(self):
        """Collect resource tiles. Ignore advanced materials if unobtainable so far."""
        self.resource_cells: List[Cell] = []
        self.resource_locked_cells: List[Cell] = []
        for cell in self.g.map:
            if cell.has_resource():
                ignore_coal = cell.resource.type == Constants.RESOURCE_TYPES.COAL and (
                        self.IGNORE_COAL)
                ignore_uranium = cell.resource.type == Constants.RESOURCE_TYPES.URANIUM and (
                        self.IGNORE_URANIUM)
                if ignore_coal or ignore_uranium:
                    self.resource_locked_cells.append(cell)
                else:
                    self.resource_cells.append(cell)

    def setup_potential_city_cells(self):
        """Collect resource tiles. Ignore advanced materials if unobtainable so far.
        Value of cell for building
            - adj res + adj ct
            - adj resource
            - adj ct + across from ct
            - across from ct
        """
        cells: set[Cell] = set()
        for cell in self.resource_cells:
            cells |= {c for c in self.g.map.get_adjacent_cells(cell) if not c.has_resource() and not c.has_city_tile()}
        self.potential_city_cells = cells

    def get_astar_limit(self):
        nunits = len(self.player.units)
        if nunits < 40:
            return 8
        elif nunits < 50:
            return 4
        else:
            return 2

    def generate_stats(self):
        self.ASTAR_LIMIT = self.get_astar_limit()
        self.setup_resource_cells()
        # self.setup_prospective_citytile_weights()
        self.setup_potential_city_cells()

    def confirm_commands(self, u, c):
        if u.can_act():  # Avoids warnings about units not able to act even when acting to stay still.
            self.set_commands.append(get_command_from_action(u, self.prospective_actions[u]))
            self.set_actions[u] = self.prospective_actions[u]
        self.g.map.set_cells[u] = c

    def set_nonacting_workers(self):
        nonactable_worker_units = [u for u in self.player.units if u.is_worker() and not u.can_act()]
        for unit in nonactable_worker_units:
            unit.log.action = 'c'
            unit.log.cell_next = pos2cell(unit.pos)
            if pos2cell(unit.pos).citytile is None:
                self.prospective_actions[unit] = 'c'
                self.confirm_commands(unit, pos2cell(unit.pos))

    def set_transfer_commands(self):
        for u in self.player.units:
            recipiant, cell = None, None
            if u.is_worker() and u.can_act:
                cell = pos2cell(u.pos)
                if cell.resource:
                    adj_units = [c.unit for c in self.g.map.get_adjacent_cells(cell)
                                 if c.unit is not None and c.unit in self.player.units and c.resource is None and c.citytile is None]
                    if len(adj_units) > 0:
                        recipiant = min(adj_units, key=lambda u: u.cargo.sum_total())
            if recipiant:
                self.set_commands.append(u.transfer(recipiant.id, cell.resource.type, u.cargo[cell.resource.type]))



    def get_max_safe_distance_for_unit(self, unit):
        """Consider if unit can survive the next night cycle"""
        current_resource_type = pos2cell(unit.pos).resource.type if pos2cell(
            unit.pos).resource is not None else 'NA'
        # Assume at most unit will traverse 2 additional steps and harvest along the way
        est_cargo = unit.cargo.sum_total() + self.resource2unitsperturn[current_resource_type] * 2
        initial_distance_covered_in_light = max(0, clock.time_to_night() + 1) // 2
        distance = initial_distance_covered_in_light
        while est_cargo > 0:
            if est_cargo > 40:
                est_cargo -= 40
                distance += 10 + 30
            else:
                nights_can_survive = est_cargo // 4  # 4 cargo spent per night
                distance += nights_can_survive // 4 # 1 move + 3 cooldown waits
                est_cargo = 0
        return distance

    def set_log_values(self):
        for unit in self.player.units:
            unit.log.max_safe_distance = self.get_max_safe_distance_for_unit(unit)

    def zone_debug(self):
        len(self.g.map.zones)
        for z in self.g.map.zones:
            self.set_commands.append(annotate.circle(z.centroid.x, z.centroid.y))
            # if len(z.player_citytiles) > 0:
            #     c = z.player_citytiles[0]
            #     self.set_commands.append(annotate.circle(c.pos.x, c.pos.y))
            # self.set_commands.append(annotate.line(z.centroid.x, z.centroid.y, self.g.players_initial_positions[self.g.id].x, self.g.players_initial_positions[self.g.id].y))

    def get_actions(self, g):
        """
        Changelog
            - go to build if anticipate meeting 100 cargo
            - weighted new builds adj resource much higher
            - assign task considers expiration and fuel efficiency
            - weight resource gather spots by fuel adjusted values, + resource edges.
        Issues
        Next
            - LSS harvest spots
            - if I've walled off resource, remove it from gather spots?
            - assign Zones() to contiguious resources
                - with centroid?
                - limit workers to Zones
                - go to nearest unsaturated zone
        """
        turn = g.turn
        self.can_unit_survive_to_cell.cache_clear()
        self.IGNORE_COAL = self.player.research_points <= map_height_params[self.g.map_height]['ignore_coal_limit']
        self.IGNORE_URANIUM = self.player.research_points <= map_height_params[self.g.map_height]['ignore_uranium_limit']
        self.set_commands = []
        self.zone_debug()
        self.num_cities = len(self.player.cities)
        self.num_workers = len([u for u in self.player.units if u.is_worker()])
        self.generate_stats()
        # self.map_workers_to_cells()
        self.set_builders: List[CityTile] = []
        self.set_research_and_build_commands()
        self.set_log_values()
        # self.produce_workers()
        self.reserved_cells: Dict[Cell] = {}
        units2prospective_cell: Dict[Unit] = {}
        self.set_actions: Dict[Unit] = {}
        self.g.map.set_cells: Dict[Unit] = {}
        self.astar = Astar(self.g.map, g.turn)
        self.zone_units()
        self.prospective_actions: Dict[Unit] = {}
        # Determine unit actions
        self.set_nonacting_workers()
        self.set_transfer_commands()
        actable_worker_units = [u for u in self.player.units if u.is_worker() and u.can_act()]
        # Sort to prioritize
        #   units on a CT
        #   units not near resources
        actable_worker_units = sorted(
            actable_worker_units, key=lambda u: (pos2cell(u.pos).citytile is None,
                                                 any([c.resource is not None for c in
                                                      (self.g.map.get_adjacent_cells(pos2cell(u.pos)) | {pos2cell(u.pos)})
                                                      ]))
        )
        action_iter = 0
        # One time task determination. This is not dependant on set actions of other workers.
        for unit in actable_worker_units:
            task, cell_target, zone = self.determine_task_and_cell_zone(unit)
            if task == Task.GATHER and zone is not None:
                zone.assigned_gather_cells.append(cell_target)
            unit.log.task = task
            unit.log.cell_target = cell_target

        while len(self.set_actions) < len(actable_worker_units):
            action_iter += 1
            if action_iter > 24:
                raise Exception(f"action resolution iteration > 24 - probable infinite loop")
            unassigned_worker_units = [u for u in actable_worker_units if u not in self.set_actions]
            self.prospective_actions = {}
            units2prospective_cell = {}
            for unit in unassigned_worker_units:
                action, cell_next = self.determine_action_for_cell(unit, unit.log.task, unit.log.cell_target)
                self.prospective_actions[unit] = action
                units2prospective_cell[unit] = cell_next
                # Update log
                unit.log.action = action
                unit.log.cell_next = cell_next

            # ACTION CONFLICT RESOLUTION
            # Confirm non-conflicting actions. Record set actions in ship log to keep track of
            # how many ships actions are finalized. Resolve actions outwards from shipyards.
            cell2units = group_units_by_requested_cells(units2prospective_cell)
            for cell, units in cell2units.items():
                if cell.citytile is None:  # Give spot to highest priority ship
                    unit = max(units, key=lambda u: pos2cell(u.pos).citytile is not None)
                    self.confirm_commands(unit, cell)
                else:
                    for unit in units:
                        self.confirm_commands(unit, cell)

        # Annotations
        # for unit in self.player.units:
        #     if unit.log.zone_closest is not None:
        #         z = unit.log.zone_assigned if unit.log.zone_assigned else unit.log.zone_closest
        #         up = unit.log.cell_next.pos if unit.log.cell_next.pos else unit.pos
        #         self.set_commands.append(annotate.line(up.x, up.y, z.centroid.x, z.centroid.y))
        return self.set_commands


def agent(obs, config):
    global game, myagent, log
    # Initalize game else update
    if obs.step == 0:
        game = Game(obs)
        myagent = MyAgent(game)
        log = Log()
    else:
        game.update(obs)
    print(f'Turn:{obs.step}', file=sys.stderr)
    actions = myagent.get_actions(game)
    return actions
