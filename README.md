whole project vibe coded with gemini-flash-2.5

# prerequirements
- activitywatch per window
- config zathurarc to show winow page
```
set window-title-basename 1
set window-title-page 1
```
- some python libraries on venv:
`pip install pandas requests matplotlib`

# usage
```
$ python3 zathura-analyzer.py -h
usage: zathura-analyzer.py [-h] [-i INITIAL_FILE] book_title page_range

Unified Zathura Activity Pipeline: Fetch -> Clean/Delta -> Analyze -> Plot.

positional arguments:
  book_title            A regex pattern or substring of the book title (e.g., 'Taha' or 'دستورکار'). Case-insensitive.
  page_range            The page range to analyze, format 'START-END' (e.g., '335-340').

options:
  -h, --help            show this help message and exit
  -i, --initial-file INITIAL_FILE
                        Optional path to a previous raw Zathura activity CSV (Snapshot 1) to calculate the reading delta. If
                        provided, the output will be the activity since this snapshot.
```
# example
## calculating total reading time
```
$ python3 zathura-analyzer.py "taha" "335-339"
✨ Step 1: Fetching AFK and window events...
   Processing events...
   Found 1246 Zathura events.
   Successfully saved raw Zathura activity snapshot to zathura_activity_raw.csv
🛠️ Step 2: Cleaning full activity data from: zathura_activity_raw.csv
   Successfully cleaned data (466 records) and saved to: zathura_activity_cleaned.csv

📊 Step 3: Starting data analysis and visualization...

--- Analysis Results for 'Operation_Research-Taha-8th Edition-2007.pdf' (Pages 335-339) ---
Total Unique Pages Analyzed: 5
Total Duration in Range: 37.65 minutes
Average Duration per Page (for unique pages in range): 7.53 minutes
------------------------------------------------------------
✅ Bar plot saved as: Operation_Research-Taha-8th Edition-2007_p335-339_analysis.png

🎉 Pipeline completed successfully!
```
image output:

<img width="1000" height="600" alt="Operation_Research-Taha-8th Edition-2007_p335-339_analysis" src="https://github.com/user-attachments/assets/9a9f5903-2e64-4d41-93d8-1382ac09ed3d" />

## calculating new reading session

```
$ python3 zathura-analyzer.py --initial-file snapshot_raw.csv "Taha" "335-339"
✨ Step 1: Fetching AFK and window events...
   Processing events...
   Found 1246 Zathura events.
   Successfully saved raw Zathura activity snapshot to zathura_activity_raw.csv
🔄 Step 2: Calculating delta activity between 'sanpshot_raw.csv' (Initial) and 'zathura_activity_raw.csv' (Newest)...
   Delta calculation complete. Total Session Time: 1.53 minutes.

📊 Step 3: Starting data analysis and visualization...

--- Analysis Results for 'Operation_Research-Taha-8th Edition-2007.pdf' (Pages 335-339) ---
Total Unique Pages Analyzed: 5
Total Duration in Range: 1.42 minutes
Average Duration per Page (for unique pages in range): 0.28 minutes
------------------------------------------------------------
✅ Bar plot saved as: Operation_Research-Taha-8th Edition-2007_p335-339_analysis.png

🎉 Pipeline completed successfully!
```
image output:

<img width="1000" height="600" alt="Operation_Research-Taha-8th Edition-2007_p335-339_analysis" src="https://github.com/user-attachments/assets/f61533d2-2c76-4cfd-b011-665056ba67b6" />

