import math
import random
import numpy as np
import time

from containers import *
from rail_segment import *
from time_base import *


class Stope:
    def __init__(self, env, ton_per_blast, ore_type, blast_1_time, blast_2_time, stope_ore_store, blast_chance, saturday_operation, sunday_operation):
        # Common variables
        self.env = env
        self.saturday_operation = saturday_operation
        self.sunday_operation = sunday_operation

        # Blast-related variables
        self.ton_per_blast = ton_per_blast
        self.ore_type = ore_type
        self.blast_1_time = blast_1_time
        self.blast_2_time = blast_2_time
        self.stope_ore_store = stope_ore_store
        self.blast_chance = blast_chance
        self.stope_capacity = np.max(self.ton_per_blast)

        # State variables
        self.results = []


    def process(self):
        time_to_next_blast = 1
        while True:
            # Wait until the next blast time
            yield self.env.timeout(time_to_next_blast)
            current_time = self.env.now
            day, current_minute = divmod(current_time, 24 * 60)
            week, day_of_week = divmod(day, 7)
            _, week_number = divmod(week, 2)

            minute = current_minute

            # Calculate time to next blast
            if current_minute < self.blast_1_time:
                time_to_next_blast = self.blast_1_time - current_minute
            elif current_minute < self.blast_2_time:
                time_to_next_blast = self.blast_2_time - current_minute
            else:  # If current time is past both blast times, calculate time until next day's first blast
                if self.blast_1_time < self.blast_2_time:
                    time_to_next_blast = (24 * 60 - current_minute) + self.blast_1_time
                else:
                    time_to_next_blast = (24 * 60 - current_minute) + self.blast_2_time

            status = 'off'
            if isinstance(self.ton_per_blast,list):
                status = 'on'
            if day_of_week < 5:
                status = 'on'
            elif (day_of_week == 5 and self.saturday_operation == 'WEEKLY') or (day_of_week == 5 and self.saturday_operation == 'BI-WEEKLY' and week_number == 0):
                status = 'on'
            elif (day_of_week == 6 and self.sunday_operation == 'WEEKLY') or (day_of_week == 6 and self.sunday_operation == 'BI-WEEKLY' and week_number == 0):
                status = 'on'
            if ((minute == self.blast_1_time) or (minute == self.blast_2_time)) and status == 'on':
                # print(random_num)
                if isinstance(self.ton_per_blast,list):
                    daily_ore = self.ton_per_blast[int(day)]
                    random_num = 0
                else:
                    daily_ore = self.ton_per_blast
                    random_num = random.random()
                if (random_num <= self.blast_chance) and (self.stope_ore_store.level() <= 0.05 * self.stope_capacity) and (daily_ore > 0):
                    # print('Blast')
                    yield from self.stope_ore_store.put(daily_ore, self.ore_type)

    def tracking(self):
        while True:
            yield self.env.timeout(1)
            self.results.append([self.env.now, self.stope_ore_store.reef_container.level + self.stope_ore_store.waste_container.level, self.stope_ore_store.reef_container.level, self.stope_ore_store.waste_container.level])


