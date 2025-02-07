
from typing import Dict, List, Tuple, Union
import pandas as pd
from utilities import get_ore_value,get_personnel_value,get_material_value

def load_excel_file(file_path: str) -> Tuple[pd.ExcelFile, List[str]]:
    """
    Load an Excel file and return the Excel file object and sheet names.
    """
    excel_file: pd.ExcelFile = pd.ExcelFile(file_path)
    return excel_file

def create_priority_schedule() -> pd.DataFrame:
    """
    Create a DataFrame representing the priority schedule.
    """
    minutes: List[int] = list(range(0, 1441, 5))
    
    priority_schedule_data: Dict[str, List[int]] = {
        'Minute': minutes,
        'Ore to shaft': [get_ore_value(m, True) for m in minutes],
        'Ore from shaft': [get_ore_value(m, False) for m in minutes],
        'Personnel to shaft': [get_personnel_value(m, True) for m in minutes],
        'Personnel from shaft': [get_personnel_value(m, False) for m in minutes],
        'Material to shaft': [get_material_value(m, True) for m in minutes],
        'Material from shaft': [get_material_value(m, False) for m in minutes]
    }
    
    return pd.DataFrame(priority_schedule_data)

def create_breakdowns_data() -> Dict[str, pd.DataFrame]:
    """
    Create dictionaries of breakdown data for different categories.
    """
    # Predefined breakdown data for different categories
    breakdowns_data: Dict[str, List[Dict[str, float]]] = {
        'Default': [
            {'Running Hours': 0, 'Cumulative Probability of Breakdown': 0, 'Repair Time': 0, 'Cumulative Probability of Repair': 0.02275013194817919},
            {'Running Hours': 40, 'Cumulative Probability of Breakdown': 0, 'Repair Time': 8, 'Cumulative Probability of Repair': 0.9999999990134123}
        ],
        'None': [
            {'Running Hours': 0, 'Cumulative Probability of Breakdown': 0, 'Repair Time': 0, 'Cumulative Probability of Repair': 0},
            {'Running Hours': 40, 'Cumulative Probability of Breakdown': 0, 'Repair Time': 8, 'Cumulative Probability of Repair': 0}
        ]
    }
    
    # Convert breakdown data to DataFrames
    return {category: pd.DataFrame(data) for category, data in breakdowns_data.items()}

def create_utilisations_data() -> Dict[str, pd.DataFrame]:
    """
    Create dictionaries of utilisation data for different categories.
    """
    # Predefined utilisation data for different categories
    utilisation_data: Dict[str, List[Dict[str, Union[int, float]]]] = {
        'Default': [
            {'Time [hr]': 0, 'Time [minutes]': 0, 'Utilisation [%]': 0},
            {'Time [hr]': 8, 'Time [minutes]': 0, 'Utilisation [%]': 0}
        ],
        'Maximum': [
            {'Time [hr]': 0, 'Time [minutes]': 0, 'Utilisation [%]': 100},
            {'Time [hr]': 8, 'Time [minutes]': 0, 'Utilisation [%]': 100}
        ]
    }
    
    # Convert utilisation data to DataFrames
    return {category: pd.DataFrame(data) for category, data in utilisation_data.items()}

def load_additional_sheets(
    excel_file: pd.ExcelFile, 
    file_name: str, 
    utilisations: Dict[str, pd.DataFrame], 
    breakdowns: Dict[str, pd.DataFrame]
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame]]:
    """
    Load additional sheets from the Excel file for utilisations and breakdowns.
    """
    # Iterate through sheet names to load additional utilisation and breakdown data
    for sheet in excel_file.sheet_names:
        if 'Utilisation' in sheet:
            utilisations[sheet] = pd.read_excel(file_name, sheet_name=sheet)
        elif 'Breakdowns' in sheet:
            breakdowns[sheet] = pd.read_excel(file_name, sheet_name=sheet)
    
    return utilisations, breakdowns

def setup_utils_and_breakdowns(file_name:str) -> Tuple[pd.DataFrame,pd.DataFrame,Dict[str, pd.DataFrame],Dict[str, pd.DataFrame]]:
    """
    Main function to process Loco Tramming simulation data.
    """
    
    # Load Excel file
    excel_file = load_excel_file(file_name)
    
    # Read simulation sheet
    sim: pd.DataFrame = pd.read_excel(file_name, 'Simulation')
    
    # Create priority schedule
    priority_schedule: pd.DataFrame = create_priority_schedule()
    
    # Create breakdowns data
    breakdowns: Dict[str, pd.DataFrame] = create_breakdowns_data()
    
    # Create utilisations data
    utilisations: Dict[str, pd.DataFrame] = create_utilisations_data()
    
    # Load additional sheets
    utilisations, breakdowns = load_additional_sheets(excel_file, file_name, utilisations, breakdowns)

    return sim,priority_schedule,breakdowns,utilisations

