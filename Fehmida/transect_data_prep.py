import pandas as pd
import os
import rasterio
from rasterio.windows import Window
import warnings
import re
import numpy as np

# Coordinates to split the study area (Lower Left to Upper Right)
bisect_coords = [[507000, 3518000], [519900, 3531540]]

# Suppress harmless warnings in the terminal
warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)

# Route the GDAL environment variables to your Miniconda installation
conda_base = r"C:\Users\andre\miniconda3"
os.environ['GDAL_DATA'] = os.path.join(conda_base, 'Library', 'share', 'gdal')
os.environ['PROJ_LIB'] = os.path.join(conda_base, 'Library', 'share', 'proj')

# 1. Load the datasets
file_path = r"C:\Users\andre\ltcover_2024Dec20.xlsx"
utm_path = r"C:\Users\andre\lttranutm.xls"
dates_path = r"C:\Users\andre\srer_transect_dates.csv"
raster_dir = r"C:\Users\andre\SRER_Predictive_Maps"  
output_dir = r"C:\Users\andre"
output_file_name = "transect_analysis_1984_onward.csv"

# Replace -9999 NoData values with 0 in the cover data
df = pd.read_excel(file_path).replace(-9999, 0)
df_utm = pd.read_excel(utm_path)
df_dates = pd.read_csv(dates_path)

# --- FIX 1: THE TRANSECT ID MISMATCH ---
def normalize_transect(t):
    # Removes leading zeros strictly on the numbers
    return re.sub(r'(?<!\d)0+(\d+)', r'\1', str(t))

cover_trans = df[['TRANSECT']].drop_duplicates().copy()
cover_trans['Norm_ID'] = cover_trans['TRANSECT'].apply(normalize_transect)

df_dates['Norm_ID'] = df_dates['Transect_ID'].apply(normalize_transect)

# Replace the old Transect_ID with the exact matching strings from df_cover
df_dates = pd.merge(df_dates, cover_trans, on='Norm_ID', how='inner')
df_dates = df_dates.drop(columns=['Transect_ID', 'Norm_ID'])
# ---------------------------------------

# 2. Extract a mapping of PASTTRAN to TRANSECT from the cover data
transect_map = df[['PASTTRAN', 'TRANSECT']].drop_duplicates()

# 3. Merge UTM coordinates
df_utm_clean = df_utm[['PASTTRAN', 'UTM X', 'UTM Y']]
utm_mapped = pd.merge(transect_map, df_utm_clean, on='PASTTRAN', how='left')[['TRANSECT', 'UTM X', 'UTM Y']]

# 4. Process the Dates file
df_dates['Date'] = pd.to_datetime(df_dates['Date'])
df_dates['Year'] = df_dates['Date'].dt.year
df_dates['Month'] = df_dates['Date'].dt.month
df_dates_clean = df_dates[['TRANSECT', 'Year', 'Month']].drop_duplicates(subset=['TRANSECT', 'Year'], keep='first')

# 5. Define the category groups
woody_codes = ["WOODY", "OTHCACTUS", "CHOLLA", "PPEAR"]
herbaceous_codes = ["NPG", "IPG", "PFORB"]

def assign_group(category):
    if category in woody_codes: return 'woody'
    elif category in herbaceous_codes: return 'herbaceous'
    else: return None

df['GROUP'] = df['CATEGORY'].apply(assign_group)
df_filtered = df.dropna(subset=['GROUP'])

# 6. Identify the columns for the year 1984 onward
year_cols = [col for col in df.columns if col.startswith('YR') and col[2:].isdigit() and int(col[2:]) >= 1984]

# 7. Reshape and aggregate the data
df_subset = df_filtered[['TRANSECT', 'GROUP'] + year_cols]
df_melted = df_subset.melt(id_vars=['TRANSECT', 'GROUP'], value_vars=year_cols, var_name='Year', value_name='Count')
df_melted['Year'] = df_melted['Year'].str.replace('YR', '').astype(int)
df_grouped = df_melted.groupby(['TRANSECT', 'Year', 'GROUP'])['Count'].sum().reset_index()

# 8. Pivot to final format
df_final = df_grouped.pivot(index=['TRANSECT', 'Year'], columns='GROUP', values='Count').fillna(0).reset_index()
df_final.columns.name = None