class Winch:
    def __init__(self, env, start_times, end_times, start_times_saturday, end_times_saturday, start_times_sunday, end_times_sunday, saturday_operation, sunday_operation, trip_time, capacity, inlet, outlet, utilisation_profile_df,
          resource_queue, list_of_simulation_resources, rail_segments_dict, workplaces, breakdown_df, repair_df):
        # Common variables
        self.env = env
        self.saturday_operation = saturday_operation
        self.sunday_operation = sunday_operation
        self.inlet = inlet
        self.outlet = outlet
        self.trip_time = trip_time
        self.capacity = capacity
        self.utilisation_profile = utilisation_profile_df['Utilisation [%]']
        self.delay_max = (60 * utilisation_profile_df['Time [hr]'].values[-1] +
                          utilisation_profile_df['Time [minutes]'].values[-1]) / (len(utilisation_profile_df) - 1)
        self.breakdown_profile = breakdown_df
        self.repair_profile = repair_df

        # Timing-related variables
        self.start_times = start_times
        self.end_times = end_times
        self.start_times_saturday = start_times_saturday
        self.end_times_saturday = end_times_saturday
        self.start_times_sunday = start_times_sunday
        self.end_times_sunday = end_times_sunday

        # Resource and breakdown variables
        self.resource_queue = resource_queue
        self.list_of_simulation_resources = list_of_simulation_resources
        self.rail_segments_dict = rail_segments_dict
        self.workplaces = workplaces

        # State variables
        self.status = [False, False, False, False]
        self.results = []
        self.breakdown = False
        self.last_breakdown = 0
        self.last_repair = 0
        self.repair_time = 0
        self.repair_time_start = 0
        self.ore_store = 0
        self.active_time_since_last_repair = 0
        self.repair_time_to_now = 0
        self.request_list = []

    def update(self, list_of_containers, all_components):
        self.list_of_containers_local = list_of_containers
        self.rail_segments_dict = {name: all_components[name] for name in all_components if isinstance(all_components[name], RailSegment)}

    def process(self):
        while True:
            yield self.env.timeout(1)
            day, minute = divmod(self.env.now, 24 * 60)

            status = 'off'  # Check to see if winch is operational
            workday = 'off'
            week, day_of_week = divmod(day, 7)
            _, week_number = divmod(week, 2)
            
            if (day_of_week < 5 or 
            (day_of_week == 5 and (self.saturday_operation == 'WEEKLY' or (self.saturday_operation == 'BI-WEEKLY' and week_number == 0))) or 
            (day_of_week == 6 and (self.sunday_operation == 'WEEKLY' or (self.sunday_operation == 'BI-WEEKLY' and week_number == 0)))):
                workday = 'on'

                            
            if workday == 'on':
                for i in range(len(self.start_times)):
                    if self.start_times[i] > self.end_times[i]:
                        if minute >= self.start_times[i]:
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.start_times[i]) / ((self.end_times[i] + 24 * 60 - self.start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.end_times[i]:
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.start_times[i]) / ((self.end_times[i] + 24 * 60 - self.start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.start_times[i]) and (minute < self.end_times[i]):
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.start_times[i]) / ((self.end_times[i] - self.start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 5:
                for i in range(len(self.start_times_saturday)):
                    if self.start_times_saturday[i] > self.end_times_saturday[i]:
                        if minute >= self.start_times_saturday[i]:
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times_saturday[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.start_times_saturday[i]) / ((self.end_times_saturday[i] + 24 * 60 - self.start_times_saturday[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.end_times_saturday[i]:
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times_saturday[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.start_times_saturday[i]) / ((self.end_times_saturday[i] + 24 * 60 - self.start_times_saturday[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.start_times_saturday[i]) and (minute < self.end_times_saturday[i]):
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times_saturday[i]
                            utilisation_index = min(math.floor(
                                (minute - self.start_times_saturday[i]) / ((self.end_times_saturday[i] - self.start_times_saturday[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 6:
                for i in range(len(self.start_times_sunday)):
                    if self.start_times_sunday[i] > self.end_times_sunday[i]:
                        if minute >= self.start_times_sunday[i]:
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times_sunday[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.start_times_sunday[i]) / ((self.end_times_sunday[i] + 24 * 60 - self.start_times_sunday[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.end_times_sunday[i]:
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times_sunday[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.start_times_sunday[i]) / ((self.end_times_sunday[i] + 24 * 60 - self.start_times_sunday[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.start_times_sunday[i]) and (minute < self.end_times_sunday[i]):
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times_sunday[i]
                            utilisation_index = min(math.floor(
                                (minute - self.start_times_sunday[i]) / ((self.end_times_sunday[i] - self.start_times_sunday[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]

            if status == 'on' and self.breakdown == False:
                random_num = random.random()
                if (self.active_time_since_last_repair - self.last_breakdown) > 0:
                    breakdown_chance = self.breakdown_profile[self.breakdown_profile['Running Hours'] <= ((self.active_time_since_last_repair - self.last_breakdown )/ 60)]['Cumulative Probability of Breakdown'].values[-1]
                else:
                    breakdown_chance = 0
                if random_num <= breakdown_chance and breakdown_chance != 0:
                        self.breakdown = True
                        # print('Breakdown at ' + str(self.env.now))
                        self.last_breakdown = self.active_time_since_last_repair
                        repair_chance = random.random()
                        self.repair_time = self.repair_profile[self.repair_profile['Cumulative Probability of Repair'] >= repair_chance]['Repair Time'].values[0] * 60
                        # print(self.repair_time)
                        self.repair_time_start = sum(row[1] for row in self.results)

            if self.breakdown == True:
                if (self.repair_time_to_now - self.repair_time_start) >= self.repair_time:
                    # print('Repaired at ' + str(self.env.now))
                    self.breakdown = False
                    self.last_repair = sum(self.results[0])

            if (status == 'on') and (self.breakdown == False):
                self.status[0] = True
                self.status[1] = True
                self.status[2] = False
                delay = (100 - utilisation_factor) / 100 * self.delay_max
                if (end_time - minute) > delay:
                    if delay > 0:
                        yield self.env.timeout(delay)
                else:
                    if (end_time - minute - 1) > 0:
                        yield self.env.timeout(end_time - minute - 1)
                    continue
                pull_inlet = 0
                for i, container in enumerate(self.inlet):
                    if self.list_of_containers_local[container].level('mixed') > 0:
                        pull_inlet = i
                        break
                ore = self.capacity

                if self.list_of_containers_local[self.inlet[pull_inlet]].level('mixed') >= ore:  # Take everything less than dump size from inlet
                    ore = ore
                elif self.list_of_containers_local[self.inlet[pull_inlet]].level('mixed') > 0:
                    ore = self.list_of_containers_local[self.inlet[pull_inlet]].level('mixed')
                else:
                    ore = 0
                if ore > 0:
                    self.status[2] = True
                    if len(self.resource_queue[pull_inlet]) == 0:
                        yield self.env.timeout(self.trip_time)
                    for i in range(len(self.resource_queue[pull_inlet])):
                        req = self.resource_segments_dict[self.resource_queue[pull_inlet][i]].request(priority=2)
                        req_store = req
                        if self.resource_queue[pull_inlet][0][:4] == 'L117':
                            pass
                        yield req
                        self.request_list.append(req_store)
                        yield self.env.timeout(self.trip_time / len(self.resource_queue[pull_inlet]))
                    temp_ore_type = yield from self.list_of_containers_local[self.inlet[pull_inlet]].get(ore, 'mixed')
                    self.ore_store += ore
                    yield self.env.timeout(self.trip_time)
                    for req in self.request_list:
                        req.resource.release(req)
                    self.request_list = []
                    yield from self.list_of_containers_local[self.outlet[pull_inlet]].put(ore, temp_ore_type)
            elif status == 'on':
                self.status = default_status(status)
                for req in self.request_list:
                    req.resource.release(req)
                self.request_list = []
            else:
                self.status = default_status(status)
                for req in self.request_list:
                    req.resource.release(req)
                self.request_list = []
                # yield self.env.timeout(4)
                time_to_next_start = get_time_to_next_start(self.env, [self.start_times, self.start_times_saturday, self.start_times_sunday])
                if time_to_next_start > 0:
                    yield self.env.timeout(time_to_next_start)

    def tracking(self):
        while True:
            yield self.env.timeout(1)
            if self.status[0] == True:
                scheduled = 1
            else:
                scheduled = 0
            if self.status[1] == True:
                available = 1
            else:
                available = 0
            if self.status[2] == True:
                active = 1
            else:
                active = 0
            self.results.append([self.env.now, scheduled, available, active, self.ore_store])
            self.ore_store = 0
            self.active_time_since_last_repair += active
            self.repair_time_to_now += scheduled


class Ore_Pass_Link:
    def __init__(self, env, reef_inlet, reef_outlet, waste_inlet, waste_outlet, rate):
        # Common variables
        self.env = env
        self.rate = rate

        # Inlet and outlet variables
        self.reef_inlet = reef_inlet
        self.waste_inlet = waste_inlet
        self.reef_outlet = reef_outlet
        self.waste_outlet = waste_outlet

    def process(self):
        while True:
            yield self.env.timeout(1)
            ore = self.rate
            if self.reef_inlet.check_level('reef') >= ore:  # Take everything less than rate from inlet
                ore = ore
                yield from self.reef_inlet.get(ore, 'reef')
            elif self.reef_inlet.check_level('reef') > 0:
                ore = self.reef_inlet.check_level('reef')
                yield from self.reef_inlet.get(ore, 'reef')
            else:
                ore = 0
            if ore > 0:
                yield from self.reef_outlet.put(ore, 'reef')
            ore = self.rate
            if self.waste_inlet.check_level('waste') >= ore:  # Take everything less than rate from inlet
                ore = ore
                yield from self.waste_inlet.get(ore, 'waste')
            elif self.waste_inlet.check_level('waste') > 0:
                ore = self.waste_inlet.check_level('waste')
                yield from self.waste_inlet.get(ore, 'waste')
            else:
                ore = 0
            if ore > 0:
                yield from self.waste_outlet.put(ore, 'waste')


class Locomotive:
    def __init__(self, env, no_hopper, hopper_capacity, tramming_velocity_full, tramming_velocity_empty, reef_start_times, reef_end_times, waste_start_times, waste_end_times, 
                 saturday_operation, sunday_operation,
                 saturday_reef_start_times, saturday_reef_end_times, saturday_waste_start_times, saturday_waste_end_times,
                 sunday_reef_start_times, sunday_reef_end_times, sunday_waste_start_times, sunday_waste_end_times,
                 loading_time, dumping_time, switching_type, outlet, inlet, inlet_distance,
                 utilisation_profile_df, resource_queue, list_of_simulation_resources, rail_segments_dict,
                 workplaces, breakdown_df, repair_df, location, priority_schedule):
       # Unique variables for Loco
        self.no_hopper = no_hopper
        self.hopper_capacity = hopper_capacity
        self.tramming_velocity_full = tramming_velocity_full
        self.tramming_velocity_empty = tramming_velocity_empty
        self.inlet_distance = inlet_distance
        self.switching_type = switching_type
        self.rest_position = determine_rest_position(location)
        self.position = self.rest_position
        self.priority_schedule = priority_schedule

        # Common variables
        self.env = env
        self.reef_start_times = reef_start_times
        self.reef_end_times = reef_end_times
        self.waste_start_times = waste_start_times
        self.waste_end_times = waste_end_times
        self.saturday_operation = saturday_operation
        self.sunday_operation = sunday_operation
        self.saturday_reef_start_times = saturday_reef_start_times
        self.saturday_reef_end_times = saturday_reef_end_times
        self.saturday_waste_start_times = saturday_waste_start_times
        self.saturday_waste_end_times = saturday_waste_end_times
        self.sunday_reef_start_times = sunday_reef_start_times
        self.sunday_reef_end_times = sunday_reef_end_times
        self.sunday_waste_start_times = sunday_waste_start_times
        self.sunday_waste_end_times = sunday_waste_end_times
        self.loading_time = loading_time
        self.dumping_time = dumping_time
        self.inlet = inlet
        self.outlet = outlet
        self.utilisation_profile = utilisation_profile_df['Utilisation [%]']
        self.delay_max = (60 * utilisation_profile_df['Time [hr]'].values[-1] + utilisation_profile_df['Time [minutes]'].values[-1]) / (len(utilisation_profile_df) - 1)
        self.resource_queue = resource_queue
        self.list_of_simulation_resources = list_of_simulation_resources
        self.rail_segments_dict = rail_segments_dict
        self.workplaces = workplaces
        self.breakdown_profile = breakdown_df
        self.repair_profile = repair_df
        
        # State variables
        self.status = [False, False, False, False]
        self.results = []
        self.breakdown = False
        self.last_breakdown = 0
        self.last_repair = 0
        self.repair_time = 0
        self.repair_time_start = 0
        self.current_ore_type = None
        self.ore_store = 0
        self.active_time_since_last_repair = 0
        self.repair_time_to_now = 0
        self.previous_request = None

    def update(self, list_of_containers, all_components):
        self.list_of_containers = list_of_containers
        self.rail_segments_dict = {name: all_components[name] for name in all_components if isinstance(all_components[name], RailSegment)}

    def process(self):
        while True:
            yield self.env.timeout(1)
            day, minute = divmod(self.env.now, 24 * 60)

            status = 'off'  # Check to see if winch is operational
            workday = 'off'
            week, day_of_week = divmod(day, 7)
            _, week_number = divmod(week, 2)
            
            if (day_of_week < 5 or 
            (day_of_week == 5 and (self.saturday_operation == 'WEEKLY' or (self.saturday_operation == 'BI-WEEKLY' and week_number == 0))) or 
            (day_of_week == 6 and (self.sunday_operation == 'WEEKLY' or (self.sunday_operation == 'BI-WEEKLY' and week_number == 0)))):
                workday = 'on'


            if workday == 'on':
                for i in range(len(self.waste_start_times)):
                    if self.waste_start_times[i] > self.waste_end_times[i]:
                        if minute >= self.waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.waste_start_times[i]) / ((self.waste_end_times[i] + 24 * 60 - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.waste_start_times[i]) / ((self.waste_end_times[i] + 24 * 60 - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.waste_start_times[i]) and (minute < self.waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.waste_start_times[i]) / ((self.waste_end_times[i] - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.reef_start_times)):
                    if self.reef_start_times[i] > self.reef_end_times[i]:
                        if minute >= self.reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.reef_start_times[i]) / ((self.reef_end_times[i] + 24 * 60 - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.reef_start_times[i]) / ((self.reef_end_times[i] + 24 * 60 - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.reef_start_times[i]) and (minute < self.reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.reef_start_times[i]) / ((self.reef_end_times[i] - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 5:
                for i in range(len(self.saturday_waste_start_times)):
                    if self.saturday_waste_start_times[i] > self.saturday_waste_end_times[i]:
                        if minute >= self.saturday_waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] + 24 * 60 - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.saturday_waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] + 24 * 60 - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.saturday_waste_start_times[i]) and (minute < self.saturday_waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.saturday_reef_start_times)):
                    if self.saturday_reef_start_times[i] > self.saturday_reef_end_times[i]:
                        if minute >= self.saturday_reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] + 24 * 60 - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.saturday_reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] + 24 * 60 - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.saturday_reef_start_times[i]) and (minute < self.saturday_reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 6:
                for i in range(len(self.sunday_waste_start_times)):
                    if self.sunday_waste_start_times[i] > self.sunday_waste_end_times[i]:
                        if minute >= self.sunday_waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] + 24 * 60 - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.sunday_waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] + 24 * 60 - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.sunday_waste_start_times[i]) and (minute < self.sunday_waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.sunday_reef_start_times)):
                    if self.reef_start_times[i] > self.sunday_reef_end_times[i]:
                        if minute >= self.sunday_reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] + 24 * 60 - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.sunday_reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] + 24 * 60 - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.sunday_reef_start_times[i]) and (minute < self.sunday_reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]

            if status == 'on' and self.breakdown == False:
                random_num = random.random()
                if (self.active_time_since_last_repair - self.last_breakdown) > 0:
                    breakdown_chance = self.breakdown_profile[self.breakdown_profile['Running Hours'] <= ((self.active_time_since_last_repair - self.last_breakdown) / 60)]['Cumulative Probability of Breakdown'].values[-1]
                else:
                    breakdown_chance = 0
                if random_num <= breakdown_chance and breakdown_chance != 0:
                        self.breakdown = True
                        # print('Breakdown at ' + str(self.env.now))
                        self.last_breakdown = self.active_time_since_last_repair
                        repair_chance = random.random()
                        self.repair_time = self.repair_profile[self.repair_profile['Cumulative Probability of Repair'] >= repair_chance]['Repair Time'].values[0] * 60
                        # print(self.repair_time)
                        self.repair_time_start = sum(row[1] for row in self.results)

            if self.breakdown == True:
                if (self.repair_time_to_now - self.repair_time_start) >= self.repair_time:
                    # print('Repaired at ' + str(self.env.now))
                    self.breakdown = False
                    self.last_repair = sum(self.results[0])

            pull_inlet = 0  # Check which inlet to pull ore from
            if (status == 'on') and (self.breakdown == False):
                self.status[0] = True
                self.status[1] = True
                self.status[2] = False
                delay = (100 - utilisation_factor) / 100 * self.delay_max
                if (end_time - minute) > delay:
                    yield self.env.timeout(delay)
                else:
                    if (end_time - minute - 1) > 0:
                        yield self.env.timeout(end_time - minute - 1)
                    continue
                if self.switching_type == 'PRIORITY':
                    for i, container in enumerate(self.inlet):
                        if self.list_of_containers[container].check_level(self.current_ore_type) > 0:
                            pull_inlet = i
                            break
                else:
                    variables = {}
                    for i, container in enumerate(self.inlet):
                        temp = self.list_of_containers[container].check_level(self.current_ore_type) / self.list_of_containers[container].capacity(self.current_ore_type)
                        variables[str(i)] = temp

                    pull_inlet = int(max(variables, key=variables.get))
                    # if self.inlet[0][:4] == "L121":
                    #   print(pull_inlet)

                ore_all = np.ones(int(self.no_hopper)) * self.hopper_capacity

                if self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type) > 0:
                    for i in range(len(ore_all)):
                        ore = ore_all[i]
                        if self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type) >= ore:  # Take everything less than hopper size from inlet
                            ore = ore
                            if self.current_ore_type == 'reef':
                                self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated += ore
                            else:
                                self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated += ore
                        elif self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type) > 0:
                            ore = self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type)
                            if self.current_ore_type == 'reef':
                                self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated += ore
                            else:
                                self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated += ore
                        else:
                            ore = 0
                        ore_all[i] = ore
                else:
                    for i in range(len(ore_all)):
                        ore_all[i] = 0

                # if np.sum(ore_all) > 0:
                if np.sum(ore_all) > self.no_hopper * self.hopper_capacity * 0.75:
                    # print(pull_inlet)
                    self.status[2] = True

                    if self.inlet_distance[pull_inlet] > 0:
                        yield self.env.timeout(self.inlet_distance[pull_inlet] / self.tramming_velocity_empty)


                    if len(self.resource_queue[pull_inlet]) > 0:
                        self.previous_request = yield from move_on_rail(self.env, 'from_shaft', self.resource_queue, pull_inlet, minute, 'ore', self.tramming_velocity_empty, self.rail_segments_dict, self, self.priority_schedule,self.previous_request)
                    
                    for i in range(len(ore_all)):
                        ore = ore_all[i]
                        if ore > 0:
                            test = yield from self.list_of_containers[self.inlet[pull_inlet]].get(ore, self.current_ore_type, self.loading_time)
                            if test is None:
                                for j in range(i,len(ore_all)):
                                    ore_all[j] = 0
                                continue
                            if self.current_ore_type == 'reef':
                                self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated -= ore
                            else:
                                self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated -= ore

                    self.ore_store += np.sum(ore_all)
                    
                    if self.inlet_distance[pull_inlet] > 0:
                        yield self.env.timeout(self.inlet_distance[pull_inlet] / self.tramming_velocity_full)
                    

                    if len(self.resource_queue[pull_inlet]) > 0:
                        self.previous_request = yield from move_on_rail(self.env, 'to_shaft', self.resource_queue, pull_inlet, minute, 'ore', self.tramming_velocity_full, self.rail_segments_dict, self, self.previous_request)

                    for i in range(len(ore_all)):
                        if ore_all[i] > 0:
                            yield from self.list_of_containers[self.outlet[pull_inlet]].put(ore_all[i], self.current_ore_type, self.dumping_time)
                            self.ore_store -= ore_all[i]

                else:
                    self.status[2] = False
                    for i in range(len(ore_all)):
                        ore = ore_all[i]
                        if self.current_ore_type == 'reef':
                            self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated -= ore
                        else:
                            self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated -= ore         
            elif status == 'on':
                if self.previous_request:
                    yield self.previous_request.resource.release(self.previous_request)
                self.position = self.rest_position
                self.status = default_status(status)
            else:
                if self.previous_request:
                    yield self.previous_request.resource.release(self.previous_request)
                self.position = self.rest_position
                self.status = default_status(status)
                # yield self.env.timeout(4)
                time_to_next_start = get_time_to_next_start(self.env, [self.reef_start_times, self.waste_start_times, self.saturday_reef_start_times, self.saturday_waste_start_times, self.sunday_reef_start_times, self.sunday_waste_start_times])
                if time_to_next_start > 0:
                    yield self.env.timeout(time_to_next_start)
    
    def tracking(self):
        while True:
            yield self.env.timeout(1)
            if self.status[0] == True:
                scheduled = 1
            else:
                scheduled = 0
            if self.status[1] == True:
                available = 1
            else:
                available = 0
            if self.status[2] == True:
                active = 1
            else:
                active = 0
            self.results.append([self.env.now, scheduled, available, active, self.ore_store, self.position[0], self.position[1], self.position[2]])
            # self.ore_store = 0
            self.active_time_since_last_repair += active
            self.repair_time_to_now += scheduled


class LHD:   
    def __init__(self, env, velocity_full, velocity_empty, dump_per_cycle, reef_start_times, reef_end_times, waste_start_times, waste_end_times, 
                 saturday_operation, sunday_operation,
                 saturday_reef_start_times, saturday_reef_end_times, saturday_waste_start_times, saturday_waste_end_times,
                 sunday_reef_start_times, sunday_reef_end_times, sunday_waste_start_times, sunday_waste_end_times,
                 loading_time, dumping_time, inlet, inlet_distance, switching_type, outlet, utilisation_profile_df,
                 resource_queue, list_of_simulation_resources, rail_segments_dict, workplaces, breakdown_df, repair_df, location):
         # Unique variables for LHD
        self.tramming_velocity_full = velocity_full
        self.tramming_velocity_empty = velocity_empty
        self.dump_per_cycle = dump_per_cycle
        self.inlet_distance = inlet_distance
        self.switching_type = switching_type
        self.rest_position = determine_rest_position(location)
        self.position = self.rest_position

        # Common variables
        self.env = env
        self.reef_start_times = reef_start_times
        self.reef_end_times = reef_end_times
        self.waste_start_times = waste_start_times
        self.waste_end_times = waste_end_times
        self.saturday_operation = saturday_operation
        self.sunday_operation = sunday_operation
        self.saturday_reef_start_times = saturday_reef_start_times
        self.saturday_reef_end_times = saturday_reef_end_times
        self.saturday_waste_start_times = saturday_waste_start_times
        self.saturday_waste_end_times = saturday_waste_end_times
        self.sunday_reef_start_times = sunday_reef_start_times
        self.sunday_reef_end_times = sunday_reef_end_times
        self.sunday_waste_start_times = sunday_waste_start_times
        self.sunday_waste_end_times = sunday_waste_end_times
        self.loading_time = loading_time
        self.dumping_time = dumping_time
        self.inlet = inlet
        self.outlet = outlet
        self.utilisation_profile = utilisation_profile_df['Utilisation [%]']
        self.delay_max = (60 * utilisation_profile_df['Time [hr]'].values[-1] + utilisation_profile_df['Time [minutes]'].values[-1]) / (len(utilisation_profile_df) - 1)
        self.resource_queue = resource_queue
        self.list_of_simulation_resources = list_of_simulation_resources
        self.rail_segments_dict = rail_segments_dict
        self.workplaces = workplaces
        self.breakdown_profile = breakdown_df
        self.repair_profile = repair_df
        
        # State variables
        self.status = [False, False, False, False]
        self.results = []
        self.breakdown = False
        self.last_breakdown = 0
        self.last_repair = 0
        self.repair_time = 0
        self.repair_time_start = 0
        self.current_ore_type = None
        self.ore_store = 0
        self.active_time_since_last_repair = 0
        self.repair_time_to_now = 0
        self.list_of_containers = None

    def update(self, list_of_containers, all_components):
        self.list_of_containers = list_of_containers
        self.rail_segments_dict = {name: all_components[name] for name in all_components if isinstance(all_components[name], RailSegment)}
    
    def process(self):
        while True:
            yield self.env.timeout(1)
            day, minute = divmod(self.env.now, 24 * 60)
            status = 'off'  # Check to see if winch is operational
            workday = 'off'
            week, day_of_week = divmod(day, 7)
            _, week_number = divmod(week, 2)
            
            if (day_of_week < 5 or 
            (day_of_week == 5 and (self.saturday_operation == 'WEEKLY' or (self.saturday_operation == 'BI-WEEKLY' and week_number == 0))) or 
            (day_of_week == 6 and (self.sunday_operation == 'WEEKLY' or (self.sunday_operation == 'BI-WEEKLY' and week_number == 0)))):
                workday = 'on'


            if workday == 'on':
                for i in range(len(self.waste_start_times)):
                    if self.waste_start_times[i] > self.waste_end_times[i]:
                        if minute >= self.waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.waste_start_times[i]) / ((self.waste_end_times[i] + 24 * 60 - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.waste_start_times[i]) / ((self.waste_end_times[i] + 24 * 60 - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.waste_start_times[i]) and (minute < self.waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.waste_start_times[i]) / ((self.waste_end_times[i] - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.reef_start_times)):
                    if self.reef_start_times[i] > self.reef_end_times[i]:
                        if minute >= self.reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.reef_start_times[i]) / ((self.reef_end_times[i] + 24 * 60 - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.reef_start_times[i]) / ((self.reef_end_times[i] + 24 * 60 - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.reef_start_times[i]) and (minute < self.reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.reef_start_times[i]) / ((self.reef_end_times[i] - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 5:
                for i in range(len(self.saturday_waste_start_times)):
                    if self.saturday_waste_start_times[i] > self.saturday_waste_end_times[i]:
                        if minute >= self.saturday_waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] + 24 * 60 - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.saturday_waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] + 24 * 60 - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.saturday_waste_start_times[i]) and (minute < self.saturday_waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.saturday_reef_start_times)):
                    if self.saturday_reef_start_times[i] > self.saturday_reef_end_times[i]:
                        if minute >= self.saturday_reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] + 24 * 60 - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.saturday_reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] + 24 * 60 - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.saturday_reef_start_times[i]) and (minute < self.saturday_reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 6:
                for i in range(len(self.sunday_waste_start_times)):
                    if self.sunday_waste_start_times[i] > self.sunday_waste_end_times[i]:
                        if minute >= self.sunday_waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] + 24 * 60 - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.sunday_waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] + 24 * 60 - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.sunday_waste_start_times[i]) and (minute < self.sunday_waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.sunday_reef_start_times)):
                    if self.reef_start_times[i] > self.sunday_reef_end_times[i]:
                        if minute >= self.sunday_reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] + 24 * 60 - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.sunday_reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] + 24 * 60 - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.sunday_reef_start_times[i]) and (minute < self.sunday_reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]

            if status == 'on' and self.breakdown == False:
                random_num = random.random()
                if (self.active_time_since_last_repair - self.last_breakdown) > 0:
                    breakdown_chance = self.breakdown_profile[self.breakdown_profile['Running Hours'] <= ((self.active_time_since_last_repair - self.last_breakdown) / 60)]['Cumulative Probability of Breakdown'].values[-1]
                else:
                    breakdown_chance = 0
                if random_num <= breakdown_chance and breakdown_chance != 0:
                        self.breakdown = True
                        # print('Breakdown at ' + str(self.env.now))
                        self.last_breakdown = self.active_time_since_last_repair
                        repair_chance = random.random()
                        self.repair_time = self.repair_profile[self.repair_profile['Cumulative Probability of Repair'] >= repair_chance]['Repair Time'].values[0] * 60
                        # print(self.repair_time)
                        self.repair_time_start = sum(row[1] for row in self.results)

            if self.breakdown == True:
                if (self.repair_time_to_now - self.repair_time_start) >= self.repair_time:
                    # print('Repaired at ' + str(self.env.now))
                    self.breakdown = False
                    self.last_repair = sum(self.results[0])

            pull_inlet = 0  # Check which inlet to pull ore from
            ore = self.dump_per_cycle
            if (status == 'on') and (self.breakdown == False):
                self.status[0] = True
                self.status[1] = True
                self.status[2] = False
                delay = (100 - utilisation_factor) / 100 * self.delay_max
                if (end_time - minute) > delay:
                    yield self.env.timeout(delay)
                else:
                    if (end_time - minute - 1) > 0:
                        yield self.env.timeout(end_time - minute - 1)
                    continue
                if self.switching_type == 'PRIORITY':
                    for i, container in enumerate(self.inlet):
                        try:
                            if self.list_of_containers[container].check_level(self.current_ore_type) > 0:
                                pull_inlet = i
                                break
                        except:
                            pass
                else:
                    variables = {}

                    for i, container in enumerate(self.inlet):

                        temp = self.list_of_containers[container].check_level(self.current_ore_type) / self.list_of_containers[container].capacity(self.current_ore_type)
                        variables[str(i)] = temp

                    pull_inlet = int(max(variables, key=variables.get))

                if self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type) >= ore:  # Take everything less than dump size from inlet
                    ore = ore
                    if self.current_ore_type == 'reef':
                        self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated += ore
                    else:
                        self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated += ore
                elif self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type) > 0:
                    ore = self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type)
                    if self.current_ore_type == 'reef':
                        self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated += ore
                    else:
                        self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated += ore
                else:
                    ore = 0
                    if self.current_ore_type == 'reef':
                        self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated += ore
                    else:
                        self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated += ore
                if ore > 0:
                    self.status[2] = True
                    if self.inlet_distance[pull_inlet] > 0:
                        yield self.env.timeout(self.inlet_distance[pull_inlet] / self.tramming_velocity_empty)
                    if len(self.resource_queue[pull_inlet]) > 0:
                        yield from move_on_rail(self.env, 'from_shaft', self.resource_queue, pull_inlet, minute, 'ore', self.tramming_velocity_empty, self.rail_segments_dict)
                    yield from self.list_of_containers[self.inlet[pull_inlet]].get(ore, self.current_ore_type, self.loading_time)
                    if self.current_ore_type == 'reef':
                        self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated -= ore
                    else:
                        self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated -= ore
                    self.ore_store += ore
                    if self.inlet_distance[pull_inlet] > 0:
                        yield self.env.timeout(self.inlet_distance[pull_inlet] / self.tramming_velocity_full)
                    if len(self.resource_queue[pull_inlet]) > 0:
                        yield from move_on_rail(self.env, 'to_shaft', self.resource_queue, pull_inlet, minute, 'ore', self.tramming_velocity_full, self.rail_segments_dict)
                    yield from self.list_of_containers[str(self.outlet[pull_inlet])].put(ore, self.current_ore_type, self.dumping_time)
            elif status == 'on':
                self.status = default_status(status)
            else:
                self.status = default_status(status)
                # yield self.env.timeout(4)
                time_to_next_start = get_time_to_next_start(self.env, [self.reef_start_times, self.waste_start_times, self.saturday_reef_start_times, self.saturday_waste_start_times, self.sunday_reef_start_times, self.sunday_waste_start_times])
                if time_to_next_start > 0:
                    yield self.env.timeout(time_to_next_start)

    def tracking(self):
        while True:
            yield self.env.timeout(1)
            if self.status[0] == True:
                scheduled = 1
            else:
                scheduled = 0
            if self.status[1] == True:
                available = 1
            else:
                available = 0
            if self.status[2] == True:
                active = 1
            else:
                active = 0
            self.results.append([self.env.now, scheduled, available, active, self.ore_store])
            self.ore_store = 0
            self.active_time_since_last_repair += active
            self.repair_time_to_now += scheduled


