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
RAW_CSV_FILENAME = "zathura_activity_raw.csv"
CLEANED_CSV_FILENAME = "zathura_activity_cleaned.csv"

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
    
    # Get all bucket IDs
    try:
        buckets_response = requests.get(f"{API_URL}/api/0/buckets")
        buckets_response.raise_for_status()
        buckets = buckets_response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching buckets: {e}")
        return False

    # Find the correct bucket IDs for AFK and window events
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
    
    # Create sets for easy lookup of non-AFK time intervals
    non_afk_intervals = []
    for event in afk_events:
        if event['data'].get('status') == 'not-afk':
            start = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            end = start + timedelta(seconds=event['duration'])
            non_afk_intervals.append((start, end))

    # Filter window events to keep only non-AFK, zathura events
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

    # Group events by title and sum up the duration
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
    
    # Convert to a list of dictionaries for writing to CSV
    data_list = []
    for title, data in grouped_activity.items():
        data_list.append({
            'title': title,
            'duration': data['duration'],
            'timestamp': data['timestamp']
        })

    # Sort the list by duration, from longest to shortest
    sorted_data = sorted(data_list, key=lambda x: x['duration'], reverse=True)
    
    # Save the sorted data to a CSV file
    try:
        with open(RAW_CSV_FILENAME, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["title", "duration", "timestamp"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerows(sorted_data)
        
        print(f"   Successfully saved raw Zathura activity to {RAW_CSV_FILENAME}")
        return True
    except IOError as e:
        print(f"An error occurred while writing the raw CSV file: {e}")
        return False

# --- 2. Data Cleaning (from zathura-data-cleaner.py) ---

def clean_and_save_data():
    """Cleans the raw CSV data and saves the processed result."""
    print(f"🛠️ Step 2: Starting data cleaning for: {RAW_CSV_FILENAME}")

    # --- Data Loading ---
    try:
        # Load the file with header and an encoding that supports Persian characters
        df = pd.read_csv(RAW_CSV_FILENAME, encoding='utf-8')
    except FileNotFoundError:
        print(f"Error: Raw input file '{RAW_CSV_FILENAME}' not found. Did the fetching step fail?")
        return False
    except Exception:
        # Fallback encoding
        try:
            df = pd.read_csv(RAW_CSV_FILENAME, encoding='iso-8859-1')
            print("   Warning: Used 'iso-8859-1' encoding for data loading.")
        except Exception as e:
            print(f"Error loading file with available encodings: {e}")
            return False

    # --- Cleaning and Transformation ---
    
    # Drop the 'timestamp' column as requested
    df = df.drop(columns=['timestamp'])

    # 1. Convert duration from seconds to minutes
    df['Duration_min'] = df['duration'] / 60

    # 2. Page Numbers Extraction: capture the two numbers inside brackets
    page_data = df['title'].str.extract(r'\[.*?(\d+)/(\d+).*?\]')
    # Use 'Int64' for integer column with support for pandas NaN (None)
    df['Current_Page'] = pd.to_numeric(page_data[0], errors='coerce').astype('Int64')
    df['Total_Pages'] = pd.to_numeric(page_data[1], errors='coerce').astype('Int64')

    # 3. Book Title Extraction: Remove the page part
    df['Book_Title'] = df['title'].str.replace(r'\s*\[.*', '', regex=True).str.strip()

    # 4. Drop original columns
    df = df.drop(columns=['title', 'duration'])

    # --- Saving ---
    df.to_csv(CLEANED_CSV_FILENAME, index=False)
    print(f"   Successfully cleaned data ({len(df)} records) and saved to: {CLEANED_CSV_FILENAME}")
    return True

# --- 3. Analysis and Plotting (from zathura-analyzer.py) ---

def analyze_and_plot(book_title_pattern, page_range):
    """Analyzes the cleaned data and generates a plot."""
    print("\n📊 Step 3: Starting data analysis and visualization...")

    # --- Data Loading ---
    try:
        # Load the cleaned data file
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
    
    # 1. Filter by Book Title using regex contains
    matching_df = df[
        df['Book_Title'].str.contains(book_title_pattern, case=False, na=False, regex=True)
    ].copy()

    unique_matches = matching_df['Book_Title'].unique()
    
    # Ambiguity Check
    if len(unique_matches) == 0:
        print(f"No book titles found matching the pattern: '{book_title_pattern}'.")
        sys.exit(0)
    
    if len(unique_matches) > 1:
        print(f"Ambiguity Error: Your search pattern '{book_title_pattern}' matched multiple books.")
        print("Please refine your pattern. Matches found:")
        for title in unique_matches:
            print(f"- {title}")
        sys.exit(1)

    # Successfully matched one book
    selected_title = unique_matches[0]
    df_filtered = matching_df
    
    # 2. Filter by Page Range
    df_filtered = df_filtered[
        (df_filtered['Current_Page'] >= start_page) &
        (df_filtered['Current_Page'] <= end_page)
    ]

    # --- Analysis and Output ---
    if df_filtered.empty:
        print(f"No records found for pages {start_page}-{end_page} in '{selected_title}'.")
        sys.exit(0)

    # Group by page and sum the duration (in case a page was viewed multiple times)
    df_agg = df_filtered.groupby('Current_Page')['Duration_min'].sum().reset_index()
    
    # Calculate Average Duration
    avg_duration = df_agg['Duration_min'].mean()

    print(f"\n--- Analysis Results for '{selected_title}' (Pages {start_page}-{end_page}) ---")
    print(f"Total Unique Pages Analyzed: {len(df_agg)}")
    print(f"Average Duration per Page (for unique pages in range): {avg_duration:.2f} minutes")
    print("-" * 60)
    
    # --- Visualization (Bar Plot with Average Line) ---
    plt.figure(figsize=(10, 6))
    
    df_plot = df_agg.sort_values(by='Current_Page')

    # Bar Plot
    # Ensure Current_Page is treated as the correct type for plotting
    x_labels = df_plot['Current_Page'].astype(int).tolist()
    x_positions = range(len(x_labels))

    plt.bar(x_positions, df_plot['Duration_min'], color='darkcyan', label='Duration per Page')

    # Horizontal Line for Average Duration
    plt.axhline(
        avg_duration,
        color='red',
        linestyle='--',
        linewidth=2,
        label=f'Average ({avg_duration:.2f} min)'
    )
    
    plt.title(f"Reading Duration per Page: {selected_title}\n(Pages {start_page} to {end_page})", fontsize=14)
    plt.xlabel("Page Number", fontsize=12)
    plt.ylabel("Duration (Minutes)", fontsize=12)
    
    # Set the x-ticks to the actual page numbers
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
        description="Unified Zathura Activity Pipeline: Fetch -> Clean -> Analyze -> Plot."
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
    args = parser.parse_args()

    # Execute the pipeline steps sequentially

    # 1. Fetch
    if not fetch_and_save_raw_data():
        print("Pipeline aborted after data fetching failure.")
        sys.exit(1)

    # 2. Clean
    if not clean_and_save_data():
        print("Pipeline aborted after data cleaning failure.")
        sys.exit(1)

    # 3. Analyze and Plot
    analyze_and_plot(args.book_title, args.page_range)
    
    print("\n🎉 Pipeline completed successfully!")

if __name__ == "__main__":
    main()
