
import simpy

from utilities import *
import math
import numpy as np

class RailResource:
    def __init__(self, env, name, capacity, location):
        self.env = env
        self.name = name
        self.capacity = capacity
        self.position = location
        if capacity != 0:
            self.resource = simpy.PriorityResource(env, capacity=capacity)
        else:
            self.resource = simpy.PriorityResource(env, capacity=1)
            self.env.process(self.auto_request())

    def request(self, priority=0):
        return self.resource.request(priority=priority)

    def release(self, req):
        return self.resource.release(req)
    
    def auto_request(self):
        with self.request(priority=0) as req:
            yield req


class RailSegment:
    def __init__(self, env, name, total_length, loco_length, speed_factor, capacity, bypass_capacity, locations, bypass_location):
        self.env = env
        self.name = name
        self.length = total_length
        self.loco_length = loco_length
        self.speed_factor = speed_factor
        self.bypass_capacity = bypass_capacity
        self.results = []
        self.cumulative = 0
        self.locations = locations
        self.bypass_location = bypass_location

        # Compute the number of smaller segments based on loco_length
        self.num_resources = math.ceil(total_length / loco_length)

        # Compute the cumulative distances along the path
        self.cumulative_distances = self.compute_cumulative_distances()
        self.segment_length = self.cumulative_distances[-1] / self.num_resources

        # Interpolate positions along the path
        self.positions = self.interpolate_positions()

        self.resources = [RailResource(env, f"{name}_Part_{i}", capacity, self.positions[i]) for i in range(self.num_resources)]
        self.bypass = RailResource(env, f"{name}_Bypass", bypass_capacity, self.bypass_location)

    def compute_cumulative_distances(self):
        cumulative_distances = [0]
        for i in range(1, len(self.locations)):
            prev_point = self.locations[i - 1]
            curr_point = self.locations[i]
            distance = np.linalg.norm(np.array(curr_point) - np.array(prev_point))
            cumulative_distances.append(cumulative_distances[-1] + distance)
        return cumulative_distances

    def interpolate_positions(self):
        positions = []
        total_path_length = self.cumulative_distances[-1]
        for i in range(self.num_resources):
            target_distance = i * self.segment_length
            # Find the two points between which this segment falls
            for j in range(1, len(self.cumulative_distances)):
                if self.cumulative_distances[j] >= target_distance:
                    t = (target_distance - self.cumulative_distances[j - 1]) / (self.cumulative_distances[j] - self.cumulative_distances[j - 1])
                    interpolated_position = [
                        self.locations[j - 1][k] + t * (self.locations[j][k] - self.locations[j - 1][k])
                        for k in range(3)
                    ]
                    positions.append(interpolated_position)
                    break
        return positions
    
    def tracking(self):
        while True:
            yield self.env.timeout(1)
            utilisation = 0
            for resource in self.resources:
                temp = resource.resource.count / resource.resource.capacity
                utilisation = max(utilisation,temp)
            if utilisation > 0:
                self.cumulative += 1
            self.results.append([self.env.now, utilisation, self.cumulative])