# 9. Merge the UTM coordinates AND Dates
df_final = pd.merge(df_final, utm_mapped, on='TRANSECT', how='left')
df_final = pd.merge(df_final, df_dates_clean, on=['TRANSECT', 'Year'], how='left')

df_final['Pred_BGR'] = float('nan')
df_final['Pred_Herb_pct'] = float('nan')
df_final['Pred_Woody_pct'] = float('nan')

# 10. --- Extract values from GeoTIFFs ---
valid_rows = df_final.dropna(subset=['Month', 'UTM X', 'UTM Y'])
print(f"Starting raster extraction for {len(valid_rows)} matched transect dates...")

for (year, month), group in valid_rows.groupby(['Year', 'Month']):
    raster_filename = f"SRER_Predictive_Maps_{int(year)}_{int(month):02d}.tif" 
    raster_path = os.path.join(raster_dir, raster_filename)
    
    if os.path.exists(raster_path):
        try:
            with rasterio.Env():
                with rasterio.open(raster_path) as src:
                    width, height = src.width, src.height
                    inv_transform = ~src.transform  
                    
                    for row_idx, row in group.iterrows():
                        transect = row['TRANSECT']
                        x, y = row['UTM X'], row['UTM Y']
                        
                        try:
                            col, row_pixel = inv_transform * (x, y)
                            px, py = int(col), int(row_pixel)
                            
                            # Ensure the 1x1 window doesn't fall off the edge of the map
                            if px < 0 or py < 0 or px >= width or py >= height:
                                continue
                            
                            # Extract EXACT single pixel
                            window = Window(px, py, 1, 1)
                            
                            # Read the pixel and flatten down to a 1D array of bands
                            pixel_data = src.read(window=window).astype(float).flatten()
                            
                            # STRICT NODATA FILTERING
                            pixel_data[pixel_data == -9999] = np.nan
                            pixel_data[pixel_data >= 65000] = np.nan
                            
                            if len(pixel_data) >= 5 and not np.isnan(pixel_data[3]):
                                df_final.at[row_idx, 'Pred_BGR'] = pixel_data[0]       
                                df_final.at[row_idx, 'Pred_Herb_pct'] = pixel_data[3]  
                                df_final.at[row_idx, 'Pred_Woody_pct'] = pixel_data[4] 
                                
                        except Exception as e:
                            print(f"   [ERROR] Failed to process {transect}: {e}")
                            
        except Exception as e:
            print(f"   [ERROR] Failed to open {raster_filename}: {e}")

# 11. Reorder, Split, and Export
print("\nFormatting and splitting output tables...")
cols = ['TRANSECT', 'Year', 'Month', 'UTM X', 'UTM Y', 'herbaceous', 'woody', 'Pred_BGR', 'Pred_Herb_pct', 'Pred_Woody_pct']
df_final = df_final[cols]

# --- NEW: BISECT THE DATASET ---
x1, y1 = bisect_coords[0]
x2, y2 = bisect_coords[1]

# Calculate the cross product to determine the mathematical side of the line
# Positive determinant = Northwest (left of line). Negative/Zero = Southeast (right of line)
determinant = (x2 - x1) * (df_final['UTM Y'] - y1) - (y2 - y1) * (df_final['UTM X'] - x1)

# Split into two new dataframes
df_nw = df_final[determinant > 0].copy()
df_se = df_final[determinant <= 0].copy()

# Setup the three file paths
output_path_main = os.path.join(output_dir, output_file_name)
output_path_nw = os.path.join(output_dir, output_file_name.replace(".csv", "_Northwest.csv"))
output_path_se = os.path.join(output_dir, output_file_name.replace(".csv", "_Southeast.csv"))

try:
    # Export all three
    df_final.to_csv(output_path_main, index=False)
    df_nw.to_csv(output_path_nw, index=False)
    df_se.to_csv(output_path_se, index=False)
    
    print(f"\nSUCCESS! Correlated datasets saved to:")
    print(f" 1. Full Dataset: {output_path_main} ({len(df_final)} rows)")
    print(f" 2. Northwest Subset: {output_path_nw} ({len(df_nw)} rows)")
    print(f" 3. Southeast Subset: {output_path_se} ({len(df_se)} rows)")
except PermissionError:
    print(f"\nCRITICAL ERROR: Could not save files because one is currently open in Excel or another program.")
except Exception as e:
    print(f"\nCRITICAL ERROR during save: {e}")
