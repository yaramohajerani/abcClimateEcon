""" Animation Visualizer for Climate 3-Layer Model
Standalone script for creating time-evolving animations and visualizations
from simulation output CSV files. Can be run independently after simulation completion.

Usage:
    python animation_visualizer.py <simulation_path> [config_file]
"""
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
from datetime import datetime

# Add the root directory to Python path to find local abcEconomics and climate framework
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import the configuration loader
from config_loader import load_model_config

def load_real_geographical_assignments(simulation_path):
    """Load REAL geographical assignments from the climate summary CSV file."""
    climate_summary_file = os.path.join(simulation_path, 'climate_3_layer_summary.csv')
    
    if not os.path.exists(climate_summary_file):
        print(f"⚠️ Climate summary file not found: {climate_summary_file}")
        return {}
    
    try:
        df = pd.read_csv(climate_summary_file)
        
        # Filter for geographical assignments
        geo_df = df[df['data_type'] == 'geographical_assignment']
        
        # Convert to the expected format
        geographical_assignments = {}
        
        for _, row in geo_df.iterrows():
            agent_type = row['agent_type']
            agent_id = int(row['agent_id'])
            continent = row['continent']
            vulnerability = row['vulnerability']
            
            if agent_type not in geographical_assignments:
                geographical_assignments[agent_type] = {}
            
            geographical_assignments[agent_type][agent_id] = {
                'continent': continent,
                'vulnerability': vulnerability
            }
        
        print(f"✅ Loaded REAL geographical assignments for {len(geographical_assignments)} agent types")
        for agent_type, assignments in geographical_assignments.items():
            print(f"    {agent_type}: {len(assignments)} agents")
        
        return geographical_assignments
        
    except Exception as e:
        print(f"❌ Error loading geographical assignments: {e}")
        return {}

def load_real_climate_events(simulation_path):
    """Load REAL climate events from the climate summary CSV file."""
    climate_summary_file = os.path.join(simulation_path, 'climate_3_layer_summary.csv')
    
    if not os.path.exists(climate_summary_file):
        print(f"⚠️ Climate summary file not found: {climate_summary_file}")
        return []
    
    try:
        df = pd.read_csv(climate_summary_file)
        
        # Filter for climate events
        events_df = df[df['data_type'] != 'geographical_assignment']
        
        if len(events_df) == 0:
            print("ℹ️ No climate events found in simulation")
            return []
        
        # Group events by round
        climate_events_history = []
        max_round = events_df['agent_id'].max() if len(events_df) > 0 else -1
        
        for round_num in range(max_round + 1):
            round_events = events_df[events_df['agent_id'] == round_num]
            
            if len(round_events) > 0:
                # Convert to the expected format
                events_dict = {}
                
                # Group by event name
                for event_name in round_events['event_name'].unique():
                    event_rows = round_events[round_events['event_name'] == event_name]
                    
                    if len(event_rows) > 0:
                        first_row = event_rows.iloc[0]
                        
                        events_dict[event_name] = {
                            'type': 'configurable_shock',
                            'rule_name': first_row['data_type'],
                            'agent_types': first_row['affected_agent_types'].split(',') if pd.notna(first_row['affected_agent_types']) else [],
                            'continents': list(event_rows['continent'].unique()),
                            'stress_factor': first_row['stress_factor'] if pd.notna(first_row['stress_factor']) else 1.0,
                            'duration': first_row['duration'] if pd.notna(first_row['duration']) else 1,
                            'affected_agents': {}
                        }
                
                climate_events_history.append(events_dict)
            else:
                climate_events_history.append({})
        
        total_events = sum(len(events) for events in climate_events_history)
        print(f"✅ Loaded REAL climate events: {total_events} events across {len(climate_events_history)} rounds")
        
        # Show event summary
        for round_num, events in enumerate(climate_events_history):
            if events:
                event_names = list(events.keys())
                print(f"    Round {round_num}: {event_names}")
        
        return climate_events_history
        
    except Exception as e:
        print(f"❌ Error loading climate events: {e}")
        return []