def move_on_rail(env, direction, resource_queue, queue_index, minute, material, velocity, rail_segments_dict, equipment,priority_schedule, previous_req = None):
    if direction == 'from_shaft':
        segment_pos = 0
        req1 = None
        backward = 0
        while segment_pos < len(resource_queue[queue_index]):
            rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
            resource_pos = 0
            backward = 0
            while resource_pos < len(rail_segment.resources):
                resource = rail_segment.resources[resource_pos]
                if previous_req:
                    if resource.resource == previous_req.resource:
                        resource_pos += 1
                        yield env.timeout(rail_segment.loco_length / velocity / rail_segment.speed_factor)
                        continue
                _, minute = divmod(env.now, 24*60)
                priority = determine_loco_priority(minute, material, 'from_shaft')
                backward = 0
                # Check if the resource is occupied by another loco
                if resource.resource.count >= resource.capacity:
                    other_loco_priority = get_priority_of_loco_on_resource(resource)
                    if resource_pos > 0:
                        current_resource = rail_segment.resources[resource_pos - 1]
                        current_resource_priority = get_priority_of_loco_on_resource(current_resource)
                    else:
                        if segment_pos > 0:
                            current_resource = rail_segments_dict[resource_queue[queue_index][segment_pos - 1]].resources[-1]
                            current_resource_priority = get_priority_of_loco_on_resource(current_resource)
                        else:
                            current_resource_priority = other_loco_priority
                    if (other_loco_priority < priority) or ((other_loco_priority == priority) and current_resource_priority < priority):
                        if rail_segment.bypass.resource.count < rail_segment.bypass.capacity and (resource_pos == 0) and req1 is None:
                            req1 = rail_segment.bypass.request()
                            test_result = yield req1 
                            if previous_req:
                                yield previous_req.resource.release(previous_req)
                                previous_req = None
                            backward = 0
                            resource_pos = 0
                            yield env.timeout(0.5)
                        elif req1 is None:
                            backward = 1
                        else:
                            backward = 0
                            yield env.timeout(0.5)

                if backward == 1:
                    if resource_pos > 1:
                        resource_pos -= 2
                        priority = min(other_loco_priority,current_resource_priority)
                    elif resource_pos > 0: 
                        if segment_pos > 0:
                            segment_pos -= 1
                            rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                            resource_pos = len(rail_segment.resources) - 1
                            priority = min(other_loco_priority,current_resource_priority)
                        else:
                            segment_pos = 0
                            rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                            resource_pos = 0
                            if previous_req:
                                yield previous_req.resource.release(previous_req)
                                previous_req = None
                    elif segment_pos > 0:
                        segment_pos -= 1
                        rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                        if len(rail_segment.resources) > 1:
                            resource_pos = len(rail_segment.resources) - 2
                            priority = min(other_loco_priority,current_resource_priority)
                        else:
                            if segment_pos > 0:
                                segment_pos -= 1
                                rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                                resource_pos = len(rail_segment.resources) - 1
                                priority = min(other_loco_priority,current_resource_priority)
                            else:
                                segment_pos = 0
                                rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                                resource_pos = 0
                                if previous_req:
                                    yield previous_req.resource.release(previous_req)
                                    previous_req = None
                    else:
                        segment_pos = 0
                        rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                        resource_pos = 0
                        if previous_req:
                            yield previous_req.resource.release(previous_req)
                            previous_req = None

                resource = rail_segment.resources[resource_pos]
                req = resource.request(priority)
                current_req = req
                test_result = yield req | env.timeout(10)
                if req not in test_result:
                    req.cancel()
                    continue
                equipment.position = resource.position

                if req1:
                    yield req1.resource.release(req1)
                    req1 = None

                if previous_req:
                    yield previous_req.resource.release(previous_req)
                previous_req = current_req

                yield env.timeout(rail_segment.loco_length / velocity / rail_segment.speed_factor)

                resource_pos += 1  # Move to the next resource within the rail_segment

            segment_pos += 1  # Move to the next RailSegment
            
        return previous_req
    else:
        # if local_trip == 80:
        #     pass
        segment_pos = len(resource_queue[queue_index]) - 1
        # previous_req = None  # To keep track of the previous resource request
        req1 = None
        backward = 0

        while segment_pos >= 0:
            rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
            resource_pos = len(rail_segment.resources) - 1
            backward = 0
            while resource_pos >= 0:
                resource = rail_segment.resources[resource_pos]
                if previous_req:
                    if resource.resource == previous_req.resource:
                        yield env.timeout(rail_segment.loco_length / velocity / rail_segment.speed_factor)
                        resource_pos -= 1  # Move to the next resource within the rail_segment
                        continue
                _, minute = divmod(env.now, 24*60)
                priority = determine_loco_priority(minute, material, 'to_shaft',priority_schedule)
                backward = 0

                # Check if the resource is occupied by another loco
                if resource.resource.count >= resource.capacity:
                    other_loco_priority = get_priority_of_loco_on_resource(resource)
                    if resource_pos < len(rail_segment.resources) - 1:
                        current_resource = rail_segment.resources[resource_pos + 1]
                        current_resource_priority = get_priority_of_loco_on_resource(current_resource)
                    else:
                        if segment_pos < len(resource_queue[queue_index]) - 1:
                            current_resource = rail_segments_dict[resource_queue[queue_index][segment_pos + 1]].resources[0]
                            current_resource_priority = get_priority_of_loco_on_resource(current_resource)
                        else:
                            current_resource_priority = other_loco_priority
                    if (other_loco_priority < priority) or ((other_loco_priority == priority) and current_resource_priority < priority):
                        if rail_segment.bypass.resource.count < rail_segment.bypass.capacity and (resource_pos == 0) and req1 is None:
                            req1 = rail_segment.bypass.request()
                            test_result = yield req1 
                            if previous_req:
                                yield previous_req.resource.release(previous_req)
                                previous_req = None
                            backward = 0
                            resource_pos = 0
                            yield env.timeout(0.5)
                        elif req1 is None:
                            backward = 1
                        else:
                            backward = 0
                            yield env.timeout(0.5)

                if backward == 1:
                    priority = min(other_loco_priority,current_resource_priority)
                    if len(rail_segment.resources) - 1 >= resource_pos + 2:
                        resource_pos += 2
                    elif len(rail_segment.resources) - 1 >= resource_pos + 1: 
                        if segment_pos < len(resource_queue[queue_index]) - 1:
                            segment_pos += 1
                            rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                            resource_pos = 0
                        else:
                            segment_pos = len(resource_queue[queue_index]) - 1
                            rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                            resource_pos = len(rail_segment.resources) - 1
                            if previous_req:
                                yield previous_req.resource.release(previous_req)
                                previous_req = None
                    elif segment_pos < len(resource_queue[queue_index]) - 1:
                        segment_pos += 1
                        rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                        if len(rail_segment.resources) > 1:
                            resource_pos = 1
                        else:
                            if segment_pos < len(resource_queue[queue_index]) - 1:
                                segment_pos += 1
                                rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                                resource_pos = 0
                            else:
                                segment_pos = len(resource_queue[queue_index]) - 1
                                rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                                resource_pos = len(rail_segment.resources) - 1
                                if previous_req:
                                    yield previous_req.resource.release(previous_req)
                                    previous_req = None
                    else:
                        segment_pos = len(resource_queue[queue_index]) - 1
                        rail_segment = rail_segments_dict[resource_queue[queue_index][segment_pos]]
                        resource_pos = len(rail_segment.resources) - 1
                        if previous_req:
                            yield previous_req.resource.release(previous_req)
                            previous_req = None

                resource = rail_segment.resources[resource_pos]
                req = resource.request(priority)
                current_req = req
                test_result = yield req | env.timeout(10)
                if req not in test_result:
                    req.cancel()
                    continue
                equipment.position = resource.position

                if req1:
                    yield req1.resource.release(req1)
                    req1 = None

                if previous_req:
                    yield previous_req.resource.release(previous_req)
                previous_req = current_req

                yield env.timeout(rail_segment.loco_length / velocity / rail_segment.speed_factor)

                resource_pos -= 1  # Move to the next resource within the rail_segment

            segment_pos -= 1  # Move to the next RailSegment

        return previous_req