class Dump_Truck:
    def __init__(self, env, velocity_full, velocity_empty, dump_per_cycle, reef_start_times, reef_end_times, waste_start_times, waste_end_times, 
                 saturday_operation, sunday_operation,
                 saturday_reef_start_times, saturday_reef_end_times, saturday_waste_start_times, saturday_waste_end_times,
                 sunday_reef_start_times, sunday_reef_end_times, sunday_waste_start_times, sunday_waste_end_times,
                 loading_time, dumping_time, inlet, inlet_distance, switching_type, outlet, utilisation_profile_df,
                 resource_queue, list_of_simulation_resources, rail_segments_dict, workplaces, breakdown_df, repair_df):
        # Unique Variables
        self.tramming_velocity_full = velocity_full
        self.tramming_velocity_empty = velocity_empty
        self.dump_per_cycle = dump_per_cycle
        self.inlet_distance = inlet_distance
        self.switching_type = switching_type
        self.inlet = inlet
        self.outlet = outlet

        # Common Variables
        self.env = env
        self.reef_start_times = reef_start_times
        self.reef_end_times = reef_end_times
        self.waste_start_times = waste_start_times
        self.waste_end_times = waste_end_times
        self.saturday_operation = saturday_operation
        self.sunday_operation = sunday_operation
        self.saturday_reef_start_times = saturday_reef_start_times
        self.saturday_reef_end_times = saturday_reef_end_times
        self.saturday_waste_start_times = saturday_waste_start_times
        self.saturday_waste_end_times = saturday_waste_end_times
        self.sunday_reef_start_times = sunday_reef_start_times
        self.sunday_reef_end_times = sunday_reef_end_times
        self.sunday_waste_start_times = sunday_waste_start_times
        self.sunday_waste_end_times = sunday_waste_end_times
        self.loading_time = loading_time
        self.dumping_time = dumping_time
        self.utilisation_profile = utilisation_profile_df['Utilisation [%]']
        self.delay_max = (60 * utilisation_profile_df['Time [hr]'].values[-1] + utilisation_profile_df['Time [minutes]'].values[-1]) / (len(utilisation_profile_df) - 1)
        self.resource_queue = resource_queue
        self.list_of_simulation_resources = list_of_simulation_resources
        self.rail_segments_dict = rail_segments_dict
        self.workplaces = workplaces
        self.breakdown_profile = breakdown_df
        self.repair_profile = repair_df

        # State Tracking Variables
        self.status = [False, False, False, False]
        self.results = []
        self.breakdown = False
        self.last_breakdown = 0
        self.last_repair = 0
        self.repair_time = 0
        self.repair_time_start = 0
        self.current_ore_type = None
        self.ore_store = 0
        self.active_time_since_last_repair = 0
        self.repair_time_to_now = 0

    def update(self, list_of_containers, all_components):
        self.list_of_containers = list_of_containers
        self.rail_segments_dict = {name: all_components[name] for name in all_components if isinstance(all_components[name], RailSegment)}
    
    def process(self):
        while True:
            yield self.env.timeout(1)
            day, minute = divmod(self.env.now, 24 * 60)

            global list_of_containers

            status = 'off'  # Check to see if winch is operational
            workday = 'off'
            week, day_of_week = divmod(day, 7)
            _, week_number = divmod(week, 2)
            
            if (day_of_week < 5 or 
            (day_of_week == 5 and (self.saturday_operation == 'WEEKLY' or (self.saturday_operation == 'BI-WEEKLY' and week_number == 0))) or 
            (day_of_week == 6 and (self.sunday_operation == 'WEEKLY' or (self.sunday_operation == 'BI-WEEKLY' and week_number == 0)))):
                workday = 'on'


            if workday == 'on':
                for i in range(len(self.waste_start_times)):
                    if self.waste_start_times[i] > self.waste_end_times[i]:
                        if minute >= self.waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.waste_start_times[i]) / ((self.waste_end_times[i] + 24 * 60 - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.waste_start_times[i]) / ((self.waste_end_times[i] + 24 * 60 - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.waste_start_times[i]) and (minute < self.waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.waste_start_times[i]) / ((self.waste_end_times[i] - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.reef_start_times)):
                    if self.reef_start_times[i] > self.reef_end_times[i]:
                        if minute >= self.reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.reef_start_times[i]) / ((self.reef_end_times[i] + 24 * 60 - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.reef_start_times[i]) / ((self.reef_end_times[i] + 24 * 60 - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.reef_start_times[i]) and (minute < self.reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.reef_start_times[i]) / ((self.reef_end_times[i] - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 5:
                for i in range(len(self.saturday_waste_start_times)):
                    if self.saturday_waste_start_times[i] > self.saturday_waste_end_times[i]:
                        if minute >= self.saturday_waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] + 24 * 60 - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.saturday_waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] + 24 * 60 - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.saturday_waste_start_times[i]) and (minute < self.saturday_waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.saturday_reef_start_times)):
                    if self.saturday_reef_start_times[i] > self.saturday_reef_end_times[i]:
                        if minute >= self.saturday_reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] + 24 * 60 - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.saturday_reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] + 24 * 60 - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.saturday_reef_start_times[i]) and (minute < self.saturday_reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 6:
                for i in range(len(self.sunday_waste_start_times)):
                    if self.sunday_waste_start_times[i] > self.sunday_waste_end_times[i]:
                        if minute >= self.sunday_waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] + 24 * 60 - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.sunday_waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] + 24 * 60 - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.sunday_waste_start_times[i]) and (minute < self.sunday_waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.sunday_reef_start_times)):
                    if self.reef_start_times[i] > self.sunday_reef_end_times[i]:
                        if minute >= self.sunday_reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] + 24 * 60 - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.sunday_reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] + 24 * 60 - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.sunday_reef_start_times[i]) and (minute < self.sunday_reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]

            if status == 'on' and self.breakdown == False:
                random_num = random.random()
                if (self.active_time_since_last_repair - self.last_breakdown) > 0:
                    breakdown_chance = self.breakdown_profile[self.breakdown_profile['Running Hours'] <= ((self.active_time_since_last_repair - self.last_breakdown) / 60)]['Cumulative Probability of Breakdown'].values[-1]
                else:
                    breakdown_chance = 0
                if random_num <= breakdown_chance and breakdown_chance != 0:
                        self.breakdown = True
                        # print('Breakdown at ' + str(self.env.now))
                        self.last_breakdown = self.active_time_since_last_repair
                        repair_chance = random.random()
                        self.repair_time = self.repair_profile[self.repair_profile['Cumulative Probability of Repair'] >= repair_chance]['Repair Time'].values[0] * 60
                        # print(self.repair_time)
                        self.repair_time_start = sum(row[1] for row in self.results)

            if self.breakdown == True:
                if (self.repair_time_to_now - self.repair_time_start) >= self.repair_time:
                    # print('Repaired at ' + str(self.env.now))
                    self.breakdown = False
                    self.last_repair = sum(self.results[0])

            pull_inlet = 0  # Check which inlet to pull ore from
            ore = self.dump_per_cycle
            if (status == 'on') and (self.breakdown == False):
                self.status[0] = True
                self.status[1] = True
                self.status[2] = False
                delay = (100 - utilisation_factor) / 100 * self.delay_max
                if (end_time - minute) > delay:
                    yield self.env.timeout(delay)
                else:
                    if (end_time - minute - 1) > 0:
                        yield self.env.timeout(end_time - minute - 1)
                    continue
                if self.switching_type == 'PRIORITY':
                    for i, container in enumerate(self.inlet):
                        if self.list_of_containers[container].check_level(self.current_ore_type) > 0:
                            pull_inlet = i
                            break
                else:
                    variables = {}
                    for i, container in enumerate(self.inlet):
                        temp = self.list_of_containers[container].check_level(self.current_ore_type) / self.list_of_containers[container].capacity(self.current_ore_type)
                        variables[str(i)] = temp

                    pull_inlet = int(max(variables, key=variables.get))

                if self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type) >= ore:  # Take everything less than dump size from inlet
                    ore = ore
                    if self.current_ore_type == 'reef':
                        self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated += ore
                    else:
                        self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated += ore
                elif self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type) > 0:
                    ore = self.list_of_containers[self.inlet[pull_inlet]].check_level(self.current_ore_type)
                    if self.current_ore_type == 'reef':
                        self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated += ore
                    else:
                        self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated += ore
                else:
                    ore = 0
                    if self.current_ore_type == 'reef':
                        self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated += ore
                    else:
                        self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated += ore

                if ore > 0:
                    self.status[2] = True
                    if self.inlet_distance[pull_inlet] > 0:
                        yield self.env.timeout(self.inlet_distance[pull_inlet] / self.tramming_velocity_empty)
                    if len(self.resource_queue[pull_inlet]) > 0:
                        yield from move_on_rail(self.env, 'from_shaft', self.resource_queue, pull_inlet, minute, 'ore', self.tramming_velocity_empty, self.rail_segments_dict)
                    yield from self.list_of_containers[self.inlet[pull_inlet]].get(ore, self.current_ore_type, self.loading_time)
                    if self.current_ore_type == 'reef':
                        self.list_of_containers[self.inlet[pull_inlet]].reef_dedicated -= ore
                    else:
                        self.list_of_containers[self.inlet[pull_inlet]].waste_dedicated -= ore
                    self.ore_store += ore
                    if self.inlet_distance[pull_inlet] > 0:
                        yield self.env.timeout(self.inlet_distance[pull_inlet] / self.tramming_velocity_full)
                    if len(self.resource_queue[pull_inlet]) > 0:
                        yield from move_on_rail(self.env, 'to_shaft', self.resource_queue, pull_inlet, minute, 'ore', self.tramming_velocity_full, self.rail_segments_dict)
                    yield from self.list_of_containers[self.outlet[pull_inlet]].put(ore, self.current_ore_type, self.dumping_time)

            elif status == 'on':
                self.status = default_status(status)
            else:
                self.status = default_status(status)
                # yield self.env.timeout(4)
                time_to_next_start = get_time_to_next_start(self.env, [self.reef_start_times, self.waste_start_times, self.saturday_reef_start_times, self.saturday_waste_start_times, self.sunday_reef_start_times, self.sunday_waste_start_times])
                if time_to_next_start > 0:
                    yield self.env.timeout(time_to_next_start)

    def tracking(self):
        while True:
            yield self.env.timeout(1)
            if self.status[0] == True:
                scheduled = 1
            else:
                scheduled = 0
            if self.status[1] == True:
                available = 1
            else:
                available = 0
            if self.status[2] == True:
                active = 1
            else:
                active = 0
            self.results.append([self.env.now, scheduled, available, active, self.ore_store])
            self.ore_store = 0
            self.active_time_since_last_repair += active
            self.repair_time_to_now += scheduled


