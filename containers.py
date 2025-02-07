import simpy

from utilities import *


class SynchronizedResourceContainer:
    def __init__(self, env, reef_capacity, waste_capacity, mix_type, inlet_number, outlet_number, wait):
        self.env = env
        self.inlet_resource = simpy.Resource(env, capacity=int(inlet_number))
        self.outlet_resource = simpy.Resource(env, capacity=int(outlet_number))

        # Initialize containers with default capacity of 1 if given capacity is <= 0
        self.reef_container = create_container(reef_capacity)
        self.waste_container = create_container(waste_capacity)

        # Set initial dedicated values
        self.reef_dedicated = 0
        self.waste_dedicated = 0

        # Set mix type and wait timer
        self.mix_type = mix_type
        self.wait_timer = wait

        # Store results and default ore type
        self.results = []
        self.default_ore = determine_default_ore(reef_capacity, waste_capacity)

    # handle default ore type
    def get_ore_type(self, ore_type: str | None) -> str:
        return ore_type if ore_type is not None else self.default_ore
    
    def get(self, number, ore_type=None, time=0):
        ore_type = self.get_ore_type(ore_type)
        return_ore = None
        outlet_request = self.outlet_resource.request()
        while len(self.inlet_resource.queue) + len(self.inlet_resource.users) < 1:
            yield self.env.timeout(1)
        if not outlet_request.triggered:
            yield outlet_request
        if time > 0:
            yield self.env.timeout(time)
        waited_time = 0
        while self.level(ore_type) < number:
            if waited_time >= self.wait_timer:
                yield self.outlet_resource.release(outlet_request)
                return None
            else:
                yield self.env.timeout(1)
                waited_time += 1
        if self.mix_type == 'SEPARATE' and ore_type != 'mixed':
            if (ore_type == 'reef' and self.reef_container.capacity > 1) or self.waste_container.capacity <= 1:
                yield self.reef_container.get(number)
                return_ore = 'reef'
            else:
                yield self.waste_container.get(number)
                return_ore = 'waste'
        elif ore_type == 'mixed':
            if ((self.reef_container.level / self.reef_container.capacity) >= (self.waste_container.level / self.waste_container.capacity) and self.reef_container.capacity > 1) or self.waste_container.capacity <= 1:
                yield self.reef_container.get(number)
                return_ore = 'reef'
            else:
                yield self.waste_container.get(number)
                return_ore = 'waste'
        else:
            if ((self.reef_container.level / self.reef_container.capacity) >= (self.waste_container.level / self.waste_container.capacity) and self.reef_container.capacity > 1) or self.waste_container.capacity <= 1:
                yield self.reef_container.get(number)
                return_ore = 'reef'
            else:
                yield self.waste_container.get(number)
                return_ore = 'reef'

        yield self.outlet_resource.release(outlet_request)
        return return_ore

    def put(self, number, ore_type=None, time=0):
        temp = self.level
        ore_type = self.get_ore_type(ore_type)

        inlet_request = self.inlet_resource.request()

        while len(self.outlet_resource.queue) + len(self.outlet_resource.users) < 1:
            yield self.env.timeout(1)
        if not inlet_request.triggered:
            yield inlet_request
        if time > 0:
            yield self.env.timeout(time)

        if self.mix_type == 'SEPARATE':
            if ore_type == 'reef':
                yield self.reef_container.put(number)
            else:
                yield self.waste_container.put(number)
        else:
            if ((self.reef_container.level / self.reef_container.capacity) <= (self.waste_container.level / self.waste_container.capacity) and self.reef_container.capacity > 1) or self.waste_container.capacity <= 1:
                yield self.reef_container.put(number)
            else:
                yield self.waste_container.put(number)
        yield self.inlet_resource.release(inlet_request)

 
    def level(self, ore_type=None):
        ore_type = self.get_ore_type(ore_type)
        return determine_level(ore_type,self.mix_type,self.reef_container.capa)
    
    def check_level(self, ore_type=None):
        ore_type = self.get_ore_type(ore_type)
        if len(self.inlet_resource.queue) + len(self.inlet_resource.users) >= 1:
            if self.mix_type == 'SEPARATE':
                if ore_type == 'reef':
                    return self.reef_container.capacity
                else:
                    return self.waste_container.capacity
            else:
                return self.reef_container.capacity + self.waste_container.capacity
        else:
            return 0

    def capacity(self, ore_type=None):
        ore_type = self.get_ore_type(ore_type)
        return determine_capacity(ore_type,self.mix_type,self.reef_container.capacity,self.waste_container.capacity)
        
    def tracking(self):
        while True:
            yield self.env.timeout(1)
            self.results.append([self.env.now, self.reef_container.level + self.waste_container.level, self.reef_container.level, self.waste_container.level])