class ClimateFrameworkFromData:
    """Simple climate framework that loads real data from CSV files."""
    def __init__(self, geographical_assignments, climate_events_history):
        self.geographical_assignments = geographical_assignments
        self.climate_events_history = climate_events_history

def collect_simulation_data(simulation_path, round_num, config_loader, climate_framework):
    """Collect data from the simulation CSV files for one round."""
    
    round_data = {
        'agents': [],
        'climate': {},
        'production': {},
        'wealth': {},
        'inventories': {}
    }
    
    # Get actual climate events for this round from climate framework
    if round_num < len(climate_framework.climate_events_history):
        round_data['climate'] = climate_framework.climate_events_history[round_num]
    
    # Read production data from CSV files
    production_files = {
        'commodity_producer': 'panel_commodity_producer_production.csv',
        'intermediary_firm': 'panel_intermediary_firm_production.csv', 
        'final_goods_firm': 'panel_final_goods_firm_production.csv',
        'household': 'panel_household_consumption.csv'
    }
    
    production_goods = {
        'commodity_producer': 'commodity',
        'intermediary_firm': 'intermediate_good',
        'final_goods_firm': 'final_good',
        'household': 'final_good'  # households consume final goods
    }
    
    # Initialize production totals
    round_data['production'] = {
        'commodity': 0,
        'intermediary': 0,
        'final_goods': 0
    }
    
    # Read data from CSV files for all agent types including households
    for agent_type, filename in production_files.items():
        file_path = os.path.join(simulation_path, filename)
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)
                
                # Filter for this specific round
                round_df = df[df['round'] == round_num]
                
                if len(round_df) > 0:
                    # Create agent data entries for each agent
                    for _, row in round_df.iterrows():
                        agent_id = int(row['name'].replace(agent_type, ''))
                        
                        # Determine if this specific agent is climate stressed
                        is_climate_stressed = is_agent_climate_stressed(
                            agent_type, agent_id, round_data['climate'], climate_framework
                        )
                        
                        # Get wealth (money) data if available
                        wealth = row.get('money', 0)
                        
                        # Get production/consumption data
                        if agent_type == 'household':
                            # For households, track consumption, not production
                            consumption = row.get(production_goods[agent_type], 0)
                            agent_data = {
                                'id': agent_id,
                                'type': agent_type,
                                'round': round_num,
                                'production': 0,  # Households don't produce
                                'consumption': consumption,
                                'production_capacity': 0,
                                'climate_stressed': is_climate_stressed,
                                'wealth': wealth,
                                'continent': get_agent_continent(agent_type, agent_id, climate_framework),
                                'vulnerability': get_agent_vulnerability(agent_type, agent_id, climate_framework)
                            }
                        else:
                            # For production agents
                            production = row.get(production_goods[agent_type], 0)
                            agent_data = {
                                'id': agent_id,
                                'type': agent_type,
                                'round': round_num,
                                'production': production,
                                'production_capacity': production,  # Use actual production as capacity for now
                                'climate_stressed': is_climate_stressed,
                                'wealth': wealth,
                                'continent': get_agent_continent(agent_type, agent_id, climate_framework),
                                'vulnerability': get_agent_vulnerability(agent_type, agent_id, climate_framework)
                            }
                        
                        round_data['agents'].append(agent_data)
                    
                    # Sum total production for production layers (not households)
                    if agent_type != 'household':
                        good_column = production_goods[agent_type]
                        total_production = round_df[good_column].sum()
                        
                        if agent_type == 'commodity_producer':
                            round_data['production']['commodity'] = total_production
                        elif agent_type == 'intermediary_firm':
                            round_data['production']['intermediary'] = total_production
                        elif agent_type == 'final_goods_firm':
                            round_data['production']['final_goods'] = total_production
                        
            except Exception as e:
                print(f"Warning: Could not read {filename}: {e}")
    
    # Calculate wealth data by summing money from all agents of each type
    round_data['wealth'] = {
        'commodity': sum([agent['wealth'] for agent in round_data['agents'] if agent['type'] == 'commodity_producer']),
        'intermediary': sum([agent['wealth'] for agent in round_data['agents'] if agent['type'] == 'intermediary_firm']),
        'final_goods': sum([agent['wealth'] for agent in round_data['agents'] if agent['type'] == 'final_goods_firm']),
        'households': sum([agent['wealth'] for agent in round_data['agents'] if agent['type'] == 'household'])
    }
    
    # Copy production to inventories
    round_data['inventories'] = round_data['production'].copy()
    
    return round_data

