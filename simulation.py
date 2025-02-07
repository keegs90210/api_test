import simpy

from components import *
import math
import random

class Simulation_Platform:
    def __init__(self):
        self.env = simpy.Environment()  # Initiate self.env
        
    def run_simulation(self,scenario_name, scenario, eval_period, final_column_names, breakdowns, utilisations,st):
        ore_passes = scenario[scenario['Component Type'] == 'Ore Pass']  # Get ore passes
        ore_pass_links = scenario[scenario['Component Type'] == 'Ore Pass Link']  # Get ore pass links
        stopes = scenario[scenario['Component Type'] == 'Stope']  # Get stopes
        conveyors = scenario[scenario['Component Type'] == 'Conveyor']  # Get conveyors
        vibrating_feeders = scenario[scenario['Component Type'] == 'Vibrating Feeder']  # Get vibrating feeders
        LHDs = scenario[scenario['Component Type'] == 'LHD']  # Get LHDs
        winders = scenario[scenario['Component Type'] == 'Winder']  # Get winders
        winches = scenario[scenario['Component Type'] == 'Winch']  # Get winches
        dump_trucks = scenario[scenario['Component Type'] == 'Dump Truck']  # Get dump trucks
        Locomotives = scenario[scenario['Component Type'] == 'Locomotive']  # Get Locomotives
        direct_cleaning = scenario[scenario['Component Type'] == 'Direct Cleaning Link']  # Get direct cleaning links

        simulation_resources = scenario[scenario['Component Type'] == 'Resource']
        excavation_resources = scenario[scenario['Component Type'] == 'Excavation Resource']

        all_components = {}
        list_of_simulation_resources = []
        list_of_ore_passes = []
        list_of_conveyors = []
        list_of_stopes = []
        list_of_equipment = []
        list_of_containers = {}
        list_of_simulation_resources = []
        rail_segments_dict = {}
        list_of_containers['No_Inlet'] = ResourceContainer(self.env, 1000, 1000, 'SEPARATE', 1, 1)  # Container for components with optional Inlets
        all_components['No_Inlet'] = list_of_containers['No_Inlet']

        # Initiate resources
        if len(simulation_resources) > 0:
            print('Initialising resources')
        for _, resource in simulation_resources.iterrows():
            resource_name = str(resource.loc['Component Name']).replace(" ", "_")
            length = float(resource.loc['Parameter 1'])
            speed_factor = float(resource.loc['Parameter 2'])
            capacity = float(resource.loc['Parameter 3'])
            bypass_capacity = float(resource.loc['Parameter 4'])
            span_length = 40
            value_temp = resource.loc['Parameter 5']
            if isinstance(value_temp, (int, float)):
                locations = [float(value_temp)]
            else:
                locations = [[float(v) for v in value.split(',')] for value in value_temp.split(';')]
            value = resource.loc['Parameter 6']
            if isinstance(value, (int, float)):
                bypass_location = [float(value)]
            else:
                bypass_location = [float(v) for v in value.split(',')]
            all_components[resource_name] = RailSegment(self.env, resource_name, length, span_length, speed_factor, capacity, bypass_capacity, locations, bypass_location)
            self.env.process(all_components[resource_name].tracking())
            list_of_simulation_resources.append(all_components[resource_name])
            rail_segments_dict[resource_name] = all_components[resource_name]

        # Initiate excavation resources
        if len(excavation_resources) > 0:
            print('Initialising excavation resources')
        for _, resource in excavation_resources.iterrows():
            resource_name = str(resource.loc['Component Name']).replace(" ", "_")
            length = float(resource.loc['Parameter 1'])
            speed_factor = float(resource.loc['Parameter 2'])
            capacity = float(resource.loc['Parameter 3'])
            bypass_capacity = float(resource.loc['Parameter 4'])
            span_length = 80
            all_components[resource_name] = simpy.PriorityResource(self.env, capacity=capacity)
            list_of_simulation_resources.append(all_components[resource_name])
        
        # rail_segments_dict = {name: list_of_simulation_resources[name] for name in list_of_simulation_resources if isinstance(list_of_simulation_resources[name], RailSegment)}

        # Initiate ore passes
        if len(ore_passes) > 0:
            print('Initialising ore passes')
        for _, row in ore_passes.iterrows():
            ore_pass_name = row.loc['Component Name'].replace(" ", "_")
            reef_capacity = float(row.loc['Parameter 1'])
            waste_capacity = float(row.loc['Parameter 2'])
            mix_type = str(row.loc['Parameter 3']).upper()
            number_of_inlet_resources = float(row.loc['Parameter 4'])
            number_of_outlet_resources = float(row.loc['Parameter 5'])
            all_components[ore_pass_name] = ResourceContainer(self.env, reef_capacity, waste_capacity, mix_type, number_of_inlet_resources, number_of_outlet_resources)
            self.env.process(all_components[ore_pass_name].tracking())
            list_of_ore_passes.append(ore_pass_name)
            list_of_containers[ore_pass_name] = all_components[ore_pass_name]

        # Initiate direct cleaning links
        if len(direct_cleaning) > 0:
            print('Initialising direct cleaning links')
        for _, row in direct_cleaning.iterrows():
            direct_cleaning_name = row.loc['Component Name'].replace(" ", "_")
            reef_capacity = float(row.loc['Parameter 1'])
            waste_capacity = float(row.loc['Parameter 2'])
            mix_type = str(row.loc['Parameter 3']).upper()
            number_of_inlet_resources = float(row.loc['Parameter 4'])
            number_of_outlet_resources = float(row.loc['Parameter 5'])
            maximum_waiting_time = float(row.loc['Parameter 6'])
            all_components[direct_cleaning_name] = SynchronizedResourceContainer(self.env, reef_capacity, waste_capacity, mix_type, number_of_inlet_resources, number_of_outlet_resources, maximum_waiting_time)
            self.env.process(all_components[direct_cleaning_name].tracking())
            list_of_ore_passes.append(direct_cleaning_name)
            list_of_containers[direct_cleaning_name] = all_components[direct_cleaning_name]

        # Initiate ore pass links
        if len(ore_pass_links) > 0:
            print('Initialising ore pass links')
        for _, row in ore_pass_links.iterrows():
            ore_pass_link_name = row.loc['Component Name'].replace(" ", "_")
            reef_inlet = str(row.loc['Parameter 1']).replace(" ", "_")
            reef_outlet = str(row.loc['Parameter 2']).replace(" ", "_")
            waste_inlet = str(row.loc['Parameter 3']).replace(" ", "_")
            waste_outlet = str(row.loc['Parameter 4']).replace(" ", "_")
            rate = float(row.loc['Parameter 5'])
            if reef_inlet == 'nan':
                reef_inlet = 'No_Inlet'
            if reef_outlet == 'nan':
                reef_outlet = 'No_Inlet'
            if waste_inlet == 'nan':
                waste_inlet = 'No_Inlet'
            if waste_outlet == 'nan':
                waste_outlet = 'No_Inlet'
            all_components[ore_pass_link_name] = Ore_Pass_Link(self.env, all_components[reef_inlet], all_components[reef_outlet], all_components[waste_inlet], all_components[waste_outlet], rate)
            self.env.process(all_components[ore_pass_link_name].process())

        # Initiate stopes
        if len(stopes) > 0:
            print('Initialising stopes')
        for _, row in stopes.iterrows():
            stope_name = stope_name = row.loc['Component Name'].replace(" ", "_")
            ton_per_blast = float(row.loc['Parameter 1'])
            ore_type = str(row.loc['Parameter 2']).lower()
            blast_1_time = float(row.loc['Parameter 3']) * 60
            blast_2_time = float(row.loc['Parameter 4']) * 60
            saturday_operation = str(row.loc['Parameter 5']).upper()
            sunday_operation = str(row.loc['Parameter 6']).upper()
            blast_chance = float(row.loc['Parameter 7']) / float(row.loc['Parameter 8'])
            # print(stope_name + ' - ' + str(blast_chance))
            if (str(blast_2_time) == 'nan'):
                blast_2_time = 25 * 60
            if (str(blast_1_time) == 'nan'):
                blast_1_time = 25 * 60
            stope_capacity = np.max(ton_per_blast)
            stope_class_name = 'stp' + stope_name
            if ore_type == 'reef':
                all_components[stope_name] = ResourceContainer(self.env, 1.05 * stope_capacity, 0, 'SEPARATE', 1, 1)
            else:
                all_components[stope_name] = ResourceContainer(self.env, 0, 1.05 * stope_capacity, 'SEPARATE', 1, 1)
            all_components[stope_class_name] = Stope(self.env, ton_per_blast, ore_type, blast_1_time, blast_2_time, all_components[stope_name], blast_chance, saturday_operation, sunday_operation)
            list_of_stopes.append(stope_class_name)
            list_of_containers[stope_name] = all_components[stope_name]
            self.env.process(all_components[stope_class_name].process())
            self.env.process(all_components[stope_class_name].tracking())

        # Initiate conveyors
        if len(conveyors) > 0:
            print('Initialising conveyors')
        for _, row in conveyors.iterrows():
            conveyor_name = row.loc['Component Name'].replace(" ", "_")
            list_of_equipment.append(f'{conveyor_name}')
            start_times = [float(value) * 60 for value in str(row.loc['Parameter 1']).split(',')]
            end_times = [float(value) * 60 for value in str(row.loc['Parameter 2']).split(',')]
            saturday_operation = str(row.loc['Parameter 3']).upper()
            start_times_saturday = [float(value) * 60 for value in str(row.loc['Parameter 4']).split(',')]
            end_times_saturday = [float(value) * 60 for value in str(row.loc['Parameter 5']).split(',')]
            sunday_operation = str(row.loc['Parameter 6']).upper()
            start_times_sunday = [float(value) * 60 for value in str(row.loc['Parameter 7']).split(',')]
            end_times_sunday = [float(value) * 60 for value in str(row.loc['Parameter 8']).split(',')]
            capacity = float(row.loc['Parameter 9']) / 60
            surge_capacity = float(row.loc['Parameter 10']) / 60
            velocity = float(row.loc['Parameter 11']) * 60 
            length = float(row.loc['Parameter 12'])
            outlet = str(row.loc['Parameter 13']).replace(" ", "_")
            resource_capacity = int(row.loc['Parameter 14'])
            workplaces = ['WP ' + name for name in str(row.loc['Parameter 15']).split(',')]
            if workplaces[0] == 'WP nan':
                workplaces = []
            if str(row.loc['Parameter 16']) != 'nan':
                conveyor_temp_breakdown_df = breakdowns[str(row.loc['Parameter 16'])]
                breakdown_df = conveyor_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = conveyor_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            else:
                conveyor_temp_breakdown_df = breakdowns['Default']
                breakdown_df = conveyor_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = conveyor_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            all_components[conveyor_name] = Conveyor(self.env, start_times, end_times, start_times_saturday, end_times_saturday, start_times_sunday, end_times_sunday, saturday_operation, sunday_operation, capacity, surge_capacity, velocity, length, outlet, resource_capacity, workplaces, breakdown_df, repair_df)
            self.env.process(all_components[conveyor_name].process())
            self.env.process(all_components[conveyor_name].tracking())
        
        # Update conveyor links
        if len(conveyors) > 0:
            print('Updating conveyors')
        for name in list_of_equipment: 
            if isinstance(all_components[name], Conveyor):
                all_components[name].update_conveyors(all_components)

        # Initiate vibrating feeders
        if len(vibrating_feeders) > 0:
            print('Initialising vibrating feeders')
        for _, row in vibrating_feeders.iterrows():
            feeder_name = row.loc['Component Name'].replace(" ", "_")
            list_of_equipment.append(f'{feeder_name}')
            start_times = [float(value) * 60 for value in str(row.loc['Parameter 1']).split(',')]
            end_times = [float(value) * 60 for value in str(row.loc['Parameter 2']).split(',')]
            saturday_operation = str(row.loc['Parameter 3']).upper()
            start_times_saturday = [float(value) * 60 for value in str(row.loc['Parameter 4']).split(',')]
            end_times_saturday = [float(value) * 60 for value in str(row.loc['Parameter 5']).split(',')]
            sunday_operation = str(row.loc['Parameter 6']).upper()
            start_times_sunday = [float(value) * 60 for value in str(row.loc['Parameter 7']).split(',')]
            end_times_sunday = [float(value) * 60 for value in str(row.loc['Parameter 8']).split(',')]
            feed_rate = float(row.loc['Parameter 9']) / 60
            inlet = str(row.loc['Parameter 10']).replace(" ", "_").split(',')
            ore_type = str(row.loc['Parameter 11']).lower()
            outlet = str(row.loc['Parameter 12']).replace(" ", "_")
            distance = float(row.loc['Parameter 13'])
            workplaces = ['WP ' + name for name in str(row.loc['Parameter 14']).split(',')]
            if workplaces[0] == 'WP nan':
                workplaces = []
            if str(row.loc['Parameter 15']) != 'nan':
                feeder_temp_breakdown_df = breakdowns[str(row.loc['Parameter 15'])]
                breakdown_df = feeder_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = feeder_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            else:
                feeder_temp_breakdown_df = breakdowns['Default']
                breakdown_df = feeder_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = feeder_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            isolated_tipping = str(row.loc['Parameter 16']).lower()
            tipping_delay = float(row.loc['Parameter 17'])
            all_components[feeder_name] = Vibrating_Feeder(self.env, start_times, end_times, start_times_saturday, end_times_saturday, start_times_sunday, end_times_sunday, saturday_operation, sunday_operation, feed_rate, inlet, ore_type, outlet, distance, workplaces, breakdown_df, repair_df, isolated_tipping, tipping_delay)
            self.env.process(all_components[feeder_name].process())
            self.env.process(all_components[feeder_name].tracking())

        # Initiate LHDs
        if len(LHDs) > 0:
            print('Initialising LHDs')
        for _, row in LHDs.iterrows():
            LHD_name = row.loc['Component Name'].replace(" ", "_")
            list_of_equipment.append(f'{LHD_name}')
            reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 1']).split(',')]
            reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 2']).split(',')]
            saturday_operation = str(row.loc['Parameter 3']).upper()
            saturday_reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 4']).split(',')]
            saturday_reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 5']).split(',')]
            sunday_operation = str(row.loc['Parameter 6']).upper()
            sunday_reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 7']).split(',')]
            sunday_reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 8']).split(',')]
            waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 9']).split(',')]
            waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 10']).split(',')]
            saturday_waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 11']).split(',')]
            saturday_waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 12']).split(',')]
            sunday_waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 13']).split(',')]
            sunday_waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 14']).split(',')]
            full_velocity = float(row.loc['Parameter 15']) / 60 * 1000
            empty_velocity = float(row.loc['Parameter 16']) / 60 * 1000
            ore_dump = float(row.loc['Parameter 17'])
            loading_time = float(row.loc['Parameter 18'])
            dumping_time = float(row.loc['Parameter 19'])
            inlet = str(row.loc['Parameter 20']).replace(", ", ",").replace(" ", "_").split(',')
            for index, temp_inlet in enumerate(inlet):
                temp = 'WP_' + temp_inlet
                temp1 = 'stp_' + temp
                if temp1 in list_of_stopes:
                    inlet[index] = temp
            value = row.loc['Parameter 21']
            if isinstance(value, (int, float)):
                inlet_distance = [float(value)]
            else:
                inlet_distance = [float(v) for v in value.split(',')]
            if str(inlet) == 'nan':
                inlet = 'No_Inlet'
                inlet_distance = 0
            switching_type = row.loc['Parameter 22'].upper().replace(" ", "_")
            outlet = str(row.loc['Parameter 23']).replace(", ", ",").replace(" ", "_").split(',')
            if len(inlet) > len(outlet):
                for _ in range(len(inlet) - len(outlet)):
                    outlet.append(outlet[-1])
            # resource_queue = row.loc['resource_queue']
            temp_test = str(row.loc['Parameter 24'])
            if temp_test != 'nan':
                resource_queue = str(row.loc['Parameter 24']).replace(", ", ",").replace("; ", ";").replace(" ", "_")
                resource_queue = [resource_item.split(',') for resource_item in resource_queue.split(';')]
            else:
                resource_queue = [[] for _ in range(len(inlet))]
            workplaces = ['WP ' + name for name in str(row.loc['Parameter 25']).split(',')]
            if workplaces[0] == 'WP nan':
                workplaces = []
            if str(row.loc['Parameter 26']) != 'nan':
                lhd_temp_breakdown_df = breakdowns[str(row.loc['Parameter 26'])]
                breakdown_df = lhd_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = lhd_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            else:
                lhd_temp_breakdown_df = breakdowns['Default']
                breakdown_df = lhd_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = lhd_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            if str(row.loc['Parameter 27']) != 'nan':
                lhd_temp_utilisation_profile_df = utilisations[str(row.loc['Parameter 27'])]
            else:
                lhd_temp_utilisation_profile_df = utilisations['Default']
            value = row.loc['Parameter 28']
            if isinstance(value, (int, float)):
                location = [float(value)]
            else:
                location = [float(v) for v in value.split(',')]

            all_components[LHD_name] = LHD( self.env, full_velocity, empty_velocity, ore_dump, reef_start_times,
                                            reef_end_times, waste_start_times, waste_end_times, saturday_operation,
                                            sunday_operation, saturday_reef_start_times, saturday_reef_end_times, 
                                            saturday_waste_start_times, saturday_waste_end_times, sunday_reef_start_times,
                                            sunday_reef_end_times, sunday_waste_start_times, sunday_waste_end_times, loading_time, 
                                            dumping_time, inlet, inlet_distance, switching_type, outlet, lhd_temp_utilisation_profile_df, 
                                            resource_queue, list_of_simulation_resources, rail_segments_dict, workplaces, 
                                            breakdown_df, repair_df, location)
            
            self.env.process(all_components[LHD_name].process())
            self.env.process(all_components[LHD_name].tracking())

        # Initiate winders
        if len(winders) > 0:
            print('Initialising winders')
        for _, row in winders.iterrows():
            winder_name = row.loc['Component Name'].replace(" ", "_")
            list_of_equipment.append(f'{winder_name}')
            reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 1']).split(',')]
            reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 2']).split(',')]
            saturday_operation = str(row.loc['Parameter 3']).upper()
            saturday_reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 4']).split(',')]
            saturday_reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 5']).split(',')]
            sunday_operation = str(row.loc['Parameter 6']).upper()
            sunday_reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 7']).split(',')]
            sunday_reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 8']).split(',')]
            waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 9']).split(',')]
            waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 10']).split(',')]
            saturday_waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 11']).split(',')]
            saturday_waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 12']).split(',')]
            sunday_waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 13']).split(',')]
            sunday_waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 14']).split(',')]
            no_skips = int(row.loc['Parameter 15'])
            skip_capacity = float(row.loc['Parameter 16'])
            loading_time = float(row.loc['Parameter 17'])
            dumping_time = float(row.loc['Parameter 18'])
            cycle_time = float(row.loc['Parameter 20']) / (float(row.loc['Parameter 19']) * 60)
            switching_type = row.loc['Parameter 21'].upper().replace(" ", "_")
            # outlet = row.loc['Parameter 22'].replace(" ", "_")
            outlet = str(row.loc['Parameter 22']).replace(", ", ",").replace(" ", "_").split(',')
            inlet = str(row.loc['Parameter 23']).replace(", ", ",").replace(" ", "_").split(',')
            if len(inlet) > len(outlet):
                for _ in range(len(inlet) - len(outlet)):
                    outlet.append(outlet[-1])
            workplaces = ['WP ' + name for name in str(row.loc['Parameter 24']).split(',')]
            if workplaces[0] == 'WP nan':
                workplaces = []
            if str(row.loc['Parameter 25']) != 'nan':
                winder_temp_breakdown_df = breakdowns[str(row.loc['Parameter 25'])]
                breakdown_df = winder_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = winder_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            else:
                winder_temp_breakdown_df = breakdowns['Default']
                breakdown_df = winder_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = winder_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            if str(row.loc['Parameter 26']) != 'nan':
                winder_temp_utilisation_profile_df = utilisations[str(row.loc['Parameter 26'])]
            else:
                winder_temp_utilisation_profile_df = utilisations['Default']
            value = row.loc['Parameter 27']
            if isinstance(value, (int, float)):
                location = [float(value)]
            else:
                location = [[float(v) for v in value1.split(',')] for value1 in value.split(';')]
            all_components[winder_name] = Winder(self.env, no_skips, skip_capacity, cycle_time, loading_time, dumping_time, reef_start_times, reef_end_times, waste_start_times, waste_end_times, saturday_operation, sunday_operation, saturday_reef_start_times, saturday_reef_end_times, saturday_waste_start_times, saturday_waste_end_times, sunday_reef_start_times, sunday_reef_end_times, sunday_waste_start_times, sunday_waste_end_times, inlet, switching_type, outlet, winder_temp_utilisation_profile_df, workplaces, breakdown_df, repair_df)
            self.env.process(all_components[winder_name].process())
            self.env.process(all_components[winder_name].tracking())

        # Initiate winches
        if len(winches) > 0:
            print('Initialising winches')
        for _, row in winches.iterrows():
            winch_name = row.loc['Component Name'].replace(" ", "_")
            list_of_equipment.append(f'{winch_name}')
            start_times = [float(value) * 60 for value in str(row.loc['Parameter 1']).split(',')]
            end_times = [float(value) * 60 for value in str(row.loc['Parameter 2']).split(',')]
            saturday_operation = str(row.loc['Parameter 3']).upper()
            start_times_saturday = [float(value) * 60 for value in str(row.loc['Parameter 4']).split(',')]
            end_times_saturday = [float(value) * 60 for value in str(row.loc['Parameter 5']).split(',')]
            sunday_operation = str(row.loc['Parameter 6']).upper()
            start_times_sunday = [float(value) * 60 for value in str(row.loc['Parameter 7']).split(',')]
            end_times_sunday = [float(value) * 60 for value in str(row.loc['Parameter 8']).split(',')]
            cycle_time_single_trip = float(row.loc['Parameter 9'])
            winch_capacity = float(row.loc['Parameter 10'])
            inlet = str(row.loc['Parameter 11']).replace(" ", "_").split(',')
            for index, temp_inlet in enumerate(inlet):
                temp = 'WP_' + temp_inlet
                temp1 = 'stp_' + temp
                if temp1 in list_of_stopes:
                    inlet[index] = temp
            # outlet = str(row.loc['Parameter 12']).replace(" ", "_")
            outlet = str(row.loc['Parameter 12']).replace(", ", ",").replace(" ", "_").split(',')
            if len(inlet) > len(outlet):
                for _ in range(len(inlet) - len(outlet)):
                    outlet.append(outlet[-1])
            temp_test = str(row.loc['Parameter 13'])
            if temp_test != 'nan':
                resource_queue = str(row.loc['Parameter 13']).replace(", ", ",").replace("; ", ";").replace(" ", "_")
                resource_queue = [resource_item.split(',') for resource_item in resource_queue.split(';')]
            else:
                resource_queue = [[] for _ in range(len(outlet))]
            workplace = ['WP ' + name for name in str(row.loc['Parameter 14']).split(',')]
            if workplace[0] == 'WP nan':
                workplace = []
            if str(row.loc['Parameter 15']) != 'nan':
                winch_temp_breakdown_df = breakdowns[str(row.loc['Parameter 15'])]
                breakdown_df = winch_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = winch_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            else:
                winch_temp_breakdown_df = breakdowns['Default']
                breakdown_df = winch_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = winch_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            if str(row.loc['Parameter 16']) != 'nan':
                winch_temp_utilisation_profile_df = utilisations[str(row.loc['Parameter 16'])]
            else:
                winch_temp_utilisation_profile_df = utilisations['Default']
            value = row.loc['Parameter 17']
            if isinstance(value, (int, float)):
                location = [float(value)]
            else:
                location = [float(v) for v in value.split(',')]
            all_components[winch_name] = Winch(self.env, start_times, end_times, start_times_saturday, end_times_saturday, start_times_sunday, end_times_sunday, saturday_operation, sunday_operation, cycle_time_single_trip, winch_capacity, inlet, outlet, winch_temp_utilisation_profile_df, resource_queue, list_of_simulation_resources, rail_segments_dict, workplace, breakdown_df, repair_df)
            self.env.process(all_components[winch_name].process())
            self.env.process(all_components[winch_name].tracking())

        # Initiate dump_trucks
        if len(dump_trucks) > 0:
            print('Initialising dump trucks')
        for _, row in dump_trucks.iterrows():
            dump_truck_name = row.loc['Component Name'].replace(" ", "_")
            list_of_equipment.append(f'{dump_truck_name}')
            reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 1']).split(',')]
            reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 2']).split(',')]
            saturday_operation = str(row.loc['Parameter 3']).upper()
            saturday_reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 4']).split(',')]
            saturday_reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 5']).split(',')]
            sunday_operation = str(row.loc['Parameter 6']).upper()
            sunday_reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 7']).split(',')]
            sunday_reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 8']).split(',')]
            waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 9']).split(',')]
            waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 10']).split(',')]
            saturday_waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 11']).split(',')]
            saturday_waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 12']).split(',')]
            sunday_waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 13']).split(',')]
            sunday_waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 14']).split(',')]
            full_velocity = float(row.loc['Parameter 15']) / 60 * 1000
            empty_velocity = float(row.loc['Parameter 16']) / 60 * 1000
            ore_dump = float(row.loc['Parameter 17'])
            loading_time = float(row.loc['Parameter 18'])
            dumping_time = float(row.loc['Parameter 19'])
            inlet = str(row.loc['Parameter 20']).replace(", ", ",").replace(" ", "_").split(',')
            value = row.loc['Parameter 21']
            if isinstance(value, (int, float)):
                inlet_distance = [float(value)]
            else:
                inlet_distance = [float(v) for v in value.split(',')]
            if str(inlet) == 'nan':
                inlet = 'No_Inlet'
                inlet_distance = 0
            switching_type = row.loc['Parameter 22'].upper().replace(" ", "_")
            # outlet = row.loc['Parameter 23'].replace(" ", "_")
            outlet = str(row.loc['Parameter 23']).replace(", ", ",").replace(" ", "_").split(',')
            if len(inlet) > len(outlet):
                for _ in range(len(inlet) - len(outlet)):
                    outlet.append(outlet[-1])
            # resource_queue = row.loc['resource_queue']
            temp_test = str(row.loc['Parameter 24'])
            if temp_test != 'nan':
                resource_queue = str(row.loc['Parameter 24']).replace(", ", ",").replace("; ", ";").replace(" ", "_")
                resource_queue = [resource_item.split(',') for resource_item in resource_queue.split(';')]
            else:
                resource_queue = [[] for _ in range(len(inlet))]
            workplaces = ['WP ' + name for name in str(row.loc['Parameter 25']).split(',')]
            if workplaces[0] == 'WP nan':
                workplaces = []
            if str(row.loc['Parameter 26']) != 'nan':
                dump_truck_temp_breakdown_df = breakdowns[str(row.loc['Parameter 26'])]
                breakdown_df = dump_truck_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = dump_truck_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            else:
                dump_truck_temp_breakdown_df = breakdowns['Default']
                breakdown_df = dump_truck_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = dump_truck_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            if str(row.loc['Parameter 27']) != 'nan':
                dump_truck_temp_utilisation_profile_df = utilisations[str(row.loc['Parameter 27'])]
            else:
                dump_truck_temp_utilisation_profile_df = utilisations['Default']
            value = row.loc['Parameter 28']
            if isinstance(value, (int, float)):
                location = [float(value)]
            else:
                location = [float(v) for v in value.split(',')]
            all_components[dump_truck_name] = Dump_Truck(self.env, full_velocity, empty_velocity, ore_dump, reef_start_times, reef_end_times, waste_start_times, waste_end_times, saturday_operation, sunday_operation, saturday_reef_start_times, saturday_reef_end_times, saturday_waste_start_times, saturday_waste_end_times, sunday_reef_start_times, sunday_reef_end_times, sunday_waste_start_times, sunday_waste_end_times, loading_time, dumping_time, inlet, inlet_distance, switching_type, outlet, dump_truck_temp_utilisation_profile_df, resource_queue, list_of_simulation_resources, rail_segments_dict, workplaces, breakdown_df, repair_df)
            self.env.process(all_components[dump_truck_name].process())
            self.env.process(all_components[dump_truck_name].tracking())

        # Initiate Locomotives
        if len(Locomotives) > 0:
            print('Initialising Locomotives')
        for _, row in Locomotives.iterrows():
            Locomotive_name = row.loc['Component Name'].replace(" ", "_")
            list_of_equipment.append(f'{Locomotive_name}')
            reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 1']).split(',')]
            reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 2']).split(',')]
            saturday_operation = str(row.loc['Parameter 3']).upper()
            saturday_reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 4']).split(',')]
            saturday_reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 5']).split(',')]
            sunday_operation = str(row.loc['Parameter 6']).upper()
            sunday_reef_start_times = [float(value) * 60 for value in str(row.loc['Parameter 7']).split(',')]
            sunday_reef_end_times = [float(value) * 60 for value in str(row.loc['Parameter 8']).split(',')]
            waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 9']).split(',')]
            waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 10']).split(',')]
            saturday_waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 11']).split(',')]
            saturday_waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 12']).split(',')]
            sunday_waste_start_times = [float(value) * 60 for value in str(row.loc['Parameter 13']).split(',')]
            sunday_waste_end_times = [float(value) * 60 for value in str(row.loc['Parameter 14']).split(',')]
            no_hoppers = float(row.loc['Parameter 15'])
            hopper_capacity = float(row.loc['Parameter 16'])
            loading_time = float(row.loc['Parameter 17'])
            dumping_time = float(row.loc['Parameter 18'])
            tramming_velocity_full = float(row.loc['Parameter 19']) * 60
            tramming_velocity_empty = float(row.loc['Parameter 20']) * 60
            switching_type = row.loc['Parameter 21'].upper().replace(" ", "_")
            # outlet = row.loc['Parameter 22'].replace(" ", "_")
            outlet = str(row.loc['Parameter 22']).replace(", ", ",").replace(" ", "_").split(',')
            inlet = str(row.loc['Parameter 23']).replace(", ", ",").replace(" ", "_").split(',')
            if len(inlet) > len(outlet):
                for _ in range(len(inlet) - len(outlet)):
                    outlet.append(outlet[-1])
            value = row.loc['Parameter 24']
            if str(value) == 'nan':
                inlet_distance = [0]
            elif isinstance(value, (int, float)):
                inlet_distance = [float(value)]
            else:
                inlet_distance = [float(v) for v in value.split(',')]
            temp_test = str(row.loc['Parameter 25'])
            if temp_test != 'nan':
                resource_queue = str(row.loc['Parameter 25']).replace(", ", ",").replace("; ", ";").replace(" ", "_")
                resource_queue = [resource_item.split(',') for resource_item in resource_queue.split(';')]
            else:
                resource_queue = [[] for _ in range(len(inlet))]
            if len(resource_queue) > len(inlet_distance):
                for _ in range(len(resource_queue) - len(inlet_distance)):
                    inlet_distance.append(0)
            workplaces = ['WP ' + name for name in str(row.loc['Parameter 26']).split(',')]
            if workplaces[0] == 'WP nan':
                workplaces = []
            if str(row.loc['Parameter 27']) != 'nan':
                Locomotive_temp_breakdown_df = breakdowns[str(row.loc['Parameter 27'])]
                breakdown_df = Locomotive_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = Locomotive_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            else:
                Locomotive_temp_breakdown_df = breakdowns['Default']
                breakdown_df = Locomotive_temp_breakdown_df[['Running Hours', 'Cumulative Probability of Breakdown']]
                repair_df = Locomotive_temp_breakdown_df[['Repair Time', 'Cumulative Probability of Repair']]
            if str(row.loc['Parameter 28']) != 'nan':
                Locomotive_temp_utilisation_profile_df = utilisations[str(row.loc['Parameter 28'])]
            else:
                Locomotive_temp_utilisation_profile_df = utilisations['Default']
            value = row.loc['Parameter 29']
            if isinstance(value, (int, float)):
                location = [float(value)]
            else:
                location = [float(v) for v in value.split(',')]
            all_components[Locomotive_name] = Locomotive(self.env, no_hoppers, hopper_capacity, tramming_velocity_full, tramming_velocity_empty, reef_start_times, reef_end_times, waste_start_times, waste_end_times, saturday_operation, sunday_operation, saturday_reef_start_times, saturday_reef_end_times, saturday_waste_start_times, saturday_waste_end_times, sunday_reef_start_times, sunday_reef_end_times, sunday_waste_start_times, sunday_waste_end_times, loading_time, dumping_time, switching_type, outlet, inlet, inlet_distance, Locomotive_temp_utilisation_profile_df, resource_queue, list_of_simulation_resources, rail_segments_dict, workplaces, breakdown_df, repair_df, location, priority_schedule)
            self.env.process(all_components[Locomotive_name].process())
            self.env.process(all_components[Locomotive_name].tracking())

        print('Updating all equipment')
        for component in list_of_equipment:
            all_components[component].update(list_of_containers, all_components)

        # Run simulation
        print('Initialising progress tracking')
        self.env.process(track_progress(self.env, scenario_name, eval_period / 100, eval_period, st))
        print('Begin simulation')
        self.env.run(until=(eval_period+0.1))

        # Store results
        results_array = []
        temp_time = None
        temp_results = None

        for component in list_of_ore_passes:
            temp_time, temp_total_results, temp_reef_results, temp_waste_results, temp_total_cum_results, temp_reef_cum_results, temp_waste_cum_results = zip(*(all_components[component].results))
            results_array.append([str(component) + ' Total', *temp_total_results])
            results_array.append([str(component) + ' Reef', *temp_reef_results])
            results_array.append([str(component) + ' Waste', *temp_waste_results])
            results_array.append([str(component) + ' Total(Cumulative)', *temp_total_cum_results])
            results_array.append([str(component) + ' Reef(Cumulative)', *temp_reef_cum_results])
            results_array.append([str(component) + ' Waste(Cumulative)', *temp_waste_cum_results])

        for component in list_of_simulation_resources:
            temp_time, temp_utilisation_results, temp_cum_utilisation_results = zip(*component.results)
            results_array.append([str(component.name) + ' Utilisation', *temp_utilisation_results])
            results_array.append([str(component.name) + ' Utilisation(Cumulative)', *temp_cum_utilisation_results])

        for component in list_of_conveyors:
            temp_name = component + '_results'
            exec(f'temp_time, temp_results = zip(*{temp_name})')
            results_array.append([component, *temp_results])

        for component in list_of_stopes:
            temp_time, temp_total_results, temp_reef_results, temp_waste_results = zip(*(all_components[component].results))
            results_array.append([str(component)[3:] + ' Total', *temp_total_results])
            results_array.append([str(component)[3:] + ' Reef', *temp_reef_results])
            results_array.append([str(component)[3:] + ' Waste', *temp_waste_results])

        for equipment in list_of_equipment:
            results = all_components[equipment].results
            if len(results[0]) == 5:
                temp_time, temp_scheduled, temp_available, temp_active, temp_ore = zip(*(all_components[equipment].results))
                results_array.append([str(equipment) + ' Scheduled', *temp_scheduled])
                results_array.append([str(equipment) + ' Available', *temp_available])
                results_array.append([str(equipment) + ' Active', *temp_active])
                results_array.append([str(equipment) + ' Ore', *temp_ore])
            else:
                temp_time, temp_scheduled, temp_available, temp_active, temp_ore, position_x, position_y, position_z = zip(*(all_components[equipment].results))
                results_array.append([str(equipment) + ' Scheduled', *temp_scheduled])
                results_array.append([str(equipment) + ' Available', *temp_available])
                results_array.append([str(equipment) + ' Active', *temp_active])
                results_array.append([str(equipment) + ' Ore', *temp_ore])
                results_array.append([str(equipment) + ' x-pos', *position_x])
                results_array.append([str(equipment) + ' y-pos', *position_y])
                results_array.append([str(equipment) + ' z-pos', *position_z])
        
        column_names = ['Time [hh:mm]', *temp_time]
        results = pd.DataFrame(results_array)
        results.columns = column_names
        results['Time [hh:mm]'] = results['Time [hh:mm]'].str.replace('_', ' ')
        results = results.T
        index_array = results.index.map(minutes_to_day)
        results.insert(0, 'Day', index_array)
        results.index = results.index.map(minutes_to_time)
        results.columns = results.iloc[0]
        results.index.name = 'Time [hh:mm]'
        results = results.drop(results.index[0])
        results = results.reset_index()
        results['Time Periods'] = results.index
        # results.to_csv('Test_Results_Temp.csv')
        # ddf = dd.from_pandas(results, npartitions=10)
        # unpivoted_results_ddf = ddf.melt(id_vars=['Time Periods', 'Time [hh:mm]', 'Time [Day]'], 
        #                              var_name='Attribute', value_name='Value')
        unpivoted_results = results.melt(id_vars=['Time Periods', 'Time [hh:mm]', 'Time [Day]'], 
                                    var_name='Attribute', value_name='Value')
        # unpivoted_results = pd.melt(results, id_vars=['Time Periods', 'Time [hh:mm]', 'Time [Day]'], var_name='Attribute', value_name='Value')
        unpivoted_results[['Component Name', 'Parameter']] = unpivoted_results['Attribute'].str.rsplit(n=1, expand=True)
        # unpivoted_results['Component Name'] = unpivoted_results['Component UID'].map(lambda uid: component_name_mapping.get(uid, 'Unknown'))

        value_changed = unpivoted_results['Value'].diff().ne(0)
        # Identify the first and last rows for each attribute
        is_first_row = unpivoted_results.groupby('Attribute').cumcount() == 0
        is_last_row = unpivoted_results.groupby('Attribute').cumcount(ascending=False) == 0
        row_before_change_1 = value_changed.shift(-1).fillna(False)
        rows_to_keep = is_first_row | is_last_row | value_changed | row_before_change_1
        df_filtered = unpivoted_results[rows_to_keep]

        # Split the 'Attribute' column and expand to multiple columns
        num_split_columns = len(final_column_names)
        split_columns = df_filtered['Attribute'].str.split(' ', expand=True).iloc[:, :num_split_columns]
        df_filtered[final_column_names] = split_columns

        df_filtered.dropna(inplace=True)
        cols = [col for col in df_filtered.columns if col != 'Value']
        cols.append('Value')
        df_filtered = df_filtered[cols]
        df_filtered['Scenario Name'] = scenario_name

        return unpivoted_results, df_filtered