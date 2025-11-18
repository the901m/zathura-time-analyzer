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
usage: zathura-analyzer.py [-h] book_title page_range

Unified Zathura Activity Pipeline: Fetch -> Clean -> Analyze -> Plot.

positional arguments:
  book_title  A regex pattern or substring of the book title (e.g., 'Taha' or 'دستورکار'). Case-insensitive.
  page_range  The page range to analyze, format 'START-END' (e.g., '335-340').

options:
  -h, --help  show this help message and exit
```
# example
```
$ python3 zathura-analyzer.py "Taha" "335-339"
✨ Step 1: Fetching AFK and window events...
   Processing events...
   Found 1239 Zathura events.
   Successfully saved raw Zathura activity to zathura_activity_raw.csv
🛠️ Step 2: Starting data cleaning for: zathura_activity_raw.csv
   Successfully cleaned data (467 records) and saved to: zathura_activity_cleaned.csv

📊 Step 3: Starting data analysis and visualization...

--- Analysis Results for 'Operation_Research-Taha-8th Edition-2007.pdf' (Pages 335-339) ---
Total Unique Pages Analyzed: 5
Average Duration per Page (for unique pages in range): 7.25 minutes
------------------------------------------------------------
✅ Bar plot saved as: Operation_Research-Taha-8th Edition-2007_p335-339_analysis.png

🎉 Pipeline completed successfully!

```
image output:

<img width="728" height="436" alt="image" src="https://github.com/user-attachments/assets/45a8e6e8-bc61-48b3-ad56-15c67ef600b8" />