def is_agent_climate_stressed(agent_type, agent_id, climate_events, climate_framework):
    """Determine if a specific agent is affected by climate stress in this round."""
    if not climate_events:
        return False
    
    for event_key, event_data in climate_events.items():
        if isinstance(event_data, dict):
            # New configurable shock format
            affected_agent_types = event_data.get('agent_types', [])
            affected_continents = event_data.get('continents', [])
            
            # Check if this agent type is affected
            if agent_type in affected_agent_types:
                # Check if this agent's continent is affected
                if 'all' in affected_continents:
                    return True
                
                agent_continent = get_agent_continent(agent_type, agent_id, climate_framework)
                if agent_continent in affected_continents:
                    return True
        
        elif event_key in ['North America', 'Europe', 'Asia', 'South America', 'Africa']:
            # Old format where event key is continent name
            agent_continent = get_agent_continent(agent_type, agent_id, climate_framework)
            if agent_continent == event_key:
                return True
    
    return False

def get_agent_continent(agent_type, agent_id, climate_framework):
    """Get the continent assignment for a specific agent."""
    if agent_type in climate_framework.geographical_assignments:
        assignments = climate_framework.geographical_assignments[agent_type]
        if agent_id in assignments:
            return assignments[agent_id]['continent']
    return 'Unknown'

def get_agent_vulnerability(agent_type, agent_id, climate_framework):
    """Get the vulnerability for a specific agent."""
    if agent_type in climate_framework.geographical_assignments:
        assignments = climate_framework.geographical_assignments[agent_type]
        if agent_id in assignments:
            return assignments[agent_id]['vulnerability']
    return 0.0

