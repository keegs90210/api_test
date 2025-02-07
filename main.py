import os
import time

import pandas as pd

from file_handling import setup_utils_and_breakdowns
from simulation import Simulation_Platform
import random
if __name__ == "__main__":

    stTotal = time.time()

    file_name: str = r'C:\Users\KeeganPestana\Documents\integrated_logistics_refactor (2)\integrated_logistics_refactor\integrated_logistics_refactor\src\Loco Tramming Sensitivity\Model\Logistics.xlsx'
    sim, priority_schedule, breakdowns, utilisations = setup_utils_and_breakdowns(file_name=file_name)

    for _, sim_scenario in sim[sim['Simulate'] == 'Y'].iterrows():

        st = time.time()
        scenario_name = sim_scenario.loc['Scenario Name']
        scenario = pd.read_excel(file_name, scenario_name)
        eval_period = sim_scenario.loc['Evaluation Period [minutes]']
        final_column_names = str(sim_scenario.loc['Column Splits']).replace(', ', ',').split(',')

        # Run the simulation (no changes needed here)
        simulation_base = Simulation_Platform()
        raw_results, shortened_results = simulation_base.run_simulation(scenario_name, scenario, eval_period,
                                                                        final_column_names, breakdowns, utilisations,st)

        # Save the pandas DataFrame to CSV first to manage memory usage
        # KURT CHANGE THE NAME TRAILING NUMBER TO BE REPRESENTATIVE OF VELOCITY
        output_dir = "Locomotive Tramming Sensitivity\\Scenario Results"
        output_file = f"{output_dir}\\{scenario_name}_2_8.csv"

        try:
            os.makedirs(output_dir, exist_ok=True)
            raw_results[
                (raw_results["Component Name"].str.contains("Locomotive")) &
                (raw_results["Component Name"].str.contains("L16"))
                ].to_csv(output_file, index=False)
        except Exception as e:
            print(f"Error saving CSV: {e}")

        raw_results[(raw_results["Component Name"].str.contains("Locomotive")) & (
            raw_results["Component Name"].str.contains("L16"))].to_csv(
            f'Locomotive Tramming Sensitivity\\Scenario Results\\{scenario_name}_2_8 .csv', index=False)

        et = time.time()
        elapsed_time = (et - st) / 60
        print(f"\033[32mCompleted {scenario_name} in {round(elapsed_time, 2)} minutes\033[0m")

    # Total elapsed time for all scenarios
    etTotal = time.time()
    total_elapsed_time = (etTotal - stTotal) / 60
    print(f"\033[32mTotal time for all scenarios: {round(total_elapsed_time, 2)} minutes\033[0m")
