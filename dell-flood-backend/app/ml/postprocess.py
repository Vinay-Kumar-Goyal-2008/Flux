import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

class PostProcessor:
    def __init__(self, elevation_threshold=5.0, ndwi_threshold=0.3):
        self.elevation_threshold = elevation_threshold
        self.ndwi_threshold = ndwi_threshold

    def compute_ndwi(self, green_band, nir_band):
        green = green_band.astype(float)
        nir = nir_band.astype(float)
        denominator = green + nir
        denominator[denominator == 0] = 1e-8
        return (green - nir) / denominator

    def filter_permanent_water(self, flood_mask, baseline_ndwi):
        # Deep permanent water threshold (only filters extreme deep clear reservoirs)
        permanent_water = baseline_ndwi > 0.85
        filtered_mask = np.copy(flood_mask)
        filtered_mask[permanent_water] = 0
        return filtered_mask

    def validate_with_dem(self, flood_mask, dem_elevation):
        # Ridge/mountain slope check: only clear high peak terrain
        median_elev = np.median(dem_elevation)
        high_ground = dem_elevation > (median_elev + 60.0)
        validated_mask = np.copy(flood_mask)
        validated_mask[high_ground] = 0
        return validated_mask

    def filter_noise(self, flood_mask, min_size=10):
        binary_mask = (flood_mask > 0).astype(np.uint8)
        if HAS_CV2:
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary_mask)
            cleaned_mask = np.zeros_like(flood_mask)
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area >= min_size:
                    cleaned_mask[labels == i] = 1
            return cleaned_mask
        else:
            # Pure Python/NumPy connected component labeling fallback
            h, w = binary_mask.shape
            visited = np.zeros((h, w), dtype=bool)
            cleaned_mask = np.zeros_like(flood_mask)
            
            for r in range(h):
                for c in range(w):
                    if binary_mask[r, c] == 1 and not visited[r, c]:
                        component = []
                        queue = [(r, c)]
                        visited[r, c] = True
                        while queue:
                            cr, cc = queue.pop(0)
                            component.append((cr, cc))
                            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                                nr, nc = cr + dr, cc + dc
                                if 0 <= nr < h and 0 <= nc < w:
                                    if binary_mask[nr, nc] == 1 and not visited[nr, nc]:
                                        visited[nr, nc] = True
                                        queue.append((nr, nc))
                        if len(component) >= min_size:
                            for cr, cc in component:
                                cleaned_mask[cr, cc] = 1
            return cleaned_mask

    def classify_water_body(self, binary_mask, avg_probability):
        total_pixels = np.sum(binary_mask)
        estimated_area_sq_km = total_pixels * 0.000019
        
        if estimated_area_sq_km < 0.03:
            return "Normal Conditions / Dry Ground", 0.0
            
        if estimated_area_sq_km < 0.2:
            classification = "Waterlogging"
        else:
            classification = "Flood Inundation"
            
        return classification, round(estimated_area_sq_km, 2)

    def calculate_severity_and_priority(self, area_sq_km, population_affected, buildings_damaged, critical_facilities_at_risk):
        if area_sq_km <= 0.03:
            return "NONE", 0.0

        if area_sq_km >= 1.0 or population_affected >= 1000:
            severity = "CRITICAL"
            score = 85.0 + min(12.0, area_sq_km * 4.0)
        elif area_sq_km >= 0.40 or population_affected >= 400:
            severity = "HIGH"
            score = 68.0 + min(15.0, area_sq_km * 12.0)
        elif area_sq_km >= 0.10 or population_affected >= 100:
            severity = "MODERATE"
            score = 45.0 + min(20.0, area_sq_km * 30.0)
        else:
            severity = "LOW"
            score = 25.0 + min(18.0, area_sq_km * 40.0)
            
        return severity, round(min(score, 99.0), 1)

    def generate_mock_dem(self):
        x = np.linspace(-3, 3, 512)
        y = np.linspace(-3, 3, 512)
        X, Y = np.meshgrid(x, y)
        
        base_elevation = 100.0 + (X**2 + Y**2) * 50.0
        np.random.seed(99)
        terrain_noise = np.random.normal(0, 2.0, (512, 512))
        
        return base_elevation + terrain_noise