class Winder:
    def __init__(self, env, no_skips, skip_capacity, cycle_time, loading_time, dumping_time, reef_start_times, reef_end_times, waste_start_times, waste_end_times, 
                 saturday_operation, sunday_operation,
                 saturday_reef_start_times, saturday_reef_end_times, saturday_waste_start_times, saturday_waste_end_times,
                 sunday_reef_start_times, sunday_reef_end_times, sunday_waste_start_times, sunday_waste_end_times,
                 inlet, switching_type, outlet, utilisation_profile_df,
                 workplaces, breakdown_df, repair_df):
        
        # Unique Attributes
        self.no_skips = no_skips
        self.skip_capacity = skip_capacity
        self.cycle_time = cycle_time
        self.loading_time = loading_time
        self.dumping_time = dumping_time
        self.inlet = inlet
        self.outlet = outlet
        self.switching_type = switching_type

        # Common Attributes
        self.env = env
        self.reef_start_times = reef_start_times
        self.reef_end_times = reef_end_times
        self.waste_start_times = waste_start_times
        self.waste_end_times = waste_end_times
        self.saturday_operation = saturday_operation
        self.sunday_operation = sunday_operation
        self.saturday_reef_start_times = saturday_reef_start_times
        self.saturday_reef_end_times = saturday_reef_end_times
        self.saturday_waste_start_times = saturday_waste_start_times
        self.saturday_waste_end_times = saturday_waste_end_times
        self.sunday_reef_start_times = sunday_reef_start_times
        self.sunday_reef_end_times = sunday_reef_end_times
        self.sunday_waste_start_times = sunday_waste_start_times
        self.sunday_waste_end_times = sunday_waste_end_times
        self.utilisation_profile = utilisation_profile_df['Utilisation [%]']
        self.delay_max = (60 * utilisation_profile_df['Time [hr]'].values[-1] + utilisation_profile_df['Time [minutes]'].values[-1]) / (len(utilisation_profile_df) - 1)
        self.workplaces = workplaces
        self.breakdown_profile = breakdown_df
        self.repair_profile = repair_df

        # State Tracking Variables
        self.status = [False, False, False, False]
        self.results = []
        self.breakdown = False
        self.last_breakdown = 0
        self.last_repair = 0
        self.repair_time = 0
        self.repair_time_start = 0
        self.current_ore_type = None
        self.ore_store = 0
        self.active_time_since_last_repair = 0
        self.repair_time_to_now = 0

        # Container Dictionary
        self.list_of_containers_local = {name: globals()[name] for name in globals() if isinstance(globals()[name], ResourceContainer)}

    def update(self, list_of_containers, all_components):
        self.list_of_containers_local = list_of_containers

    def process(self):
        while True:
            yield self.env.timeout(1)
            day, minute = divmod(self.env.now, 24 * 60)

            status = 'off'  # Check to see if winch is operational
            workday = 'off'
            week, day_of_week = divmod(day, 7)
            _, week_number = divmod(week, 2)
            
            if (day_of_week < 5 or 
                (day_of_week == 5 and (self.saturday_operation == 'WEEKLY' or (self.saturday_operation == 'BI-WEEKLY' and week_number == 0))) or 
                (day_of_week == 6 and (self.sunday_operation == 'WEEKLY' or (self.sunday_operation == 'BI-WEEKLY' and week_number == 0)))):
                    workday = 'on'


            if workday == 'on':
                for i in range(len(self.waste_start_times)):
                    if self.waste_start_times[i] > self.waste_end_times[i]:
                        if minute >= self.waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.waste_start_times[i]) / ((self.waste_end_times[i] + 24 * 60 - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.waste_start_times[i]) / ((self.waste_end_times[i] + 24 * 60 - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.waste_start_times[i]) and (minute < self.waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.waste_start_times[i]) / ((self.waste_end_times[i] - self.waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.reef_start_times)):
                    if self.reef_start_times[i] > self.reef_end_times[i]:
                        if minute >= self.reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.reef_start_times[i]) / ((self.reef_end_times[i] + 24 * 60 - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.reef_start_times[i]) / ((self.reef_end_times[i] + 24 * 60 - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.reef_start_times[i]) and (minute < self.reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.reef_start_times[i]) / ((self.reef_end_times[i] - self.reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 5:
                for i in range(len(self.saturday_waste_start_times)):
                    if self.saturday_waste_start_times[i] > self.saturday_waste_end_times[i]:
                        if minute >= self.saturday_waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] + 24 * 60 - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.saturday_waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] + 24 * 60 - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.saturday_waste_start_times[i]) and (minute < self.saturday_waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.saturday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_waste_start_times[i]) / ((self.saturday_waste_end_times[i] - self.saturday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.saturday_reef_start_times)):
                    if self.saturday_reef_start_times[i] > self.saturday_reef_end_times[i]:
                        if minute >= self.saturday_reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] + 24 * 60 - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.saturday_reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] + 24 * 60 - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.saturday_reef_start_times[i]) and (minute < self.saturday_reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.saturday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.saturday_reef_start_times[i]) / ((self.saturday_reef_end_times[i] - self.saturday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
            elif day_of_week == 6:
                for i in range(len(self.sunday_waste_start_times)):
                    if self.sunday_waste_start_times[i] > self.sunday_waste_end_times[i]:
                        if minute >= self.sunday_waste_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] + 24 * 60 - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.sunday_waste_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] + 24 * 60 - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.sunday_waste_start_times[i]) and (minute < self.sunday_waste_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'waste'
                            self.status = default_status(status)
                            end_time = self.sunday_waste_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_waste_start_times[i]) / ((self.sunday_waste_end_times[i] - self.sunday_waste_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                for i in range(len(self.sunday_reef_start_times)):
                    if self.reef_start_times[i] > self.sunday_reef_end_times[i]:
                        if minute >= self.sunday_reef_start_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i] + 24 * 60
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] + 24 * 60 - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                        elif minute < self.sunday_reef_end_times[i]:
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute + 24 * 60 - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] + 24 * 60 - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]
                    else:
                        if (minute >= self.sunday_reef_start_times[i]) and (minute < self.sunday_reef_end_times[i]):
                            status = 'on'
                            self.current_ore_type = 'reef'
                            self.status = default_status(status)
                            end_time = self.sunday_reef_end_times[i]
                            utilisation_index = min(math.floor(
                                (minute - self.sunday_reef_start_times[i]) / ((self.sunday_reef_end_times[i] - self.sunday_reef_start_times[i]) / len(self.utilisation_profile))), len(self.utilisation_profile) - 1)
                            utilisation_factor = self.utilisation_profile[utilisation_index]

            if status == 'on' and self.breakdown == False:
                random_num = random.random()
                if (self.active_time_since_last_repair - self.last_breakdown) > 0:
                    breakdown_chance = self.breakdown_profile[self.breakdown_profile['Running Hours'] <= ((self.active_time_since_last_repair - self.last_breakdown) / 60)]['Cumulative Probability of Breakdown'].values[-1]
                else:
                    breakdown_chance = 0
                if random_num <= breakdown_chance and breakdown_chance != 0:
                        self.breakdown = True
                        # print('Breakdown at ' + str(self.env.now))
                        self.last_breakdown = self.active_time_since_last_repair
                        repair_chance = random.random()
                        self.repair_time = self.repair_profile[self.repair_profile['Cumulative Probability of Repair'] >= repair_chance]['Repair Time'].values[0] * 60
                        # print(self.repair_time)
                        self.repair_time_start = sum(row[1] for row in self.results)

            if self.breakdown == True:
                if (self.repair_time_to_now - self.repair_time_start) >= self.repair_time:
                    # print('Repaired at ' + str(self.env.now))
                    self.breakdown = False
                    self.last_repair = sum(self.results[0])

            pull_inlet = 0  # Check which inlet to pull ore from
            ore = self.skip_capacity
            if (status == 'on') and (self.breakdown == False):
                self.status[0] = True
                self.status[1] = True
                self.status[2] = False
                delay = (100 - utilisation_factor) / 100 * self.delay_max
                if (end_time - minute) > delay:
                    yield self.env.timeout(delay)
                else:
                    if (end_time - minute - 1) > 0:
                        yield self.env.timeout(end_time - minute - 1)
                    continue
                if self.no_skips == 1:
                    if self.switching_type == 'PRIORITY':
                        for i, container in enumerate(self.inlet):
                            if self.list_of_containers_local[container].check_level(self.current_ore_type) > 0:
                                pull_inlet = i
                                break
                    else:
                        variables = {}
                        for i, container in enumerate(self.inlet):
                            temp = self.list_of_containers_local[container].check_level(self.current_ore_type) / list_of_containers[container].capacity(self.current_ore_type)
                            variables[str(i)] = temp

                        pull_inlet = int(max(variables, key=variables.get))

                    if self.list_of_containers_local[self.inlet[pull_inlet]].check_level(self.current_ore_type) >= ore:  # Take everything less than dump size from inlet
                        ore = ore
                    elif self.list_of_containers_local[self.inlet[pull_inlet]].check_level(self.current_ore_type) > 0:
                        ore = self.list_of_containers_local[self.inlet[pull_inlet]].check_level(self.current_ore_type)
                    else:
                        ore = 0
                    if ore > 0:
                        self.status[2] = True
                        yield self.env.timeout(self.cycle_time)
                        print(ore, self.list_of_containers_local[self.inlet[pull_inlet]].check_level(self.current_ore_type))
                        yield from self.list_of_containers_local[self.inlet[pull_inlet]].get(ore, self.current_ore_type, self.loading_time)
                        self.ore_store += ore
                        yield self.env.timeout(self.cycle_time)
                        yield from self.list_of_containers_local[str(self.outlet[0])].put(ore, self.current_ore_type, self.dumping_time - 1)
                else:
                    if self.switching_type == 'PRIORITY':
                        for i, container in enumerate(self.inlet):
                            if self.list_of_containers_local[container].check_level(self.current_ore_type) > 0:
                                pull_inlet = i
                                break
                    else:
                        variables = {}
                        for i, container in enumerate(self.inlet):
                            temp = self.list_of_containers_local[container].check_level(self.current_ore_type)
                            variables[str(i)] = temp

                        pull_inlet = int(max(variables, key=variables.get))

                    if self.list_of_containers_local[self.inlet[pull_inlet]].check_level(self.current_ore_type) >= ore:  # Take everything less than dump size from inlet
                        ore = ore
                    elif self.list_of_containers_local[self.inlet[pull_inlet]].check_level(self.current_ore_type) > 0:
                        ore = self.list_of_containers_local[self.inlet[pull_inlet]].check_level(self.current_ore_type)
                    else:
                        ore = 0
                    if ore > 0:
                        self.status[2] = True
                        yield from self.list_of_containers_local[self.inlet[pull_inlet]].get(ore, self.current_ore_type, max(self.loading_time, self.dumping_time) - 1)
                        self.ore_store += ore
                        yield self.env.timeout(self.cycle_time)
                        yield from self.list_of_containers_local[str(self.outlet[0])].put(ore, self.current_ore_type)
            elif status == 'on':
                self.status = default_status(status)

            else:
                self.status = default_status(status)
                # yield env.timeout(4)
                time_to_next_start = get_time_to_next_start(self.env, [self.reef_start_times, self.waste_start_times, self.saturday_reef_start_times, self.saturday_waste_start_times, self.sunday_reef_start_times, self.sunday_waste_start_times])
                if time_to_next_start > 0:
                    yield self.env.timeout(time_to_next_start)

    def tracking(self):
        while True:
            yield self.env.timeout(1)
            if self.status[0] == True:
                scheduled = 1
            else:
                scheduled = 0
            if self.status[1] == True:
                available = 1
            else:
                available = 0
            if self.status[2] == True:
                active = 1
            else:
                active = 0
            self.results.append([self.env.now, scheduled, available, active, self.ore_store])
            self.ore_store = 0
            self.active_time_since_last_repair += active
            self.repair_time_to_now += scheduled