def create_time_evolution_visualization(visualization_data, simulation_path, config_loader):
    """Create time-evolving visualization from real simulation data."""
    
    print("🎬 Creating time-evolving visualization from REAL simulation data...")
    
    rounds = visualization_data['rounds']
    
    # Extract time series data
    commodity_production = [data['commodity'] for data in visualization_data['production_data']]
    intermediary_production = [data['intermediary'] for data in visualization_data['production_data']]
    final_goods_production = [data['final_goods'] for data in visualization_data['production_data']]
    
    commodity_wealth = [data['commodity'] for data in visualization_data['wealth_data']]
    intermediary_wealth = [data['intermediary'] for data in visualization_data['wealth_data']]
    final_goods_wealth = [data['final_goods'] for data in visualization_data['wealth_data']]
    household_wealth = [data['households'] for data in visualization_data['wealth_data']]
    
    # Count climate events by round
    climate_stress_counts = []
    for round_agents in visualization_data['agent_data']:
        stress_count = sum([1 for agent in round_agents if agent['climate_stressed']])
        climate_stress_counts.append(stress_count)
    
    # Calculate production capacities dynamically from configuration
    commodity_config = config_loader.get_agent_config('commodity_producer')
    intermediary_config = config_loader.get_agent_config('intermediary_firm')
    final_goods_config = config_loader.get_agent_config('final_goods_firm')
    
    commodity_capacity = commodity_config['count'] * commodity_config['production']['base_output_quantity']
    intermediary_capacity = intermediary_config['count'] * intermediary_config['production']['base_output_quantity']
    final_goods_capacity = final_goods_config['count'] * final_goods_config['production']['base_output_quantity']
    
    # Create comprehensive time evolution plot
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('REAL Climate 3-Layer Supply Chain: Time Evolution Analysis', fontsize=16, fontweight='bold')
    
    # Plot 1: Production evolution over time
    ax1.plot(rounds, commodity_production, 'o-', label='Commodity Production', color='#8B4513', linewidth=2, markersize=4)
    ax1.plot(rounds, intermediary_production, 's-', label='Intermediary Production', color='#DAA520', linewidth=2, markersize=4)
    ax1.plot(rounds, final_goods_production, '^-', label='Final Goods Production', color='#00FF00', linewidth=2, markersize=4)
    
    ax1.set_title('Production Levels Over Time (Real Data)', fontweight='bold')
    ax1.set_xlabel('Round')
    ax1.set_ylabel('Production Level')
    ax1.legend(loc='center right', fontsize=9)
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Wealth evolution by sector
    ax2.plot(rounds, commodity_wealth, 'o-', label='Commodity Producers', color='#8B4513', linewidth=2, markersize=4)
    ax2.plot(rounds, intermediary_wealth, 's-', label='Intermediary Firms', color='#DAA520', linewidth=2, markersize=4)
    ax2.plot(rounds, final_goods_wealth, '^-', label='Final Goods Firms', color='#00FF00', linewidth=2, markersize=4)
    ax2.plot(rounds, household_wealth, 'd-', label='Households', color='#4169E1', linewidth=2, markersize=4)
    ax2.set_title('Wealth Evolution by Sector (Real Data)', fontweight='bold')
    ax2.set_xlabel('Round')
    ax2.set_ylabel('Total Wealth ($)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Climate stress events over time
    ax3.plot(rounds, climate_stress_counts, 'ro-', linewidth=3, markersize=6)
    ax3.fill_between(rounds, climate_stress_counts, alpha=0.3, color='red')
    ax3.set_title('Climate Stress Events Over Time (Real Data)', fontweight='bold')
    ax3.set_xlabel('Round')
    ax3.set_ylabel('Number of Stressed Agents')
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Supply chain resilience analysis
    # Calculate production volatility as resilience metric
    commodity_volatility = np.std(commodity_production)
    intermediary_volatility = np.std(intermediary_production)
    final_goods_volatility = np.std(final_goods_production)
    
    # Calculate correlation between climate events and production drops
    production_changes = np.diff(commodity_production)
    climate_changes = np.diff(climate_stress_counts)
    
    ax4.axis('off')
    
    # Summary statistics from REAL simulation
    total_rounds = len(rounds)
    avg_climate_events = np.mean(climate_stress_counts)
    max_climate_events = np.max(climate_stress_counts)
    final_total_wealth = sum([commodity_wealth[-1], intermediary_wealth[-1], 
                             final_goods_wealth[-1], household_wealth[-1]])
    
    # Calculate supply chain impact propagation
    max_commodity_stress = max(climate_stress_counts) if climate_stress_counts else 0
    supply_chain_efficiency = (final_goods_production[-1] / final_goods_production[0] * 100) if final_goods_production[0] > 0 else 100
    
    summary_text = f"""
    REAL SIMULATION ANALYSIS SUMMARY
    
    📊 Simulation Overview:
    • Total Rounds: {total_rounds}
    • Final Total Wealth: ${final_total_wealth:.0f}
    • Supply Chain Efficiency: {supply_chain_efficiency:.1f}%
    
    🌪️ Climate Impact Analysis:
    • Average climate events per round: {avg_climate_events:.1f}
    • Maximum climate events in one round: {max_climate_events}
    • Total climate stress events: {sum(climate_stress_counts)}
    
    📈 Production Volatility (Resilience):
    • Commodity layer: {commodity_volatility:.2f}
    • Intermediary layer: {intermediary_volatility:.2f}
    • Final goods layer: {final_goods_volatility:.2f}
    
    💰 Final Production Levels:
    • Commodity: {commodity_production[-1]:.2f}
    • Intermediary: {intermediary_production[-1]:.2f}
    • Final Goods: {final_goods_production[-1]:.2f}
    """
    
    ax4.text(0.05, 0.95, summary_text, transform=ax4.transAxes, fontsize=10,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
    
    plt.tight_layout()
    
    # Save the time evolution plot
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{simulation_path}/climate_3layer_time_evolution_{timestamp}.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ Time evolution visualization saved: {filename}")
    
    plt.close()
    return filename

def create_animated_supply_chain(visualization_data, simulation_path, config_loader):
    """Create animated GIF showing supply chain evolution over time."""
    
    print("🎞️ Creating animated supply chain visualization...")
    
    # Calculate production capacities dynamically from configuration
    commodity_config = config_loader.get_agent_config('commodity_producer')
    intermediary_config = config_loader.get_agent_config('intermediary_firm')
    final_goods_config = config_loader.get_agent_config('final_goods_firm')
    
    commodity_capacity = commodity_config['count'] * commodity_config['production']['base_output_quantity']
    intermediary_capacity = intermediary_config['count'] * intermediary_config['production']['base_output_quantity']
    final_goods_capacity = final_goods_config['count'] * final_goods_config['production']['base_output_quantity']
    
    # Set up the animation plot with more subplots including geographical map
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 14))
    fig.suptitle('Climate 3-Layer Supply Chain Evolution (Animated)', fontsize=16, fontweight='bold')
    
    # Define continent positions for the world map (simplified layout)
    continent_positions = {
        'North America': (1, 3, 1.5, 1),     # (x, y, width, height)
        'South America': (1.2, 1.5, 1, 1.2),
        'Europe': (3, 3.2, 0.8, 0.6),
        'Africa': (3.2, 2, 0.8, 1.5),
        'Asia': (4.5, 2.5, 2, 1.8)
    }
    
    def animate(frame):
        # Clear all subplots
        for ax in [ax1, ax2, ax3, ax4]:
            ax.clear()
        
        if frame >= len(visualization_data['rounds']):
            return
        
        round_num = visualization_data['rounds'][frame]
        agent_data = visualization_data['agent_data'][frame]
        production_data = visualization_data['production_data'][frame]
        wealth_data = visualization_data['wealth_data'][frame]
        climate_events = visualization_data['climate_events'][frame]
        
        # Plot 1: Agent network with real stress status
        ax1.set_title(f'Supply Chain Network - Round {round_num}')
        ax1.set_xlim(0, 7)
        ax1.set_ylim(0, 4)
        
        # Define positions for consistent agent layout
        agent_positions = {
            'commodity_producer': [(1, 1), (1, 2), (1, 3)],
            'intermediary_firm': [(3, 1.5), (3, 2.5)],
            'final_goods_firm': [(5, 1.5), (5, 2.5)],
            'household': [(6.5, 0.5), (6.5, 1.5), (6.5, 2.5), (6.5, 3.5)]
        }
        
        agent_type_colors = {
            'commodity_producer': '#8B4513',
            'intermediary_firm': '#DAA520',
            'final_goods_firm': '#00FF00',
            'household': '#4169E1'
        }
        
        pos_idx = {'commodity_producer': 0, 'intermediary_firm': 0, 'final_goods_firm': 0, 'household': 0}
        
        for agent in agent_data:
            agent_type = agent['type']
            if agent_type in agent_positions and pos_idx[agent_type] < len(agent_positions[agent_type]):
                pos = agent_positions[agent_type][pos_idx[agent_type]]
                pos_idx[agent_type] += 1
                
                color = '#FF0000' if agent['climate_stressed'] else agent_type_colors[agent_type]
                size = 200 if agent['climate_stressed'] else 100
                
                ax1.scatter(pos[0], pos[1], c=color, s=size, alpha=0.8)
                ax1.text(pos[0], pos[1]-0.2, f"${agent['wealth']:.0f}", 
                        ha='center', fontsize=8)
        
        # Add supply chain flow arrows
        ax1.annotate('', xy=(2.8, 2), xytext=(1.2, 2), 
                    arrowprops=dict(arrowstyle='->', lw=2, color='gray'))
        ax1.annotate('', xy=(4.8, 2), xytext=(3.2, 2), 
                    arrowprops=dict(arrowstyle='->', lw=2, color='gray'))
        ax1.annotate('', xy=(6.3, 2), xytext=(5.2, 2), 
                    arrowprops=dict(arrowstyle='->', lw=2, color='gray'))
        
        ax1.text(1, 3.7, 'Layer 1\nCommodity', ha='center', fontsize=10, fontweight='bold')
        ax1.text(3, 3.7, 'Layer 2\nIntermediary', ha='center', fontsize=10, fontweight='bold')
        ax1.text(5, 3.7, 'Layer 3\nFinal Goods', ha='center', fontsize=10, fontweight='bold')
        ax1.text(6.5, 3.7, 'Households', ha='center', fontsize=10, fontweight='bold')
        
        # Plot 2: Production levels up to current frame
        ax2.set_title('Production Levels Over Time')
        rounds_so_far = visualization_data['rounds'][:frame+1]
        
        commodity_prod = [visualization_data['production_data'][i]['commodity'] for i in range(frame+1)]
        intermediary_prod = [visualization_data['production_data'][i]['intermediary'] for i in range(frame+1)]
        final_goods_prod = [visualization_data['production_data'][i]['final_goods'] for i in range(frame+1)]
        
        ax2.plot(rounds_so_far, commodity_prod, 'o-', label='Commodity', color='#8B4513')
        ax2.plot(rounds_so_far, intermediary_prod, 's-', label='Intermediary', color='#DAA520')
        ax2.plot(rounds_so_far, final_goods_prod, '^-', label='Final Goods', color='#00FF00')
        
        ax2.legend(fontsize=8, loc='upper left')
        ax2.set_xlabel('Round')
        ax2.set_ylabel('Production Level')
        ax2.grid(True, alpha=0.3)
        
        # Plot 3: Geographical Distribution World Map
        ax3.set_title(f'Global Climate Impact Map - Round {round_num}')
        ax3.set_xlim(0, 7)
        ax3.set_ylim(0, 5)
        ax3.set_aspect('equal')
        
        # Draw continent shapes (simplified rectangles)
        continent_colors = {}
        for continent in continent_positions.keys():
            # Default color
            base_color = '#90EE90'  # Light green for normal
            
            # Check if this continent has climate stress
            if climate_events and continent in climate_events:
                if 'stress' in str(climate_events[continent]):
                    base_color = '#FF6B6B'  # Red for climate stress
            
            continent_colors[continent] = base_color
            
            # Draw continent rectangle
            x, y, width, height = continent_positions[continent]
            continent_rect = plt.Rectangle((x, y), width, height, 
                                         facecolor=base_color, 
                                         edgecolor='black', 
                                         alpha=0.6)
            ax3.add_patch(continent_rect)
            
            # Add continent label
            ax3.text(x + width/2, y + height/2, continent.replace(' ', '\n'), 
                    ha='center', va='center', fontsize=8, fontweight='bold')
        
        # Place agents on their continents
        agent_counts_by_continent = {}
        for agent in agent_data:
            continent = agent['continent']
            if continent not in agent_counts_by_continent:
                agent_counts_by_continent[continent] = {
                    'commodity_producer': 0,
                    'intermediary_firm': 0, 
                    'final_goods_firm': 0,
                    'household': 0
                }
            agent_counts_by_continent[continent][agent['type']] += 1
        
        # Draw agent indicators on continents
        for continent, counts in agent_counts_by_continent.items():
            if continent in continent_positions:
                x, y, width, height = continent_positions[continent]
                
                # Position agents within continent bounds
                agent_positions_in_continent = [
                    (x + 0.2, y + height - 0.2),  # Top-left: commodity
                    (x + width - 0.2, y + height - 0.2),  # Top-right: intermediary
                    (x + 0.2, y + 0.2),  # Bottom-left: final goods
                    (x + width - 0.2, y + 0.2)   # Bottom-right: households
                ]
                
                agent_types = ['commodity_producer', 'intermediary_firm', 'final_goods_firm', 'household']
                agent_colors = ['#8B4513', '#DAA520', '#00FF00', '#4169E1']
                agent_symbols = ['o', 's', '^', 'D']
                
                for i, agent_type in enumerate(agent_types):
                    if counts[agent_type] > 0:
                        pos_x, pos_y = agent_positions_in_continent[i]
                        
                        # Check if agents of this type in this continent are stressed
                        stressed_agents = [a for a in agent_data 
                                         if a['continent'] == continent 
                                         and a['type'] == agent_type 
                                         and a['climate_stressed']]
                        
                        color = '#FF0000' if stressed_agents else agent_colors[i]
                        size = 150 if stressed_agents else 80
                        
                        ax3.scatter(pos_x, pos_y, c=color, s=size, marker=agent_symbols[i], 
                                  alpha=0.9, edgecolors='black', linewidth=1)
                        
                        # Add count label
                        ax3.text(pos_x, pos_y - 0.15, str(counts[agent_type]), 
                               ha='center', va='center', fontsize=6, fontweight='bold')
        
        # Add legend for agent types
        legend_elements = []
        agent_type_names = ['Commodity Producers', 'Intermediary Firms', 'Final Goods Firms', 'Households']
        agent_colors = ['#8B4513', '#DAA520', '#00FF00', '#4169E1']
        agent_symbols = ['o', 's', '^', 'D']
        
        for i, (name, color, symbol) in enumerate(zip(agent_type_names, agent_colors, agent_symbols)):
            legend_elements.append(plt.Line2D([0], [0], marker=symbol, color='w', 
                                            markerfacecolor=color, markersize=8, 
                                            label=name, markeredgecolor='black', markeredgewidth=0.5))
        
        # Add stress indicator to legend
        legend_elements.append(plt.Line2D([0], [0], marker='o', color='w', 
                                        markerfacecolor='#FF0000', markersize=10, 
                                        label='Climate Stressed', markeredgecolor='black', markeredgewidth=0.5))
        
        ax3.legend(handles=legend_elements, loc='lower right', fontsize=8, 
                  title='Agent Types', title_fontsize=9, framealpha=0.8)
        
        ax3.axis('off')  # Remove axes for cleaner world map look
        
        # Plot 4: Wealth distribution
        ax4.set_title('Wealth by Sector')
        wealth_types = list(wealth_data.keys())
        wealth_amounts = list(wealth_data.values())
        colors = ['#8B4513', '#DAA520', '#00FF00', '#4169E1']
        
        bars = ax4.bar(wealth_types, wealth_amounts, color=colors, alpha=0.7)
        ax4.set_ylabel('Total Wealth ($)')
        
        # Add wealth labels
        for bar, amount in zip(bars, wealth_amounts):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(wealth_amounts)*0.01, 
                    f'${amount:.0f}', ha='center', va='bottom', fontsize=9)
        
        plt.tight_layout()
    
    # Create animation
    num_frames = len(visualization_data['rounds'])
    anim = animation.FuncAnimation(fig, animate, frames=num_frames, interval=1500, repeat=True)
    
    # Save animation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{simulation_path}/climate_3layer_animation_{timestamp}.gif"
    
    print(f"💾 Saving animation as {filename}...")
    anim.save(filename, writer='pillow', fps=0.67)  # Slower fps for better readability
    print(f"✅ Animation saved: {filename}")
    
    plt.close()  # Clean up memory
    
    return filename

