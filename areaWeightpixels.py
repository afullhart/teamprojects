import arcpy
from arcpy.sa import *
import numpy as np

# Set environment
#raster_path = r'C:\Users\andre\Documents\ArcGIS\Projects\MyProject2\Data\Erosivity_IMERGV06B_30min_2001_2021.tif'
#raster_path = r'C:\Users\andre\Documents\ArcGIS\Projects\MyProject2\Data\GloRESatE.tif'
raster_path = r'C:\Users\andre\Documents\ArcGIS\Projects\MyProject2\Data\Figure_A1a_IMERGV06_Erosivity.tif'
#raster_path = r'C:\Users\andre\Documents\ArcGIS\Projects\MyProject2\Data\Figure_A1b_Corrected_Erosivity.tif'
output_lat_raster = r'C:\Users\andre\Documents\ArcGIS\Projects\MyProject2\Data\latitude.tif'
output_area_raster = r'C:\Users\andre\Documents\ArcGIS\Projects\MyProject2\Data\area_km2.tif'
arcpy.env.workspace = r'C:\Users\andre\Documents\ArcGIS\Projects\MyProject2\Data'

arr = arcpy.RasterToNumPyArray(raster_path).astype(float)
l = arr.flatten()
print(l)
print(len(l))
print('pixel avg', np.nanmean(l))
print('filtered pixel avg', np.nanmean(l[(l > 1.0) & (l < 30000.0)]))

# Check out the Spatial Analyst extension
arcpy.CheckOutExtension('Spatial')

# 1. Describe the raster to get cell sizes
desc = arcpy.Describe(raster_path)
cell_size_y = abs(desc.meanCellHeight) # in degrees
cell_size_x = abs(desc.meanCellWidth)  # in degrees

input_raster = arcpy.Raster(raster_path)

lower_left_corner = input_raster.extent.lowerLeft
cell_size = cell_size_x
rows = input_raster.height
cols = input_raster.width
spatial_reference = input_raster.spatialReference

input_array = arcpy.RasterToNumPyArray(input_raster)

n_pixels = np.count_nonzero(~np.isnan(input_array))
print('non-nan pixel count: ', n_pixels)

# Create a NumPy array for latitudes
# Latitudes increase from the bottom row to the top row (south to north)
# The cell center coordinate is used, so start with the center of the bottom-left cell
latitudes = np.zeros((rows, cols), dtype=np.float32)

# 1. Calculate latitude for each row (y-coordinate)
# The y_coord starts from the bottom-left corner and increases upwards
for row in range(rows):
    y_coord = lower_left_corner.Y + (row * cell_size) + (cell_size / 2.0)
    latitudes[rows - 1 - row, :] = y_coord # Fill from top to bottom in array to match raster orientation

# Convert the NumPy array of latitudes back to a raster
# The spatial reference from the original raster is crucial
output_lat_raster = arcpy.NumPyArrayToRaster(latitudes, lower_left_corner, cell_size, cell_size, value_to_nodata=None)

# Define the spatial reference for the output raster (inherits from input)
arcpy.DefineProjection_management(output_lat_raster, spatial_reference)

latitude_raster = arcpy.Raster(output_lat_raster)

# 2. Convert latitude raster to radians
# Latitude (Y) is needed to calculate the cosine for shrinking longitude lengths
lat_radians = (latitude_raster * math.pi) / 180.0

# 3. Calculate Area in km2 using Raster Calculator
# 1 degree lat ≈ 111.32 km. Length of 1 degree lon ≈ 111.32 * cos(lat)
# Area ≈ (111.32 * cos(lat)) * (111.32) * cell_deg_x * cell_deg_y
pixel_area = (111.32 * Cos(lat_radians)) * (111.32 * cell_size_x * cell_size_y)

land_raster = input_raster
land_raster = Con(land_raster > 0.0, land_raster, np.nan)
#land_raster = Con(land_raster < 30000.0, land_raster, np.nan)
for_constant_pixel_area = Con(land_raster != np.nan, pixel_area, np.nan)

constant_value = arcpy.RasterToNumPyArray(for_constant_pixel_area).astype(float)
constant_value = np.where(constant_value > 0.0, constant_value, np.nan) 
constant_value = np.nansum(constant_value)
print('constant value', constant_value)
const_raster = CreateConstantRaster(float(constant_value), 'FLOAT', 0.1, Extent(-180, -90, 180, 90))
arcpy.DefineProjection_management(const_raster, spatial_reference)

weight_raster = land_raster * (pixel_area/const_raster)
weight_arr = arcpy.RasterToNumPyArray(weight_raster).astype(float)
weight_arr = np.where(weight_arr < 0.0, np.nan, weight_arr) 

print('shape', weight_arr.shape)
print('mean', np.nanmean(weight_arr))
print('sum', np.nansum(weight_arr))
print('count', np.sum(~np.isnan(weight_arr)))
area_avg = np.nansum(weight_arr)
print(area_avg)