class Conveyor:
    def __init__(self, env, start_times, end_times, start_times_saturday, end_times_saturday, start_times_sunday, end_times_sunday, saturday_operation, sunday_operation, 
                 capacity, surge_capacity, velocity, length, outlet, num_instantaneous_vibrating_feeders, workplaces, breakdown_df, repair_df):
        # Unique Attributes
        self.capacity = capacity * round(length / velocity)  # Adjusted based on velocity and length
        self.surge_capacity = surge_capacity
        self.velocity = velocity
        self.length = length
        self.outlet = outlet
        self.num_instantaneous_vibrating_feeders = num_instantaneous_vibrating_feeders

        # Common Attributes
        self.env = env
        self.start_times = start_times
        self.end_times = end_times
        self.start_times_saturday = start_times_saturday
        self.end_times_saturday = end_times_saturday
        self.start_times_sunday = start_times_sunday
        self.end_times_sunday = end_times_sunday
        self.saturday_operation = saturday_operation
        self.sunday_operation = sunday_operation
        self.workplaces = workplaces
        self.breakdown_profile = breakdown_df
        self.repair_profile = repair_df

        # State Tracking Variables
        self.status = [False, False, False, False]
        self.results = []
        self.breakdown = False
        self.last_breakdown = 0
        self.last_repair = 0
        self.repair_time = 0
        self.repair_time_start = 0
        self.ore_store = 0
        self.repair_time_to_now = 0
        self.active_time_since_last_repair = 0

        # Conveyor System
        conveyor_slots = math.ceil(length / velocity)
        self.conveyor_ore_store = np.zeros(conveyor_slots)
        self.conveyor_ore_type = [None] * conveyor_slots 

        # Simulation Resources
        self.conveyor_resource = simpy.PriorityResource(env, capacity=num_instantaneous_vibrating_feeders)
        self.list_of_containers_local = {name: globals()[name] for name in globals() if isinstance(globals()[name], ResourceContainer)}
        self.list_of_conveyors_local = {}

    def update_conveyors(self, all_components):
        self.list_of_conveyors_local = {name: all_components[name] for name in all_components if isinstance(all_components[name], Conveyor)}

    def update(self, list_of_containers, all_components):
        self.list_of_containers_local = list_of_containers
        self.rail_segments_dict = {name: all_components[name] for name in all_components if isinstance(all_components[name], RailSegment)}

    def process(self):
        while True:
            yield self.env.timeout(1)
            day, minute = divmod(self.env.now, 24 * 60)

            status = 'off'  # Check to see if winch is operational
            workday = 'off'
            week, day_of_week = divmod(day, 7)
            _, week_number = divmod(week, 2)
            if (day_of_week < 5 or 
                    (day_of_week == 5 and (self.saturday_operation == 'WEEKLY' or 
                    (self.saturday_operation == 'BI-WEEKLY' and week_number == 0))) or 
                    (day_of_week == 6 and (self.sunday_operation == 'WEEKLY' or 
                    (self.sunday_operation == 'BI-WEEKLY' and week_number == 0)))):
                workday = 'on'

                            
            if workday == 'on':
                for i in range(len(self.start_times)):
                    if self.start_times[i] > self.end_times[i]:
                        if minute >= self.start_times[i]:
                            status = 'on'
                            self.status = default_status(status)
                        elif minute < self.end_times[i]:
                            status = 'on'
                            self.status = default_status(status)
                    else:
                        if (minute >= self.start_times[i]) and (minute < self.end_times[i]):
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times[i]
            elif day_of_week == 5:
                for i in range(len(self.start_times_saturday)):
                    if self.start_times_saturday[i] > self.end_times_saturday[i]:
                        if minute >= self.start_times_saturday[i]:
                            status = 'on'
                            self.status = default_status(status)
                        elif minute < self.end_times_saturday[i]:
                            status = 'on'
                            self.status = default_status(status)
                    else:
                        if (minute >= self.start_times_saturday[i]) and (minute < self.end_times_saturday[i]):
                            status = 'on'
                            self.status = default_status(status)
            elif day_of_week == 6:
                for i in range(len(self.start_times_sunday)):
                    if self.start_times_sunday[i] > self.end_times_sunday[i]:
                        if minute >= self.start_times_sunday[i]:
                            status = 'on'
                            self.status = default_status(status)
                        elif minute < self.end_times_sunday[i]:
                            status = 'on'
                            self.status = default_status(status)
                    else:
                        if (minute >= self.start_times_sunday[i]) and (minute < self.end_times_sunday[i]):
                            status = 'on'
                            self.status = default_status(status)

            if status == 'on' and self.breakdown == False:
            # if (status == 'on' or np.sum(self.conveyor_ore_store) > 0) and self.breakdown == False:             
                random_num = random.random()
                if (self.active_time_since_last_repair - self.last_breakdown) > 0:
                    breakdown_chance = self.breakdown_profile[self.breakdown_profile['Running Hours'] <= ((self.active_time_since_last_repair - self.last_breakdown) / 60)]['Cumulative Probability of Breakdown'].values[-1]
                else:
                    breakdown_chance = 0
                if random_num <= breakdown_chance and breakdown_chance != 0:
                        self.breakdown = True
                        # print('Breakdown at ' + str(self.env.now))
                        self.last_breakdown = self.active_time_since_last_repair
                        repair_chance = random.random()
                        self.repair_time = self.repair_profile[self.repair_profile['Cumulative Probability of Repair'] >= repair_chance]['Repair Time'].values[0] * 60
                        # print(self.repair_time)
                        self.repair_time_start = sum(row[1] for row in self.results)

            if self.breakdown == True:
                if (self.repair_time_to_now - self.repair_time_start) >= self.repair_time:
                    # print('Repaired at ' + str(self.env.now))
                    self.breakdown = False
                    self.last_repair = sum(self.results[0])

            if (status == 'on') and (self.breakdown == False):
                self.status[0] = True
                self.status[1] = True
                self.status[2] = False
                ore = self.conveyor_ore_store[0]
                temp_ore_type = self.conveyor_ore_type[0]
                # self.ore_store = np.max(self.conveyor_ore_store) * 60
                self.ore_store = np.sum(self.conveyor_ore_store) / len(self.conveyor_ore_store) * 60
                if self.ore_store > 0:
                    self.status[2] = True
                else:
                    self.status[2] = False
                for i in range(len(self.conveyor_ore_store) - 1):
                    self.conveyor_ore_store[i] = self.conveyor_ore_store[i + 1]
                    self.conveyor_ore_type[i] = self.conveyor_ore_type[i + 1]
                self.conveyor_ore_store[-1] = 0
                self.conveyor_ore_type[-1] = None
                if ore > 0:
                    if str(self.outlet) in self.list_of_containers_local:
                        yield from self.list_of_containers_local[str(self.outlet)].put(ore, temp_ore_type)
                    else:
                        try_dump = True
                        while try_dump:
                            if self.list_of_conveyors_local[str(self.outlet)].conveyor_ore_store[-1] + ore <= self.list_of_conveyors_local[str(self.outlet)].surge_capacity:
                                self.list_of_conveyors_local[str(self.outlet)].conveyor_ore_store[-1] += ore
                                temp_type = self.list_of_conveyors_local[str(self.outlet)].conveyor_ore_type[-1]
                                if temp_type == 'reef' or temp_ore_type == 'reef':
                                    self.list_of_conveyors_local[str(self.outlet)].conveyor_ore_type[-1] = 'reef'
                                else:
                                    self.list_of_conveyors_local[str(self.outlet)].conveyor_ore_type[-1] = 'waste'
                                try_dump = False
                            else:

                                if str(self.outlet) == 'X_X_X_X_CV01' and self.list_of_conveyors_local[str(self.outlet)].breakdown == False:
                                    pass
                                yield self.env.timeout(1)
            elif status == 'on':
                self.status = default_status(status)
                self.ore_store = 0
            else:
                self.status = default_status(status)
                self.ore_store = 0
                # yield self.env.timeout(4)
                time_to_next_start = get_time_to_next_start(self.env, [self.start_times, self.start_times_saturday, self.start_times_sunday])
                if time_to_next_start > 0:
                    yield self.env.timeout(time_to_next_start)
    
    def tracking(self):
        while True:
            yield self.env.timeout(1)
            if self.status[0] == True:
                scheduled = 1
            else:
                scheduled = 0
            if self.status[1] == True:
                available = 1
            else:
                available = 0
            if self.status[2] == True:
                active = 1
            else:
                active = 0
            self.results.append([self.env.now, scheduled, available, active, self.ore_store])
            self.active_time_since_last_repair += active
            self.repair_time_to_now += scheduled


