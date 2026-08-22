import sys
import os
import numpy as np
from PIL import Image

# Add backend app to path
sys.path.append(os.path.abspath('.'))

# Load dotenv to get client credentials
from dotenv import load_dotenv
load_dotenv()

from app.api.endpoints import download_sentinel_data

try:
    sar_vv, sar_vh, opt_r, opt_g, opt_b, opt_nir = download_sentinel_data(25.6124, 85.1376)
    print("Download successful!")
    print("sar_vv shape:", sar_vv.shape, "min:", sar_vv.min(), "max:", sar_vv.max())
    print("opt_r shape:", opt_r.shape, "min:", opt_r.min(), "max:", opt_r.max())
    
    # Save optical image
    arr_opt = np.stack([opt_r, opt_g, opt_b], axis=-1)
    opt_img = Image.fromarray(arr_opt.astype(np.uint8))
    opt_img.save("test_opt.png")
    
    # Save SAR image
    vv_norm = ((sar_vv - sar_vv.min()) / (sar_vv.max() - sar_vv.min() + 1e-8) * 255.0).astype(np.uint8)
    sar_img = Image.fromarray(vv_norm, mode='L')
    sar_img.save("test_sar.png")
    
    print("Images saved as test_opt.png and test_sar.png")
except Exception as e:
    print("Error during test:", e)