def collect_all_visualization_data(simulation_path, config_loader, climate_framework, num_rounds):
    """Collect visualization data for all rounds from the simulation CSV files."""
    
    print("📊 Collecting visualization data from simulation results...")
    visualization_data = {
        'rounds': [],
        'agent_data': [],
        'climate_events': [],
        'production_data': [],
        'wealth_data': []
    }
    
    # Read data for each round from the CSV files
    for r in range(num_rounds):
        round_data = collect_simulation_data(simulation_path, r, config_loader, climate_framework)
        
        visualization_data['rounds'].append(r)
        visualization_data['agent_data'].append(round_data['agents'])
        visualization_data['climate_events'].append(round_data['climate'])
        visualization_data['production_data'].append(round_data['production'])
        visualization_data['wealth_data'].append(round_data['wealth'])
        
        # Add debug info
        total_production = sum(round_data['production'].values())
        print(f"    Round {r}: Total production = {total_production:.2f} (commodity: {round_data['production']['commodity']:.2f}, intermediary: {round_data['production']['intermediary']:.2f}, final_goods: {round_data['production']['final_goods']:.2f})")
    
    print("✅ Visualization data collection completed!")
    return visualization_data

def run_animation_visualizations(simulation_path, config_file=None):
    """Main function to run all animation visualizations from simulation output."""
    
    print("🎬 Starting Animation Visualizer for Climate 3-Layer Model")
    print("=" * 60)
    
    # Load configuration
    if config_file is None:
        config_file = os.path.join(os.path.dirname(simulation_path), "model_config.json")
    
    if not os.path.exists(config_file):
        print(f"❌ Configuration file not found: {config_file}")
        return
    
    print(f"🔧 Loading configuration from: {config_file}")
    config_loader = load_model_config(config_file)
    
    # Try to detect number of rounds from CSV files
    production_file = os.path.join(simulation_path, 'panel_commodity_producer_production.csv')
    if not os.path.exists(production_file):
        print(f"❌ Simulation output not found in: {simulation_path}")
        print("Make sure you've run the simulation first!")
        return
    
    try:
        df = pd.read_csv(production_file)
        num_rounds = df['round'].max() + 1
        print(f"📊 Detected {num_rounds} rounds in simulation output")
    except Exception as e:
        print(f"❌ Error reading simulation data: {e}")
        return
    
    # Load REAL geographical assignments and climate events from CSV files
    print("🌍 Loading REAL geographical assignments from simulation data...")
    geographical_assignments = load_real_geographical_assignments(simulation_path)
    
    print("🌪️ Loading REAL climate events from simulation data...")
    climate_events_history = load_real_climate_events(simulation_path)
    
    # Ensure we have enough rounds in climate events (pad with empty events if needed)
    while len(climate_events_history) < num_rounds:
        climate_events_history.append({})
    
    # Create simple climate framework using real data
    climate_framework = ClimateFrameworkFromData(geographical_assignments, climate_events_history)
    
    print(f"✅ Using 100% REAL simulation data - no reconstruction needed!")
    
    # Collect visualization data
    visualization_data = collect_all_visualization_data(
        simulation_path, config_loader, climate_framework, num_rounds
    )
    
    if not visualization_data['rounds']:
        print("❌ No visualization data collected!")
        return
    
    # Create visualizations
    print("\n🎬 Creating time-evolving visualizations...")
    
    # Create time evolution plot
    time_plot_file = create_time_evolution_visualization(
        visualization_data, simulation_path, config_loader
    )
    
    # Create animated visualization
    animation_file = create_animated_supply_chain(
        visualization_data, simulation_path, config_loader
    )
    
    print(f"\n🎉 Animation visualizations completed!")
    print(f"📊 Time evolution plot: {time_plot_file}")
    print(f"🎞️ Animation: {animation_file}")
    
    return {
        'time_plot': time_plot_file,
        'animation': animation_file,
        'visualization_data': visualization_data
    }

def main():
    """Command line interface for the animation visualizer."""
    
    if len(sys.argv) < 2:
        print("Usage: python animation_visualizer.py <simulation_path> [config_file]")
        print("  simulation_path: Path to the simulation output directory")
        print("  config_file: Optional path to configuration file (default: model_config.json in parent directory)")
        sys.exit(1)
    
    simulation_path = sys.argv[1]
    config_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(simulation_path):
        print(f"❌ Simulation path does not exist: {simulation_path}")
        sys.exit(1)
    
    results = run_animation_visualizations(simulation_path, config_file)
    
    if results:
        print("\n✅ Animation visualization completed successfully!")
    else:
        print("\n❌ Animation visualization failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()