class Vibrating_Feeder:
    def __init__(self, env, start_times, end_times, start_times_saturday, end_times_saturday, start_times_sunday, end_times_sunday, saturday_operation, sunday_operation,
                 feed_rate, inlet, ore_type, outlet, distance, workplaces, breakdown_df, repair_df, isolated_tipping, tipping_delay):
       # Environment & Scheduling
        self.env = env
        self.start_times = start_times
        self.end_times = end_times
        self.start_times_saturday = start_times_saturday
        self.end_times_saturday = end_times_saturday
        self.start_times_sunday = start_times_sunday
        self.end_times_sunday = end_times_sunday
        self.saturday_operation = saturday_operation
        self.sunday_operation = sunday_operation

        # Operational Parameters
        self.feed_rate = feed_rate
        self.inlet = inlet
        self.ore_type = ore_type
        self.outlet = outlet
        self.distance = distance
        self.workplaces = workplaces
        self.isolated_tipping = isolated_tipping
        self.tipping_delay = tipping_delay

        # State Tracking Variables
        self.status = [False, False, False, False]
        self.results = []
        self.breakdown = False
        self.last_breakdown = 0
        self.last_repair = 0
        self.repair_time = 0
        self.repair_time_start = 0
        self.ore_store = 0
        self.repair_time_to_now = 0
        self.active_time_since_last_repair = 0

        # Breakdown & Repair Profiles
        self.breakdown_profile = breakdown_df
        self.repair_profile = repair_df

        # Simulation Resources
        self.list_of_containers_local = {}
        self.list_of_conveyors_local = {}

    def update(self, list_of_containers, all_components):
        self.list_of_containers_local = list_of_containers
        self.list_of_containers = list_of_containers
        self.rail_segments_dict = {name: all_components[name] for name in all_components if isinstance(all_components[name], RailSegment)}
        self.list_of_conveyors_local = {name: all_components[name] for name in all_components if isinstance(all_components[name], Conveyor)}

    def process(self,status = 'off',workday = 'off') : # Check to see if winch is operational
        while True:
            # yield self.env.timeout(1)
            day, minute = divmod(self.env.now, 24 * 60)            
            week, day_of_week = divmod(day, 7)
            _, week_number = divmod(week, 2)
            
            if day_of_week < 5:
                workday = 'on'
            elif (day_of_week == 5 and self.saturday_operation == 'WEEKLY') or (day_of_week == 5 and self.saturday_operation == 'BI-WEEKLY' and week_number == 0):
                workday = 'on'
            elif (day_of_week == 5 and self.sunday_operation == 'WEEKLY') or (day_of_week == 6 and self.sunday_operation == 'BI-WEEKLY' and week_number == 0):
                workday = 'on'
                            
            if workday == 'on':
                for i in range(len(self.start_times)):
                    if self.start_times[i] > self.end_times[i]:
                        if minute >= self.start_times[i]:
                            status = 'on'
                            self.status = default_status(status)
                        elif minute < self.end_times[i]:
                            status = 'on'
                            self.status = default_status(status)
                    else:
                        if (minute >= self.start_times[i]) and (minute < self.end_times[i]):
                            status = 'on'
                            self.status = default_status(status)
                            end_time = self.end_times[i]
            elif day_of_week == 5:
                for i in range(len(self.start_times_saturday)):
                    if self.start_times_saturday[i] > self.end_times_saturday[i]:
                        if minute >= self.start_times_saturday[i]:
                            status = 'on'
                            self.status = default_status(status)
                        elif minute < self.end_times_saturday[i]:
                            status = 'on'
                            self.status = default_status(status)
                    else:
                        if (minute >= self.start_times_saturday[i]) and (minute < self.end_times_saturday[i]):
                            status = 'on'
                            self.status = default_status(status)
            elif day_of_week == 6:
                for i in range(len(self.start_times_sunday)):
                    if self.start_times_sunday[i] > self.end_times_sunday[i]:
                        if minute >= self.start_times_sunday[i]:
                            status = 'on'
                            self.status = default_status(status)
                        elif minute < self.end_times_sunday[i]:
                            status = 'on'
                            self.status = default_status(status)
                    else:
                        if (minute >= self.start_times_sunday[i]) and (minute < self.end_times_sunday[i]):
                            status = 'on'
                            self.status = default_status(status)

            if status == 'on' and self.breakdown == False:
                random_num = random.random()
                if (self.active_time_since_last_repair - self.last_breakdown) > 0:
                    breakdown_chance = self.breakdown_profile[self.breakdown_profile['Running Hours'] <= ((self.active_time_since_last_repair - self.last_breakdown) / 60)]['Cumulative Probability of Breakdown'].values[-1]
                else:
                    breakdown_chance = 0
                if random_num <= breakdown_chance and breakdown_chance != 0:
                        self.breakdown = True
                        # print('Breakdown at ' + str(self.env.now))
                        self.last_breakdown = self.active_time_since_last_repair
                        repair_chance = random.random()
                        self.repair_time = self.repair_profile[self.repair_profile['Cumulative Probability of Repair'] >= repair_chance]['Repair Time'].values[0] * 60
                        # print(self.repair_time)
                        self.repair_time_start = sum(row[1] for row in self.results)

            if self.breakdown == True:
                if (self.repair_time_to_now - self.repair_time_start) >= self.repair_time:
                    # print('Repaired at ' + str(self.env.now))
                    self.breakdown = False
                    self.last_repair = sum(self.results[0])

            if (status == 'on') and (self.breakdown == False):
                self.status[0] = True
                self.status[1] = True
                self.status[2] = False
                tip = False
                if (sum(self.list_of_conveyors_local[self.outlet].conveyor_ore_store)) < (self.list_of_conveyors_local[self.outlet].capacity):
                    ore = self.feed_rate
                    pull_inlet = 0
                    if self.list_of_containers_local[
                        self.inlet[pull_inlet]].level(self.ore_type) >= ore:  # Take everything less than feeder rate from inlet
                        ore = ore
                    elif self.list_of_containers_local[self.inlet[pull_inlet]].level(self.ore_type) > 0:
                        ore = self.list_of_containers_local[self.inlet[pull_inlet]].level(self.ore_type)
                    else:
                        ore = 0
                    index = min(round(self.distance / self.list_of_conveyors_local[self.outlet].velocity) - 1, len(self.list_of_conveyors_local[self.outlet].conveyor_ore_store) - 1)
                    ore = max(0, min(ore, self.list_of_conveyors_local[self.outlet].capacity - sum(self.list_of_conveyors_local[self.outlet].conveyor_ore_store), self.list_of_conveyors_local[self.outlet].surge_capacity - self.list_of_conveyors_local[self.outlet].conveyor_ore_store[index]))
                    if ore > self.list_of_conveyors_local[self.outlet].surge_capacity:
                        pass
                    # print(ore)
                    # if sum(globals()[self.outlet].conveyor_ore_store) + ore > globals()[self.outlet].capacity:
                    #     # print(globals()[self.outlet].capacity)
                    #     # print(globals()[self.outlet].conveyor_ore_store)
                    #     # print(sum(globals()[self.outlet].conveyor_ore_store))
                    #     ore = max(0, globals()[self.outlet].capacity - sum(globals()[self.outlet].conveyor_ore_store))
                    # elif globals()[self.outlet].conveyor_ore_store[index] + ore > globals()[self.outlet].surge_capacity:
                    #     ore = max(0, globals()[self.outlet].surge_capacity - globals()[self.outlet].conveyor_ore_store[index])
                    if ore > 0:
                        pull_inlet_level = self.list_of_containers[self.inlet[pull_inlet]].level(self.ore_type)
                        max_inlet_capacity = self.list_of_containers[self.inlet[pull_inlet]].capacity(self.ore_type)
                        priority = calculate_priority(pull_inlet_level, max_inlet_capacity)
                        req = self.list_of_conveyors_local[self.outlet].conveyor_resource.request(priority=priority)
                        result = yield req | self.env.timeout(1)
                        if req in result:
                            if self.isolated_tipping == 'y':
                                index = min(round(self.distance / self.list_of_conveyors_local[self.outlet].velocity) - 1, len(self.list_of_conveyors_local[self.outlet].conveyor_ore_store) - 1)
                                if (round(self.tipping_delay) + index) > (len(self.list_of_conveyors_local[self.outlet].conveyor_ore_store)) - 1:
                                    #print('Tipping delay longer than lenght of belt before')
                                    if self.list_of_conveyors_local[self.outlet].conveyor_ore_store[-1] > 0:
                                        tip = False
                                    else:
                                        tip = True
                                else:
                                    if self.list_of_conveyors_local[self.outlet].conveyor_ore_store[round(self.tipping_delay) + index] > 0:
                                        tip = False
                                    else:
                                        tip = True
                                self.list_of_conveyors_local[self.outlet].conveyor_ore_store[index]
                            else:
                                tip = True
                            if tip:
                                self.status[2] = True
                                if self.ore_type == 'waste':
                                    pass
                                yield from self.list_of_containers[self.inlet[pull_inlet]].get(ore, self.ore_type)
                                self.ore_store += ore
                                self.list_of_conveyors_local[self.outlet].conveyor_ore_store[index] += ore
                                temp_type = self.list_of_conveyors_local[self.outlet].conveyor_ore_type[index]
                                if temp_type == 'reef' or self.ore_type == 'reef':
                                    self.list_of_conveyors_local[str(self.outlet)].conveyor_ore_type[index] = 'reef'
                                else:
                                    self.list_of_conveyors_local[str(self.outlet)].conveyor_ore_type[index] = 'waste'
                                yield self.env.timeout(1)
                                yield self.list_of_conveyors_local[self.outlet].conveyor_resource.release(req)
                            else:
                                if priority == 0:
                                    pass
                                self.status[2] = False
                                yield self.env.timeout(1)
                                yield self.list_of_conveyors_local[self.outlet].conveyor_resource.release(req)
                        else:
                            if priority == 0:
                                pass
                            self.status[2] = False
                            req.cancel()
                            yield self.env.timeout(1)
                    else:
                        self.status[2] = False
                        yield self.env.timeout(1)
                else:
                    self.status[2] = False
                    yield self.env.timeout(1)
            elif status == 'on':
                self.status = default_status(status)
                yield self.env.timeout(1)
            else:
                self.status = default_status(status)
                time_to_next_start = get_time_to_next_start(self.env, [self.start_times, self.start_times_saturday, self.start_times_sunday])
                if time_to_next_start > 0:
                    yield self.env.timeout(time_to_next_start)
                yield self.env.timeout(1)

    def tracking(self):
        while True:
            yield self.env.timeout(1)
            if self.status[0] == True:
                scheduled = 1
            else:
                scheduled = 0
            if self.status[1] == True:
                available = 1
            else:
                available = 0
            if self.status[2] == True:
                active = 1
            else:
                active = 0
            self.results.append([self.env.now, scheduled, available, active, self.ore_store])
            self.ore_store = 0
            self.active_time_since_last_repair += active
            self.repair_time_to_now += scheduled