class ResourceContainer:
    def __init__(self, env, reef_capacity, waste_capacity, mix_type, inlet_number, outlet_number):
        self.env = env
        self.inlet_resource = simpy.Resource(env, capacity=int(inlet_number))
        self.outlet_resource = simpy.Resource(env, capacity=int(outlet_number))

        # Initialize containers with default capacity of 1 if given capacity is <= 0
        self.reef_container = create_container(env, reef_capacity)
        self.waste_container = create_container(env, waste_capacity)

        # Set initial dedicated values
        self.reef_dedicated = 0
        self.waste_dedicated = 0
        self.reef_cumulative = 0     
        self.waste_cumulative = 0      
        
        # Set mix type
        self.mix_type = mix_type
        
        # Store results and default ore type
        self.results = []
        self.default_ore = determine_default_ore(reef_capacity, waste_capacity)

    # handle default ore type
    def get_ore_type(self, ore_type: str | None) -> str:
        return ore_type if ore_type is not None else self.default_ore
    
    def select_container(self, ore_type, number):
        reef_ratio = self.reef_container.level / self.reef_container.capacity
        waste_ratio = self.waste_container.level / self.waste_container.capacity

        if (reef_ratio >= waste_ratio and self.reef_container.capacity > 1) or self.waste_container.capacity <= 1:
            yield self.reef_container.get(number)
            return "reef"
        else:
            yield self.waste_container.get(number)
            return "waste"

    def select_container(self, number: int) -> str:
        reef_ratio: float = self.reef_container.level / self.reef_container.capacity
        waste_ratio: float = self.waste_container.level / self.waste_container.capacity

        if (reef_ratio >= waste_ratio and self.reef_container.capacity > 1) or self.waste_container.capacity <= 1:
            yield self.reef_container.get(number)
            return "reef"
        else:
            yield self.waste_container.get(number)
            return "waste"

    def get(self, number: int, ore_type: str = None, time: int = 0) -> str:
        ore_type = self.get_ore_type(ore_type)
        return_ore: str = ""
        outlet_request = self.outlet_resource.request()

        if not outlet_request.triggered:
            yield outlet_request

        if time > 0:
            yield self.env.timeout(time)

        if self.mix_type == "SEPARATE" and ore_type != "mixed":
            if ore_type == "reef" and self.reef_container.capacity > 1 or self.waste_container.capacity <= 1:
                yield self.reef_container.get(number)
                return_ore = "reef"
            else:
                yield self.waste_container.get(number)
                return_ore = "waste"
        else:
            return_ore = yield from self.select_container(number)

        yield self.outlet_resource.release(outlet_request)
        return return_ore


    def select_put_container(self, number: int, ore_type: str) -> None:
        reef_ratio: float = self.reef_container.level / self.reef_container.capacity
        waste_ratio: float = self.waste_container.level / self.waste_container.capacity

        if (reef_ratio <= waste_ratio and self.reef_container.capacity > 1) or self.waste_container.capacity <= 1:
            yield self.reef_container.put(number)
            self.reef_cumulative += number
        else:
            yield self.waste_container.put(number)
            self.waste_cumulative += number

    def put(self, number: int, ore_type: str = None, time: int = 0) -> None:
        ore_type = self.get_ore_type(ore_type)
        inlet_request = self.inlet_resource.request()

        if not inlet_request.triggered:
            yield inlet_request

        if time > 0:
            yield self.env.timeout(time)

        if self.mix_type == "SEPARATE":
            if ore_type == "reef":
                yield self.reef_container.put(number)
                self.reef_cumulative += number
            else:
                yield self.waste_container.put(number)
                self.waste_cumulative += number
        else:
            yield from self.select_put_container(number, ore_type)

        yield self.inlet_resource.release(inlet_request)

    def level(self, ore_type=None):
        ore_type = self.get_ore_type(ore_type)
        if self.mix_type == 'SEPARATE' and ore_type != 'mixed':
            if ore_type == 'reef' and self.reef_container.capacity > 1:
                return self.reef_container.level
            else:
                return self.waste_container.level
        else:
            return self.reef_container.level + self.waste_container.level
        
    def check_level(self, ore_type=None):
        ore_type = self.get_ore_type(ore_type)
        if self.mix_type == 'SEPARATE':
            if ore_type == 'reef':
                return self.reef_container.level - self.reef_dedicated
            else:
                return self.waste_container.level - self.waste_dedicated
        else:
            return self.reef_container.level + self.waste_container.level - self.waste_dedicated - self.reef_dedicated

    def capacity(self, ore_type=None):
        ore_type = self.get_ore_type(ore_type)
        return determine_capacity(ore_type,self.mix_type,self.reef_container.capacity,self.waste_container.capacity)
    
    def tracking(self):
        while True:
            yield self.env.timeout(1)
            self.results.append([self.env.now, self.reef_container.level + self.waste_container.level, self.reef_container.level, self.waste_container.level, self.reef_cumulative + self.waste_cumulative, self.reef_cumulative, self.waste_cumulative])

