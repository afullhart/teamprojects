// ============================================================================
// 1. CONFIGURATION & CONSTANTS
// ============================================================================
var roi = ee.Geometry.Rectangle([-111.08, 31.20, -109.79, 32.06]);

// Full PARDIG-LR archive spans 1999-01-01T00:00:00Z to 2023-12-31T23:45:00Z
var START_DATE = '1999-01-01T00:00:00Z';
var END_DATE   = '2024-01-01T00:00:00Z'; // filterDate end is exclusive

// Unit conversion: m/hr -> mm/hr (1 m = 1,000 mm)
var M_HR_TO_MM_HR = 1000;

// Threshold in converted units (mm/hr) to retain a timestep.
// 0 omits strictly zero accumulation; raise slightly (e.g., 0.01) if float32 drizzle noise appears.
var MIN_PRECIP_MM_HR = 0;

// Cap number of pixel tasks queued during initial testing (set to null for all 117 pixels)
var MAX_PIXELS_TO_EXPORT = 5;
var EXPORT_FOLDER = 'PARDIG_LR_SRER_WGEW';

// ============================================================================
// 2. LOAD DATASET & EXTRACT NATIVE 0.1° PIXEL CENTROIDS
// ============================================================================
var pardig = ee.ImageCollection('projects/gcp-public-data-weathernext/assets/PARDIG_1_LR')
  .filterDate(START_DATE, END_DATE)
  .select('precipitation');

// Read native grid projection (EPSG:4326, 0.1° / ~11,132 m scale)
var nativeProj = pardig.first().projection();

// Sample exact pixel centroids on the native PARDIG grid inside the ROI
var pixelGrid = ee.Image.pixelLonLat()
  .reproject(nativeProj)
  .sample({
    region: roi,
    projection: nativeProj,
    geometries: true
  });

// Visualize ROI and pixel centroids
Map.centerObject(roi, 9);
Map.addLayer(roi, {color: 'gray'}, 'Full Study Extent');
Map.addLayer(pixelGrid, {color: 'red'}, 'PARDIG 0.1° Pixel Centroids');

// ============================================================================
// 3. QUEUE ONE CSV EXPORT TASK PER PIXEL
// ============================================================================
pixelGrid.toList(500).evaluate(function(pixelList) {
  if (!pixelList) {
    print('Failed to evaluate pixel list.');
    return;
  }

  var totalPixels = pixelList.length;
  var exportCount = MAX_PIXELS_TO_EXPORT ? Math.min(totalPixels, MAX_PIXELS_TO_EXPORT) : totalPixels;
  print('Total PARDIG pixels in ROI:', totalPixels, '| Queuing tasks:', exportCount);

  for (var i = 0; i < exportCount; i++) {
    var feat = pixelList[i];
    var lon = feat.properties.longitude;
    var lat = feat.properties.latitude;

    // Build clean coordinate filename (e.g., PARDIG_LR_px001_31p25N_111p05W)
    var latStr = Math.abs(lat).toFixed(2).replace('.', 'p') + (lat >= 0 ? 'N' : 'S');
    var lonStr = Math.abs(lon).toFixed(2).replace('.', 'p') + (lon >= 0 ? 'E' : 'W');
    var padIdx = ('000' + (i + 1)).slice(-3);
    var fileName = 'PARDIG_LR_px' + padIdx + '_' + latStr + '_' + lonStr;

    var ptGeom = ee.Geometry.Point([lon, lat]);

    // Extract single-pixel time series and convert m/hr -> mm/hr
    var pixelTimeSeries = pardig.map(function(img) {
      var valMmHr = img.multiply(M_HR_TO_MM_HR).reduceRegion({
        reducer: ee.Reducer.first(),
        geometry: ptGeom,
        crs: nativeProj
      }).get('precipitation');

      return ee.Feature(null, {
        'timestamp': img.get('start_time'),
        'precip_mm_hr': valMmHr
      });
    })
    // Omit 0-accumulation and masked/null timesteps
    .filter(ee.Filter.gt('precip_mm_hr', MIN_PRECIP_MM_HR));

    // Export CSV (selectors strip out system:index and .geo JSON columns to save space)
    Export.table.toDrive({
      collection: pixelTimeSeries,
      description: fileName,
      folder: EXPORT_FOLDER,
      fileNamePrefix: fileName,
      fileFormat: 'CSV',
      selectors: ['timestamp', 'precip_mm_hr']
    });
  }
});
