import pandas as pd
import re
import argparse
import sys
import requests
import json
import csv
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# --- Configuration ---
API_URL = "http://localhost:5600"
RAW_CSV_FILENAME = "zathura_activity_raw.csv" # Always the newest snapshot
CLEANED_CSV_FILENAME = "zathura_activity_cleaned.csv" # Contains full activity OR delta activity

# --- 1. Data Fetching (from zathura_csv.py) ---

def get_events_from_bucket(bucket_id, limit=10000):
    """Fetches all events from a specified bucket."""
    url = f"{API_URL}/api/0/buckets/{bucket_id}/events"
    params = {"limit": limit}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching events from bucket {bucket_id}: {e}")
        return None

def fetch_and_save_raw_data():
    """Fetches, processes, and exports Zathura activity to a raw CSV file."""
    print("✨ Step 1: Fetching AFK and window events...")
    
    try:
        buckets_response = requests.get(f"{API_URL}/api/0/buckets")
        buckets_response.raise_for_status()
        buckets = buckets_response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching buckets: {e}")
        return False

    afk_bucket_id = next((b for b in buckets if b.startswith("aw-watcher-afk_")), None)
    window_bucket_id = next((b for b in buckets if b.startswith("aw-watcher-window_")), None)

    if not afk_bucket_id or not window_bucket_id:
        print("Could not find required buckets. Make sure ActivityWatch is running.")
        return False

    afk_events = get_events_from_bucket(afk_bucket_id)
    window_events = get_events_from_bucket(window_bucket_id)

    if not afk_events or not window_events:
        print("Failed to fetch events. Exiting.")
        return False

    print("   Processing events...")
    
    non_afk_intervals = []
    for event in afk_events:
        if event['data'].get('status') == 'not-afk':
            start = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            end = start + timedelta(seconds=event['duration'])
            non_afk_intervals.append((start, end))

    zathura_events = []
    for event in window_events:
        event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        if event['data'].get('app') == 'org.pwmt.zathura' and event['duration'] > 0:
            is_afk = True
            for start, end in non_afk_intervals:
                if start <= event_time <= end:
                    is_afk = False
                    break
            if not is_afk:
                zathura_events.append(event)
    
    print(f"   Found {len(zathura_events)} Zathura events.")

    grouped_activity = {}
    for event in zathura_events:
        title = event['data'].get('title')
        if title:
            if title not in grouped_activity:
                grouped_activity[title] = {
                    'duration': 0,
                    'timestamp': event['timestamp']
                }
            grouped_activity[title]['duration'] += event['duration']
    
    data_list = []
    for title, data in grouped_activity.items():
        data_list.append({
            'title': title,
            'duration': data['duration'],
            'timestamp': data['timestamp']
        })

    sorted_data = sorted(data_list, key=lambda x: x['duration'], reverse=True)
    
    try:
        # Use csv.QUOTE_ALL for robust handling of titles with commas
        with open(RAW_CSV_FILENAME, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["title", "duration", "timestamp"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            
            writer.writeheader()
            writer.writerows(sorted_data)
        
        print(f"   Successfully saved raw Zathura activity snapshot to {RAW_CSV_FILENAME}")
        return True
    except IOError as e:
        print(f"An error occurred while writing the raw CSV file: {e}")
        return False

# --- Delta Calculation Helpers (Adapted from delta-calculator.py) ---

def _clean_and_prepare_file(input_file_name, session_tag):
    """Loads, cleans, and standardizes one raw Zathura activity CSV, extracting total pages."""
    try:
        # Use csv.QUOTE_ALL for robust handling of titles with commas
        df = pd.read_csv(input_file_name, encoding='utf-8', quoting=csv.QUOTE_ALL)
    except FileNotFoundError:
        print(f"Error: Input file '{input_file_name}' not found. Cannot calculate delta.")
        sys.exit(1)
    except Exception:
        try:
            df = pd.read_csv(input_file_name, encoding='iso-8859-1', quoting=csv.QUOTE_ALL)
        except Exception as e:
            print(f"Error loading file with available encodings: {e}")
            sys.exit(1)

    # Convert duration from seconds to minutes
    df['Duration_min'] = df['duration'] / 60
    
    # Extract Book Title, Current Page, AND Total Pages
    page_data = df['title'].str.extract(r'\[.*?(\d+)/(\d+).*?\]')
    df['Current_Page'] = pd.to_numeric(page_data[0], errors='coerce').astype('Int64')
    df['Total_Pages'] = pd.to_numeric(page_data[1], errors='coerce').astype('Int64')

    df['Book_Title'] = df['title'].str.replace(r'\s*\[.*', '', regex=True).str.strip()

    # Create a unique key for merging (Book + Page)
    df['key'] = df['Book_Title'] + "-" + df['Current_Page'].astype(str)
    
    # Keep only the necessary columns and rename duration to be session-specific
    df_cleaned = df[['key', 'Book_Title', 'Current_Page', 'Total_Pages', 'Duration_min']].copy()
    df_cleaned.rename(columns={'Duration_min': f'Duration_min_{session_tag}'}, inplace=True)
    
    return df_cleaned


def calculate_delta_activity(file_start, file_end):
    """Calculates the delta activity between two raw Zathura snapshots and saves the result."""
    print(f"🔄 Step 2: Calculating delta activity between '{file_start}' (Initial) and '{file_end}' (Newest)...")

    # Load and Clean Both Files
    df_start = _clean_and_prepare_file(file_start, 'Start')
    df_end = _clean_and_prepare_file(file_end, 'End')
    
    # Merge DataFrames
    df_merged = pd.merge(
        df_end[['key', 'Book_Title', 'Current_Page', 'Total_Pages', 'Duration_min_End']],
        df_start[['key', 'Duration_min_Start']], 
        on='key',
        how='left' 
    )
    
    # Fill NaN durations from the start file with 0 (pages read for the first time in this session)
    df_merged['Duration_min_Start'] = df_merged['Duration_min_Start'].fillna(0)
    
    # Calculate Delta
    df_merged['Duration_Delta_min'] = df_merged['Duration_min_End'] - df_merged['Duration_min_Start']

    # Final Filtering and Output Formatting
    df_session_activity = df_merged[df_merged['Duration_Delta_min'] > 0].copy()
    
    # Format the final DataFrame to match the 'zathura_activity_cleaned.csv' structure
    df_session_activity.rename(columns={'Duration_Delta_min': 'Duration_min'}, inplace=True)
    df_session_activity = df_session_activity[['Book_Title', 'Current_Page', 'Total_Pages', 'Duration_min']]
    df_session_activity['Duration_min'] = df_session_activity['Duration_min'].round(2)
    df_session_activity.sort_values(by=['Book_Title', 'Current_Page'], inplace=True)
    
    # Save the result to the standard cleaned file
    df_session_activity.to_csv(CLEANED_CSV_FILENAME, index=False)
    
    total_session_time = df_session_activity['Duration_min'].sum()
    print(f"   Delta calculation complete. Total Session Time: {total_session_time:.2f} minutes.")
    
    return True # Success

# --- 2. Data Cleaning (from zathura-data-cleaner.py) ---

def clean_and_save_full_data(input_file_name, output_file_name):
    """Cleans the raw CSV data (full activity) and saves the processed result."""
    print(f"🛠️ Step 2: Cleaning full activity data from: {input_file_name}")

    try:
        # Load the file with header and an encoding that supports Persian characters
        df = pd.read_csv(input_file_name, encoding='utf-8')
    except Exception:
        # Fallback encoding
        try:
            df = pd.read_csv(input_file_name, encoding='iso-8859-1')
            print("   Warning: Used 'iso-8859-1' encoding for data loading.")
        except Exception as e:
            print(f"Error loading file with available encodings: {e}")
            return False

    # 1. Convert duration from seconds to minutes
    df['Duration_min'] = df['duration'] / 60

    # 2. Page Numbers Extraction: capture the two numbers inside brackets
    page_data = df['title'].str.extract(r'\[.*?(\d+)/(\d+).*?\]')
    df['Current_Page'] = pd.to_numeric(page_data[0], errors='coerce').astype('Int64')
    df['Total_Pages'] = pd.to_numeric(page_data[1], errors='coerce').astype('Int64')

    # 3. Book Title Extraction: Remove the page part
    df['Book_Title'] = df['title'].str.replace(r'\s*\[.*', '', regex=True).str.strip()

    # 4. Drop original columns
    df = df.drop(columns=['title', 'duration', 'timestamp'])

    # --- Saving ---
    df.to_csv(output_file_name, index=False)
    print(f"   Successfully cleaned data ({len(df)} records) and saved to: {output_file_name}")
    return True

# --- 3. Analysis and Plotting (from zathura-analyzer.py) ---

def analyze_and_plot(book_title_pattern, page_range):
    """Analyzes the cleaned data (full or delta) and generates a plot."""
    print("\n📊 Step 3: Starting data analysis and visualization...")

    # --- Data Loading ---
    try:
        df = pd.read_csv(CLEANED_CSV_FILENAME)
    except FileNotFoundError:
        print(f"Error: '{CLEANED_CSV_FILENAME}' not found. Ensure the cleaning step succeeded.")
        sys.exit(1)

    # --- Page Range Parsing ---
    try:
        start_page, end_page = map(int, page_range.split('-'))
        if start_page > end_page or start_page < 1:
            raise ValueError
    except ValueError:
        print(f"Error: Invalid page range format. Use 'START-END', where START <= END and START >= 1. Example: '335-340'.")
        sys.exit(1)

    # --- Filtering (Regex Search Enabled) ---
    matching_df = df[
        df['Book_Title'].str.contains(book_title_pattern, case=False, na=False, regex=True)
    ].copy()

    unique_matches = matching_df['Book_Title'].unique()
    
    if len(unique_matches) == 0:
        print(f"No book titles found matching the pattern: '{book_title_pattern}'.")
        sys.exit(0)
    
    if len(unique_matches) > 1:
        print(f"Ambiguity Error: Your search pattern '{book_title_pattern}' matched multiple books.")
        print("Please refine your pattern. Matches found:")
        for title in unique_matches:
            print(f"- {title}")
        sys.exit(1)

    selected_title = unique_matches[0]
    df_filtered = matching_df
    
    df_filtered = df_filtered[
        (df_filtered['Current_Page'] >= start_page) &
        (df_filtered['Current_Page'] <= end_page)
    ]

    # --- Analysis and Output ---
    if df_filtered.empty:
        print(f"No records found for pages {start_page}-{end_page} in '{selected_title}'.")
        sys.exit(0)

    # Group by page and sum the duration
    df_agg = df_filtered.groupby('Current_Page')['Duration_min'].sum().reset_index()
    
    avg_duration = df_agg['Duration_min'].mean()
    total_duration = df_agg['Duration_min'].sum() # Calculate total duration for plot title

    print(f"\n--- Analysis Results for '{selected_title}' (Pages {start_page}-{end_page}) ---")
    print(f"Total Unique Pages Analyzed: {len(df_agg)}")
    print(f"Total Duration in Range: {total_duration:.2f} minutes")
    print(f"Average Duration per Page (for unique pages in range): {avg_duration:.2f} minutes")
    print("-" * 60)
    
    # --- Visualization (Bar Plot with Average Line) ---
    plt.figure(figsize=(10, 6))
    
    df_plot = df_agg.sort_values(by='Current_Page')

    x_labels = df_plot['Current_Page'].astype(int).tolist()
    x_positions = range(len(x_labels))

    plt.bar(x_positions, df_plot['Duration_min'], color='darkcyan', label='Duration per Page')

    plt.axhline(
        avg_duration,
        color='red',
        linestyle='--',
        linewidth=2,
        label=f'Average ({avg_duration:.2f} min)'
    )
    
    # UPDATED TITLE: Now includes Total Time
    plt.title(
        f"Reading Duration per Page: {selected_title}\n(Pages {start_page} to {end_page}) & Total Time: {total_duration:.2f} min", 
        fontsize=14
    )
    plt.xlabel("Page Number", fontsize=12)
    plt.ylabel("Duration (Minutes)", fontsize=12)
    
    plt.xticks(x_positions, x_labels, rotation=45, ha='right')
    
    plt.grid(axis='y', linestyle=':', alpha=0.5)
    plt.legend()
    plt.tight_layout()
    
    # Save the plot
    plot_filename = f"{selected_title.replace('.pdf', '')}_p{start_page}-{end_page}_analysis.png"
    plt.savefig(plot_filename)
    print(f"✅ Bar plot saved as: {plot_filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Unified Zathura Activity Pipeline: Fetch -> Clean/Delta -> Analyze -> Plot."
    )
    # Arguments for the final analysis step
    parser.add_argument(
        'book_title',
        type=str,
        help="A regex pattern or substring of the book title (e.g., 'Taha' or 'دستورکار'). Case-insensitive."
    )
    parser.add_argument(
        'page_range',
        type=str,
        help="The page range to analyze, format 'START-END' (e.g., '335-340')."
    )
    # New optional argument for delta calculation
    parser.add_argument(
        '-i',
        '--initial-file',
        type=str,
        default=None,
        help="Optional path to a previous raw Zathura activity CSV (Snapshot 1) to calculate the reading delta. If provided, the output will be the activity since this snapshot."
    )
    args = parser.parse_args()

    # 1. Fetch the Newest Activity Snapshot
    if not fetch_and_save_raw_data():
        print("Pipeline aborted after data fetching failure.")
        sys.exit(1)

    # 2. Clean or Calculate Delta
    if args.initial_file:
        # Delta Mode: Calculate the difference between the initial file and the newest snapshot
        if not calculate_delta_activity(args.initial_file, RAW_CSV_FILENAME):
            print("Pipeline aborted after delta calculation failure.")
            sys.exit(1)
    else:
        # Full Activity Mode: Clean the newest snapshot directly
        if not clean_and_save_full_data(RAW_CSV_FILENAME, CLEANED_CSV_FILENAME):
            print("Pipeline aborted after data cleaning failure.")
            sys.exit(1)

    # 3. Analyze and Plot
    analyze_and_plot(args.book_title, args.page_range)
    
    print("\n🎉 Pipeline completed successfully!")

if __name__ == "__main__":
    main()
