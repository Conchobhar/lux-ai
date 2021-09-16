import math, sys
from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate

DIRECTIONS = Constants.DIRECTIONS
g = None


def determine_research():
    pass


def produce_workers():
    pass


def get_actions(g):
    
    actions = []
    player = g.players[g.id]
    opponent = g.players[(g.id + 1) % 2]
    width, height = g.map.width, g.map.height
    
    determine_research()
    produce_workers()

    resource_cells: list[Cell] = []
    for y in range(height):
        for x in range(width):
            cell = g.map.get_cell(x, y)
            if cell.has_resource():
                resource_cells.append(cell)

    # Determine unit actions
    for unit in player.units:
        if unit.is_worker() and unit.can_act():
            closest_dist = math.inf
            closest_resource_tile = None
            if unit.get_cargo_space_left() > 0:
                # if the unit is a worker and we have space in cargo, find the nearest resource tile and try to mine it
                for cell in resource_cells:
                    if cell.resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal(): continue
                    if cell.resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium(): continue
                    dist = cell.pos.distance_to(unit.pos)
                    if dist < closest_dist:
                        closest_dist = dist
                        closest_resource_tile = cell
                if closest_resource_tile is not None:
                    actions.append(unit.move(unit.pos.direction_to(closest_resource_tile.pos)))
            else:
                # if unit is a worker and there is no cargo space left, and we have cities, lets return to them
                if len(player.cities) > 0:
                    closest_dist = math.inf
                    closest_city_tile = None
                    for k, city in player.cities.items():
                        for city_tile in city.citytiles:
                            dist = city_tile.pos.distance_to(unit.pos)
                            if dist < closest_dist:
                                closest_dist = dist
                                closest_city_tile = city_tile
                    if closest_city_tile is not None:
                        move_dir = unit.pos.direction_to(closest_city_tile.pos)
                        actions.append(unit.move(move_dir))

    # you can add debug annotations using the functions in the annotate object
    # actions.append(annotate.circle(0, 0))
    
    return actions


def agent(obs, config):
    global g
    # Initalize game else update
    if obs.step == 0:
        g = Game(obs)
        # g.update(observation["updates"][2:])
        # g.id = observation.player
    else:
        g.update(obs.updates)
    actions = get_actions(g)
    return actions