# def track_progress(env, scenario_name, delay, total_time, start_time):
#     while True:
#         yield env.timeout(10)
#         time_completed = time.time() - start_time
#         hours_done = math.floor(time_completed/60/60)
#         minutes_done = math.floor((time_completed - hours_done * 60 *60)/60)
#         seconds_done = math.floor(time_completed - hours_done * 60 * 60 - minutes_done * 60)

#         total_est_time = math.floor(time_completed / ((int(env.now) / total_time)))

#         hours_to_go = math.floor(total_est_time/60/60)
#         minutes_to_go = math.floor((total_est_time - hours_to_go * 60 *60)/60)
#         seconds_to_go = math.floor(total_est_time - hours_to_go * 60 * 60 - minutes_to_go * 60)

#         elapsed_time_str = f'{hours_done:02}:{minutes_done:02}:{seconds_done:02}'
#         eta_str = f'{hours_to_go:02}:{minutes_to_go:02}:{seconds_to_go:02}'
#         print("\033[34m",scenario_name, " | Progress: ", int((int(env.now) / total_time) * 100), 
#             "%  | Time: ", int(env.now), " of ", total_time, 
#             " | Elapsed Time: ", elapsed_time_str, 
#             " | ETA: ", eta_str, "\033[0m")

# I just refactored this function a bit but kept original
# above in case it broke something
def track_progress(env, scenario_name: str, delay: int, total_time: int, start_time: float):
    while True:
        yield env.timeout(10)
        time_completed = time.time() - start_time
        progress_ratio = int(env.now) / total_time

        total_est_time = time_completed / progress_ratio if progress_ratio > 0 else 0
        remaining_time = max(total_est_time - time_completed, 0)

        elapsed_h, elapsed_m = divmod(int(time_completed), 3600)
        elapsed_m, elapsed_s = divmod(elapsed_m, 60)

        eta_h, eta_m = divmod(int(remaining_time), 3600)
        eta_m, eta_s = divmod(eta_m, 60)

        elapsed_time_str = f'{elapsed_h:02}:{elapsed_m:02}:{elapsed_s:02}'
        eta_str = f'{eta_h:02}:{eta_m:02}:{eta_s:02}'

        print("\033[34m", scenario_name, " | Progress:", int(progress_ratio * 100), 
              "% | Time:", int(env.now), "of", total_time, 
              "| Elapsed Time:", elapsed_time_str, 
              "| ETA:", eta_str, "\033[0m")
