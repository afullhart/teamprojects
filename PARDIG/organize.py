import glob
import os
import pandas as pd

INPUT_DIR = r"C:\Users\andre\Desktop\PARDIG_LR_SRER_WGEW_Annual"
OUTPUT_DIR = r"C:\Users\andre\Desktop\Output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. Read and concatenate all 25 annual CSVs
csv_files = sorted(glob.glob(os.path.join(INPUT_DIR, "PARDIG_LR_AllPixels_*.csv")))
print(f"Found {len(csv_files)} annual files. Loading...")
df = pd.concat((pd.read_csv(f) for f in csv_files), ignore_index=True)

# Round coordinates to 2 decimal places to prevent float representation drift
df["lat_r"] = df["latitude"].round(2)
df["lon_r"] = df["longitude"].round(2)

# 2. Group by unique pixel coordinates and write 117 individual CSVs
unique_pixels = (
    df[["lat_r", "lon_r"]]
    .drop_duplicates()
    .sort_values(by=["lat_r", "lon_r"], ascending=[True, True])
    .reset_index(drop=True)
)

for idx, row in unique_pixels.iterrows():
    lat, lon = row["lat_r"], row["lon_r"]
    px_df = (
        df[(df["lat_r"] == lat) & (df["lon_r"] == lon)][["timestamp", "precip_mm_hr"]]
        .sort_values("timestamp")
    )

    lat_str = f"{abs(lat):.2f}".replace(".", "p") + ("N" if lat >= 0 else "S")
    lon_str = f"{abs(lon):.2f}".replace(".", "p") + ("E" if lon >= 0 else "W")
    fname = f"PARDIG_LR_px{idx + 1:03d}_{lat_str}_{lon_str}.csv"

    px_df.to_csv(os.path.join(OUTPUT_DIR, fname), index=False)

print(f"Created {len(unique_pixels)} pixel time-series CSVs in {OUTPUT_DIR}")

