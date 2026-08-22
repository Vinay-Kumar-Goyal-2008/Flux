import sys
import os
import numpy as np
import cv2
from PIL import Image

sys.path.append(os.path.abspath('.'))

from dotenv import load_dotenv
load_dotenv()

from app.api.endpoints import download_sentinel_data
from app.ml.inference import SegFormerMiTB2Fusion

def run_test():
    print("Initializing model...")
    model = SegFormerMiTB2Fusion()
    
    print("Downloading Sentinel data for Patna (25.6124, 85.1376)...")
    sar_vv, sar_vh, opt_r, opt_g, opt_b, opt_nir = download_sentinel_data(25.6124, 85.1376)
    
    print("Running inference...")
    prob_map = model.run_inference(sar_vv, sar_vh, opt_r, opt_g, opt_b, opt_nir)
    
    print("Probability Map Stats:")
    print("Shape:", prob_map.shape)
    print("Min:", prob_map.min())
    print("Max:", prob_map.max())
    print("Mean:", prob_map.mean())
    print("Pixels > 0.4:", np.sum(prob_map > 0.4))
    print("Pixels > 0.7:", np.sum(prob_map > 0.7))
    
    # Save probability map as an image
    prob_img = Image.fromarray((prob_map * 255).astype(np.uint8))
    prob_img.save("prob_map_patna.png")
    print("Saved prob_map_patna.png")

if __name__ == "__main__":
    run_test()
