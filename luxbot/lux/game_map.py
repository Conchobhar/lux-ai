import heapq
from collections import deque
from typing import List, Set, Iterator, Dict, Deque

from .constants import Constants

DIRECTIONS = Constants.DIRECTIONS
RESOURCE_TYPES = Constants.RESOURCE_TYPES


class Resource:
    def __init__(self, r_type: str, amount: int):
        self.type = r_type
        self.amount = amount

    def __repr__(self):
        return f"{self.type} {self.amount}"


class Cell:
    def __init__(self, x, y):
        self.pos = Position(x, y)
        self.resource: Resource = None
        self.citytile = None
        self.unit = None
        self.road = 0
        self.zone: MapZone = None

    def __repr__(self) -> str:
        return f"C({self.pos} R:{self.resource} CT: {self.citytile})"

    def has_resource(self):
        return self.resource is not None and self.resource.amount > 0

    def has_city_tile(self):
        return self.citytile is not None


class Position:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __sub__(self, pos: 'Position') -> int:
        return abs(pos.x - self.x) + abs(pos.y - self.y)

    def distance_to(self, pos: 'Position', axis=None):
        """
        Returns Manhattan (L1/grid) distance to pos.
        If axis specified, only consider distance along it.
        """
        if axis == 'x':
            return abs(self.x - pos.x)
        elif axis == 'y':
            return abs(self.y - pos.y)
        else:
            return self - pos

    def is_adjacent(self, pos: 'Position'):
        return (self - pos) <= 1

    def __eq__(self, pos: 'Position') -> bool:
        return self.x == pos.x and self.y == pos.y

    def equals(self, pos: 'Position'):
        return self == pos

    def translate(self, direction, units) -> 'Position':
        if direction == DIRECTIONS.NORTH:
            return Position(self.x, self.y - units)
        elif direction == DIRECTIONS.EAST:
            return Position(self.x + units, self.y)
        elif direction == DIRECTIONS.SOUTH:
            return Position(self.x, self.y + units)
        elif direction == DIRECTIONS.WEST:
            return Position(self.x - units, self.y)
        elif direction == DIRECTIONS.CENTER:
            return Position(self.x, self.y)

    def __hash__(self):
        return (str(self.x) + str(self.y)).__hash__()

    def direction_to(self, target_pos: 'Position') -> DIRECTIONS:
        """
        Return closest position to target_pos from this position
        """
        check_dirs = [
            DIRECTIONS.NORTH,
            DIRECTIONS.EAST,
            DIRECTIONS.SOUTH,
            DIRECTIONS.WEST,
        ]
        closest_dist = self.distance_to(target_pos)
        closest_dir = DIRECTIONS.CENTER
        for direction in check_dirs:
            newpos = self.translate(direction, 1)
            dist = target_pos.distance_to(newpos)
            if dist < closest_dist:
                closest_dir = direction
                closest_dist = dist
        return closest_dir

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"

    def __repr__(self) -> str:
        return self.__str__()

    # def __cmp__(self, other):
    #     return


