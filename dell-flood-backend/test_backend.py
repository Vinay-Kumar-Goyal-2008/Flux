import sys
import os
import numpy as np

# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ml.inference import SegFormerMiTB2Fusion
from app.ml.postprocess import PostProcessor
from app.RAG.generator import SituationReportGenerator

def test_ml_inference():
    print("--------------------------------------------------")
    print("1. Testing ML Inference (SegFormer MiT-B2 Simulation)...")
    
    # Initialize model
    model = SegFormerMiTB2Fusion()
    
    # Create mock inputs
    sar_vv = np.random.normal(0, 1.0, (512, 512))
    sar_vh = np.random.normal(0, 1.0, (512, 512))
    opt_r = np.random.randint(0, 255, (512, 512), dtype=np.uint8)
    opt_g = np.random.randint(0, 255, (512, 512), dtype=np.uint8)
    opt_b = np.random.randint(0, 255, (512, 512), dtype=np.uint8)
    
    prob_map = model.run_inference(sar_vv, sar_vh, opt_r, opt_g, opt_b, cloud_cover_pct=15.0)
    
    assert prob_map.shape == (512, 512), f"Expected shape (512, 512), got {prob_map.shape}"
    assert np.min(prob_map) >= 0.0 and np.max(prob_map) <= 1.0, "Probabilities must be between 0.0 and 1.0"
    
    print("✓ Inference output shape and bounds verified successfully!")

def test_post_processing():
    print("--------------------------------------------------")
    print("2. Testing Post-Processing Layer...")
    
    processor = PostProcessor()
    
    # NDWI Calculation
    green = np.array([120, 180, 200])
    nir = np.array([30, 40, 240])
    ndwi = processor.compute_ndwi(green, nir)
    expected_ndwi = (green - nir) / (green + nir)
    assert np.allclose(ndwi, expected_ndwi), "NDWI calculations mismatch"
    print("✓ NDWI calculation verified.")

    # Permanent Water Subtraction
    flood_mask = np.array([[1, 1], [1, 0]], dtype=np.uint8)
    baseline_ndwi = np.array([[0.4, 0.1], [0.5, 0.2]]) # NDWI above 0.3 is water
    filtered = processor.filter_permanent_water(flood_mask, baseline_ndwi)
    # [0, 0] and [1, 0] should be filtered out (baseline ndwi > 0.3)
    assert filtered[0, 0] == 0, "Failed to filter permanent water at [0, 0]"
    assert filtered[0, 1] == 1, "Incorrect filter at [0, 1]"
    print("✓ Permanent water body subtraction verified.")

    # Noise Removal
    noisy_mask = np.zeros((100, 100), dtype=np.uint8)
    noisy_mask[10:12, 10:12] = 1 # Small noise component (4 pixels)
    noisy_mask[40:60, 40:60] = 1 # Large valid component (400 pixels)
    cleaned = processor.filter_noise(noisy_mask, min_size=10)
    assert np.sum(cleaned[10:12, 10:12]) == 0, "Noise pixels were not removed"
    assert np.sum(cleaned[40:60, 40:60]) == 400, "Valid flood pixels were removed"
    print("✓ Connected Components noise filter verified.")

    # Classification & Severity
    binary_mask = np.ones((512, 512), dtype=np.uint8)
    classification, area = processor.classify_water_body(binary_mask, 0.8)
    assert "Flood" in classification, f"Expected Flood in classification, got {classification}"
    
    severity, score = processor.calculate_severity_and_priority(
        area_sq_km=area,
        population_affected=15000,
        buildings_damaged=1200,
        critical_facilities_at_risk=8
    )
    assert severity == "CRITICAL", f"Expected severity CRITICAL, got {severity}"
    assert score >= 85.0, f"Expected priority score >= 85.0, got {score}"
    
    print("✓ Water classification and severity scoring verified.")

def test_rag_generation():
    print("--------------------------------------------------")
    print("3. Testing RAG Document Generation...")
    
    # Initialize generator
    generator = SituationReportGenerator(db_path="./test_chroma_data")
    
    # Generate report
    report = generator.generate_report(
        location="Muzaffarpur",
        area_sq_km=4.82,
        classification="Flood",
        severity="HIGH",
        population_affected=5200,
        buildings_damaged=240,
        facilities_at_risk=3
    )
    
    assert "MUZAFFARPUR" in report, "Report missing target location"
    assert "4.82" in report, "Report missing flood area metrics"
    assert "5,200" in report, "Report missing population metrics"
    
    print("✓ Semantic RAG report generation verified.")
    
    # Clean up test database directory
    try:
        import shutil
        if os.path.exists("./test_chroma_data"):
            shutil.rmtree("./test_chroma_data")
    except Exception as e:
        print(f"Error cleaning up test directory: {e}")

if __name__ == "__main__":
    print("STARTING BACKEND VERIFICATION SUITE")
    try:
        test_ml_inference()
        test_post_processing()
        test_rag_generation()
        print("--------------------------------------------------")
        print("ALL TESTS PASSED SUCCESSFULLY! BACKEND PIPELINE VERIFIED.")
    except AssertionError as e:
        print(f"TEST FAILURE: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR RUNNING TESTS: {e}")
        sys.exit(1)
