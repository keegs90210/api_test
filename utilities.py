from typing import List
import simpy

def create_container(environment, capacity: int):
    return simpy.Container(environment, capacity=max(int(capacity), 1))

# Determine type of ore
def determine_default_ore(reef_capacity, waste_capacity) -> str:
    if reef_capacity > 0:
        return 'reef'
    if waste_capacity > 0:
        return 'waste'
    return None


# Determine rest position
def determine_rest_position(location) -> list:
    if isinstance(location, list):
        return location
    else:
        return [0, 0, 0]


# return on or off status code
def default_status(state: str) -> List[bool]:
    if state == 'on':
        return [True, False, False, False]
    else:
        return [False, False, False, False]  # off status code


# determine capacity based off of mix type and ore type
def determine_capacity(ore_type, mix_type, reef_capacity, waste_capacity):
    if mix_type == 'SEPARATE':
        if ore_type == 'reef':
            return reef_capacity
        else:
            return waste_capacity
    else:
        return reef_capacity + waste_capacity


# determine the appropriate level based off of mix type and ore type 
def determine_level(ore_type, mix_type, reef_capacity, reef_level, waste_level):
    if mix_type == 'SEPARATE' and ore_type != 'mixed':
        if ore_type == 'reef' and reef_capacity > 1:
            return reef_level
        else:
            return waste_level
    else:
        return reef_level + waste_level


def get_priority_of_loco_on_resource(resource):
    # Check for users and get the highest priority (lowest number)
    if resource.resource.users:
        users_priority = min(request.priority for request in resource.resource.users)
    else:
        users_priority = float('inf')  # Set to infinity if no users

    # Check for queued requests and get the highest priority
    # print(len(resource.resource.queue))
    if resource.resource.queue:
        queue_priority = min(request.priority for request in resource.resource.queue)
    else:
        queue_priority = float('inf')  # Set to infinity if no queue

    # Return the highest priority (lowest number)
    return min(users_priority, queue_priority)


def determine_loco_priority(minute, loco_type, direction, priority_schedule) -> int:
    if loco_type == 'ore':
        if direction == 'to_shaft':
            return int(priority_schedule[priority_schedule['Minute'] <= minute]['Ore to shaft'].values[-1])
        else:
            return int(priority_schedule[priority_schedule['Minute'] <= minute]['Ore from shaft'].values[-1])
    elif loco_type == 'personnel':
        if direction == 'to_shaft':
            return int(priority_schedule[priority_schedule['Minute'] <= minute]['Personnel to shaft'].values[-1])
        else:
            return int(priority_schedule[priority_schedule['Minute'] <= minute]['Personnel from shaft'].values[-1])
    elif loco_type == 'material':
        if direction == 'to_shaft':
            return int(priority_schedule[priority_schedule['Minute'] <= minute]['Material to shaft'].values[-1])
        else:
            return int(priority_schedule[priority_schedule['Minute'] <= minute]['Material from shaft'].values[-1])


def get_ore_value(minute: int, to_shaft: bool) -> int:
    """
    Determine ore movement value based on time and direction.
    """
    hour = minute // 60
    return 1 if (hour % 2 == 0 and to_shaft) else \
        2 if (hour % 2 == 0 and not to_shaft) else \
            3 if to_shaft else 4

def get_personnel_value(minute: int, to_shaft: bool) -> int:
    """
    Determine personnel movement value based on time and direction.
    """
    hour = minute // 60
    if hour % 2 != 0:
        return 5 if to_shaft else 6
    elif hour % 4 == 1:
        return 1 if to_shaft else 2
    else:
        return 3 if to_shaft else 4

def get_material_value(minute: int, to_shaft: bool) -> int:
    """
    Determine material movement value based on time and direction.
    """
    hour = minute // 60
    if hour % 2 == 0:
        return 4 if to_shaft else 3
    elif hour % 4 == 2:
        return 6 if to_shaft else 5
    else:
        return 2 if to_shaft else 1