class MapZone:
    """Contiguious region of a single resources and immediately adjacent cititiles and vacant cells.
        - Centroid is a Position() estimate of the zones centre. It may not lie on a resource
        - Distance is from the original players starting citytile
        - MapZones may share cititiles and vacent cells.
    """

    def __init__(self, zone_id, zone_cells, resource_type, player_id, player_initial_position, game_map):
        self.zone_id = str(zone_id)
        self.player_id = player_id
        self.resource_type = resource_type
        self.centroid: Position = None
        self.distance = None
        self.cells: List[Cell] = []
        self.perimeter_cells: List[Cell] = []
        self.resource_cells: List[Cell] = []
        self.resource_cells_adj_ct: List[Cell] = []
        self.resource_cells_not_adj_ct: List[Cell] = []
        self.vacant_cells: List[Cell] = []
        self.vacant_cells_no_adj_player_ct: List[Cell] = []
        self.vacant_cells_no_adj_player_: List[Cell] = []
        self.player_citytiles: List[Cell] = []
        self.player_citytiles_with_adj_opponent_unit: List[Cell] = []
        self.opponent_citytiles: List[Cell] = []
        self.player_initial_position = player_initial_position
        self.game_map = game_map
        self.create_from_cells(zone_cells)
        self.assigned_gather_cells = []
        self.assigned_units = []
        self.opponent_units = []

    def __repr__(self):
        return f"Z({self.zone_id}, {self.centroid})"

    def __hash__(self):
        return self.zone_id.__hash__()

    @property
    def capacity(self):
        return max(1, len(self.resource_cells) // 4) + len(self.opponent_units)

    @property
    def is_enclaved(self):
        return len(self.vacant_cells) == 0

    @property
    def is_enclaved_by_opponent(self):
        return self.is_enclaved and (len(self.player_citytiles) == 0)

    @property
    def is_contested(self):
        return len(self.opponent_citytiles) > 0 or len(self.opponent_units) > 0   # and (len(self.opponent_citytiles) - len(self.player_citytiles)) > (len(self.vacant_cells) // 2)

    @property
    def saturation(self):
        return (len(self.assigned_units)) / self.capacity

    @property
    def is_saturated(self):
        return self.saturation >= 1

    @property
    def remaining_capacity(self):
        return max(0, self.capacity - len(self.assigned_units))

    def is_unit_assignable(self, unit: 'Unit'):
        return (not self.is_enclaved) or (self.game_map.get_cell_by_pos(unit.pos) in self.cells)

    # def get_unassigned_gather_cells(self):
    #     cell_groups = [self.vacant_cells, self.player_citytiles_with_adj_opponent_unit, self.resource_cells_adj_ct,
    #      self.resource_cells_not_adj_ct, self.player_citytiles]
    #     return [c for cg in cell_groups for c in cg if c not in self.assigned_gather_cells]

    def create_from_cells(self, cells):
        self.cells = cells
        for c in cells:
            c.zone = self
            if c.resource:
                self.resource_cells.append(c)
                if any([adj.citytile is not None for adj in self.game_map.get_adjacent_cells(c)]):
                    self.resource_cells_adj_ct.append(c)
                else:
                    self.resource_cells_not_adj_ct.append(c)
            elif c.citytile:
                c.citytile.zone = self
                if c.citytile.team == self.player_id:
                    self.player_citytiles.append(c)
                    if any([adj.unit is not None and adj.unit.team != self.player_id for adj in
                            self.game_map.get_adjacent_cells(c)]):
                        self.player_citytiles_with_adj_opponent_unit.append(c)
                else:
                    self.opponent_citytiles.append(c)
            else:
                if all([((adj.citytile is None) or (adj.citytile.team != self.player_id))
                        for adj in
                        self.game_map.get_adjacent_cells(c)]):
                    self.vacant_cells_no_adj_player_ct.append(c)
                self.vacant_cells.append(c)
        # Determine perimeter cells
        for c in (self.vacant_cells + self.player_citytiles + self.opponent_citytiles):
            for adj in self.game_map.get_adjacent_cells(c):
                if adj not in self.cells:
                    self.perimeter_cells.append(c)

        self.centroid = calculate_centroid(self.resource_cells)
        self.distance = self.centroid.distance_to(self.player_initial_position)

    # def update_with_opponent_units(self, units_cells):
    #     self.present_opponent_units = [u for u in units if ]


class GameMap:
    def __init__(self, width, height):
        self.height = height
        self.width = width
        self.map: List[List[Cell]] = [None] * height
        for y in range(0, self.height):
            self.map[y] = [None] * width
            for x in range(0, self.width):
                self.map[y][x] = Cell(x, y)
        self.zones: List[MapZone] = []
        self.set_cells: Dict['Unit', Cell] = {}  # Keep track of cells assigned by other units

    def get_cell_by_pos(self, pos) -> Cell:
        return self.map[pos.y][pos.x]

    def get_cell(self, x, y) -> Cell:
        return self.map[y][x]

    def __iter__(self) -> Iterator[Cell]:
        for y in range(self.height):
            for x in range(self.width):
                yield self.get_cell(x, y)

    def is_valid_position(self, pos: Position) -> bool:
        return 0 <= pos.x < self.width and 0 <= pos.y < self.height

    def get_adjacent_cells(self, cell: Cell, avoid_opponent_ct: bool = False, avoid_set_cells: bool = False,
                           avoid_player_ct_on_wood: bool = False) -> Set[Cell]:
        deltas = (
            DIRECTIONS.NORTH,
            DIRECTIONS.EAST,
            DIRECTIONS.SOUTH,
            DIRECTIONS.WEST,
        )
        positions = [cell.pos.translate(d, 1) for d in deltas]
        cells = set()
        avoid_opponent_ct_flag, avoid_set_cells_flag, avoid_player_ct_on_wood_flag = False, False, False
        for cell in {self.get_cell_by_pos(p) for p in positions if self.is_valid_position(p)}:
            if avoid_opponent_ct:
                avoid_opponent_ct_flag = cell.citytile is not None and not cell.citytile.is_player_citytile()
            if avoid_set_cells:
                avoid_set_cells_flag = cell in self.set_cells.values()
            if avoid_player_ct_on_wood:
                any_adj_cells_on_wood = any([(ct.resource and ct.resource.type == RESOURCE_TYPES.WOOD)
                                             for ct in self.get_adjacent_cells(cell)])
                avoid_player_ct_on_wood_flag = cell.citytile is not None and cell.citytile.is_player_citytile() and any_adj_cells_on_wood
            if not avoid_set_cells_flag and not avoid_opponent_ct_flag and not avoid_player_ct_on_wood_flag:  # Both flags should be false if adding to set.
                cells.add(cell)
        return cells

    def get_transverse_cells(self, cell: Cell) -> Set[Cell]:
        deltas = (
            (DIRECTIONS.NORTH, DIRECTIONS.EAST),
            (DIRECTIONS.SOUTH, DIRECTIONS.EAST),
            (DIRECTIONS.SOUTH, DIRECTIONS.WEST),
            (DIRECTIONS.NORTH, DIRECTIONS.WEST),
        )
        positions = []
        pos = cell.pos
        for dpair in deltas:
            for d in dpair:
                pos = pos.translate(d, 1)
        positions.append(pos)
        return {self.get_cell_by_pos(p) for p in positions if self.is_valid_position(p)}

    def setResource(self, r_type, x, y, amount):
        """
        do not use this function, this is for internal tracking of state
        """
        cell = self.get_cell(x, y)
        cell.resource = Resource(r_type, amount)

    def explore_from_cell(self, cell: Cell, resource_type):
        """Recursively explore cells, ignoring those already explored and building the explored list while traversing.
        Each call
            - Marks the argument cell as explored
            - Appends cell to collection if applicable
            - Begins further exploration if adjacent cells are applicable
        """
        cells = set()
        cells |= {cell, }
        self.assigned_cells |= {cell, }
        for c in self.get_adjacent_cells(cell):
            # Explore resource cells of the same type, not yet explored.
            if c.resource and c.resource.type == resource_type and c not in self.assigned_cells:
                cells |= self.explore_from_cell(c, resource_type)
            else:  # Ignore other resource types
                # self.explored_cells |= {c, }
                pass
                # TODO - Might change behaviour here later.
                if c.citytile:  # Collect citytiles adjacent resource, but do not explore further from them
                    cells |= {c, }
                elif not c.resource:  # Collect empty adjacent tiles
                    cells |= {c, }
        return cells

    assigned_cells = set()

    restype2order = {
        RESOURCE_TYPES.WOOD: 0,
        RESOURCE_TYPES.COAL: 1,
        RESOURCE_TYPES.URANIUM: 2,
    }

    def generate_zones(self, player_id, player_initial_position):
        """Generate list of zones at the start of each turn.
        List is sorted by distance to players initial turn 0 position descending.
        """
        zone_id_counter = 0
        zones = []
        self.assigned_cells = set()
        all_resource_cells = set([cell for cell in self if cell.resource])
        while len(self.assigned_cells) < len(all_resource_cells):
            to_assign = list(all_resource_cells - self.assigned_cells)
            next_cell = to_assign[0]
            zone_cells = self.explore_from_cell(next_cell,
                                                resource_type=next_cell.resource.type)  # search all adjacent cells if not_already_explored and (is_resource or is_myct or is enemy_ct)
            zone = MapZone(zone_id_counter, zone_cells, next_cell.resource.type, player_id,
                           player_initial_position, self)  # Zone IDs not guaranteed to translate across turns...
            zone_id_counter += 1
            zones.append(zone)
        # Sort zones by resource type readiness, then distance to player origin.
        # This is important for zone assignment to units later.
        self.zones = sorted(zones,
                            key=lambda z: (self.restype2order[z.resource_type],
                                           z.centroid.distance_to(z.player_initial_position)))


def calculate_centroid(cells) -> Position:
    xs, ys, n = 0, 0, len(cells)
    for cell in cells:
        xs += cell.pos.x
        ys += cell.pos.y
    return Position(xs // n, ys // n)


class Node:

    def __init__(self, cell: Cell):
        self.cell: Cell = cell
        self.parent: Node = None
        self.H = 0
        self.G = 0

    @property
    def F(self):
        return self.H + self.G

    def get_path(self) -> Deque[Cell]:
        """Follow trail of parent nodes to recreate path (excluding initial node)"""
        path = deque()
        node = self
        while node.parent:
            path.appendleft(node.cell)
            node = node.parent
        return path

    def __eq__(self, other: 'Node'):
        return self.cell == other.cell

    def __hash__(self):
        return self.cell.__hash__()

    def __repr__(self):
        return f"N({self.G}, {self.cell.__repr__()}"


class Astar:

    def __init__(self, game_map: GameMap, turn):
        # Open and closed sets are really key'd by the Cell the Node represents
        self.game_map: GameMap = game_map
        self.open: Dict[Node, Node] = dict()
        self.closed: Dict[Node, Node] = dict()
        self.goal: Node = None
        self.unit: 'Unit' = None
        self.zone: MapZone = None
        self.turn = turn  # Change path finding behaviour at later stages
        self.SUSTAINABLE_WOOD_TURN_LIMIT = 280

    @staticmethod
    def heuristic(node_current: Node, node_goal: Node):
        """L1 distance"""
        return node_current.cell.pos.distance_to(node_goal.cell.pos)

    def cost_to_traverse(self, cell: Cell):
        """Return a cost heuristic for how valuable this cell is as part of a path.
            - Default 2 for moving 1 cell and resting
            - 0.5 if unit will harvest. All else equal, move along resources.
            - Large penalty for crossing a CT that will harvest wood

        Ideally we would have a virtual unit and clock here and estimate if it would expire without resources
        """
        will_unit_harvest = (cell.resource is not None) or any(
            [adj.resource is not None for adj in self.game_map.get_adjacent_cells(cell)])
        citytile_cost = 0
        any_adj_cells_are_wood = any([(ct.resource and ct.resource.type == RESOURCE_TYPES.WOOD) for ct in
                                      self.game_map.get_adjacent_cells(cell)])
        if cell.citytile and any_adj_cells_are_wood:
            citytile_cost = 10
        return (1 if will_unit_harvest else 2) + citytile_cost

    def search(self, cell_start: Cell, cell_goal: Cell, unit: 'Unit', limit=None) -> Deque[Cell]:
        """Search entrypoint. Initalise nodes.
        limit will reduce path search until only a limit of G has been covered."""
        self.goal = Node(cell_goal)
        self.open = dict()
        self.closed = dict()
        self.unit = unit
        self.zone: MapZone = self.unit.log.zone_assigned if self.unit.log.zone_assigned else self.unit.log.zone_closest
        node_current = Node(cell_start)
        node_current.H = cell_start.pos.distance_to(cell_goal.pos)
        return self._search(node_current, self.goal, limit=limit)

    def _search(self, current_node: Node, goal_node: Node, limit=8) -> Deque[Cell]:
        self.open[current_node] = current_node
        first_cell = current_node.cell
        avoid_player_ct_on_wood = self.zone is not None and (
                self.game_map.get_cell_by_pos(self.unit.pos) not in self.zone.cells
                and self.zone.resource_type == RESOURCE_TYPES.WOOD)
        while current_node != goal_node:
            if len(self.open) == 0 or (limit is not None and current_node.G > limit):
                # If no complete path is found, we return the best incomplete path from the current node
                return current_node.get_path()
            # Get next best node
            current_node = min(self.open, key=lambda node: node.F)
            del self.open[current_node]
            self.closed[current_node] = current_node
            # Consider neighbours
            avoid_set_cells = current_node.cell == first_cell  # Only avoid cells set this turn for other workers, if it is adjacent the origin cell.
            avoid_opponent_ct = not (self.zone is not None and self.zone.is_enclaved) and current_node.G < 5  # Ignore opponent CTs at long distances
            for adj_cell in self.game_map.get_adjacent_cells(current_node.cell, avoid_opponent_ct=avoid_opponent_ct,
                                                             avoid_set_cells=avoid_set_cells,
                                                             avoid_player_ct_on_wood=avoid_player_ct_on_wood):
                adj_node = Node(adj_cell)
                adj_node.parent = current_node
                # H - estimate cost heuristic to get to the goal cell from here
                adj_node.H = self.heuristic(adj_node, goal_node)
                # G - actual acruing cost to get to the current cell from the start
                adj_node.G = current_node.G + self.cost_to_traverse(adj_cell)
                # If adj node was previously stored in open, and adj node has a lower F score, replace it
                if adj_node in self.open:
                    prev_node = self.open[adj_node]
                    if prev_node.F > adj_node.F:
                        self.open[adj_node] = adj_node
                # If adj node has not been recorded in either open or closed, add to open
                if adj_node not in self.open and adj_node not in self.closed:
                    self.open[adj_node] = adj_node
        return current_node.get_path()
