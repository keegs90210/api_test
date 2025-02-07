import random

def get_scenario_random(self, raw_random):
    if self.scenario == 'best':
        return 0.75 + 0.2 * raw_random  
    elif self.scenario == 'worst':
        return 0.25 * raw_random  
    elif self.scenario == 'base':
        return raw_random 
    else: 
        return random.random()
    
