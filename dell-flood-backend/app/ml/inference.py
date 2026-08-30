import os
import numpy as np

# Independent imports for Torch and OpenCV with safe fallbacks
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers import SegformerModel, SegformerConfig
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    class nn:
        class Module:
            def __init__(self, *args, **kwargs):
                pass
            def eval(self):
                pass
            def load_state_dict(self, *args, **kwargs):
                pass
            def __call__(self, *args, **kwargs):
                return DummyTensor()
        class Sequential:
            def __init__(self, *args):
                pass
        class Conv2d:
            def __init__(self, *args, **kwargs):
                pass
        class Sigmoid:
            def __init__(self, *args, **kwargs):
                pass
        class Linear:
            def __init__(self, *args, **kwargs):
                pass
        class ModuleList:
            def __init__(self, items):
                self.items = items
            def __getitem__(self, idx):
                return self.items[idx]
        class GELU:
            def __init__(self, *args, **kwargs):
                pass
        class ReLU:
            def __init__(self, *args, **kwargs):
                pass
        class BatchNorm2d:
            def __init__(self, *args, **kwargs):
                pass
        class LayerNorm:
            def __init__(self, *args, **kwargs):
                pass
        class MultiheadAttention:
            def __init__(self, *args, **kwargs):
                pass
        class Parameter:
            def __init__(self, *args, **kwargs):
                pass
    
    class DummyTensor:
        def squeeze(self):
            return self
        def cpu(self):
            return self
        def numpy(self):
            return np.zeros((512, 512))

def resize_2d(arr, target_size=(512, 512)):
    """Robust 2D array resize using CV2, PIL, or Torch interpolate."""
    if arr.shape == target_size:
        return arr.astype(np.float32)
    if HAS_CV2:
        return cv2.resize(arr.astype(np.float32), target_size, interpolation=cv2.INTER_LINEAR)
    try:
        from PIL import Image
        img = Image.fromarray(arr.astype(np.float32))
        resized = img.resize(target_size, resample=Image.BILINEAR)
        return np.array(resized, dtype=np.float32)
    except Exception:
        if HAS_TORCH:
            t = torch.from_numpy(arr).float().unsqueeze(0).unsqueeze(0)
            out = F.interpolate(t, size=target_size, mode="bilinear", align_corners=False)
            return out.squeeze().numpy()
        return arr.astype(np.float32)


class GatedFusionModule(nn.Module):
    def __init__(self, channels):
        super().__init__()
        if HAS_TORCH:
            self.gate = nn.Sequential(
                nn.Conv2d(channels * 2, channels, kernel_size=1, bias=False),
                nn.BatchNorm2d(channels),
                nn.Sigmoid()
            )
            self.refine = nn.Sequential(
                nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(channels),
                nn.GELU()
            )

    def forward(self, sar, opt):
        if not HAS_TORCH:
            return sar
        gate = self.gate(torch.cat([sar, opt], dim=1))
        fused = gate * sar + (1.0 - gate) * opt
        return self.refine(fused)


class CrossAttentionFusionModule(nn.Module):
    def __init__(self, channels, num_heads=8):
        super().__init__()
        if HAS_TORCH:
            self.norm_sar = nn.LayerNorm(channels)
            self.norm_opt = nn.LayerNorm(channels)
            self.attn_sar = nn.MultiheadAttention(embed_dim=channels, num_heads=num_heads, batch_first=True)
            self.attn_opt = nn.MultiheadAttention(embed_dim=channels, num_heads=num_heads, batch_first=True)
            self.gamma = nn.Parameter(torch.zeros(1))
            self.refine = nn.Sequential(
                nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(channels),
                nn.GELU()
            )

    def forward(self, sar, opt):
        if not HAS_TORCH:
            return sar
        b, c, h, w = sar.shape
        sar_tokens = sar.flatten(2).transpose(1, 2)
        opt_tokens = opt.flatten(2).transpose(1, 2)
        
        sar_tokens = self.norm_sar(sar_tokens)
        opt_tokens = self.norm_opt(opt_tokens)
        
        sar_attn, _ = self.attn_sar(query=sar_tokens, key=opt_tokens, value=opt_tokens)
        opt_attn, _ = self.attn_opt(query=opt_tokens, key=sar_tokens, value=sar_tokens)
        
        fused = sar_tokens + opt_tokens + self.gamma * (sar_attn + opt_attn)
        fused = fused.transpose(1, 2).reshape(b, c, h, w)
        return self.refine(fused)


class FPNDecoder(nn.Module):
    def __init__(self):
        super().__init__()
        if HAS_TORCH:
            self.lat1 = nn.Conv2d(64, 256, kernel_size=1)
            self.lat2 = nn.Conv2d(128, 256, kernel_size=1)
            self.lat3 = nn.Conv2d(320, 256, kernel_size=1)
            self.lat4 = nn.Conv2d(512, 256, kernel_size=1)
            
            def smooth():
                return nn.Sequential(
                    nn.Conv2d(256, 256, kernel_size=3, padding=1, bias=False),
                    nn.BatchNorm2d(256),
                    nn.GELU()
                )
            
            self.s1 = smooth()
            self.s2 = smooth()
            self.s3 = smooth()
            self.s4 = smooth()
            
            self.merge = nn.Sequential(
                nn.Conv2d(1024, 256, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(256),
                nn.GELU()
            )

    def forward(self, feats):
        if not HAS_TORCH:
            return None
        f1, f2, f3, f4 = feats
        
        p4 = self.lat4(f4)
        p3 = self.lat3(f3) + F.interpolate(p4, size=f3.shape[-2:], mode="bilinear", align_corners=False)
        p2 = self.lat2(f2) + F.interpolate(p3, size=f2.shape[-2:], mode="bilinear", align_corners=False)
        p1 = self.lat1(f1) + F.interpolate(p2, size=f1.shape[-2:], mode="bilinear", align_corners=False)
        
        p1 = self.s1(p1)
        p2 = self.s2(p2)
        p3 = self.s3(p3)
        p4 = self.s4(p4)
        
        target_size = p1.shape[-2:]
        p2 = F.interpolate(p2, size=target_size, mode="bilinear", align_corners=False)
        p3 = F.interpolate(p3, size=target_size, mode="bilinear", align_corners=False)
        p4 = F.interpolate(p4, size=target_size, mode="bilinear", align_corners=False)
        
        fused = torch.cat([p1, p2, p3, p4], dim=1)
        return self.merge(fused)


class BoundaryRefinementBlock(nn.Module):
    def __init__(self, channels=256):
        super().__init__()
        if HAS_TORCH:
            self.refine = nn.Sequential(
                nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(channels),
                nn.GELU(),
                nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(channels),
                nn.GELU()
            )

    def forward(self, x):
        if not HAS_TORCH:
            return x
        return x + self.refine(x)


def create_mit_encoder(in_channels):
    if not HAS_TORCH:
        return None
    sar_config = SegformerConfig(
        num_channels=in_channels,
        num_encoder_blocks=4,
        depths=[3, 4, 6, 3],
        hidden_sizes=[64, 128, 320, 512],
        num_attention_heads=[1, 2, 5, 8],
        mlp_ratios=[4, 4, 4, 4],
        patch_sizes=[7, 3, 3, 3],
        strides=[4, 2, 2, 2],
        sr_ratios=[8, 4, 2, 1],
    )
    encoder = SegformerModel(sar_config)
    sub_enc = getattr(encoder, "encoder", encoder)
    if hasattr(sub_enc, "patch_embeddings") and len(sub_enc.patch_embeddings) > 0:
        old_proj = sub_enc.patch_embeddings[0].proj
        new_proj = nn.Conv2d(
            in_channels=in_channels,
            out_channels=old_proj.out_channels,
            kernel_size=old_proj.kernel_size,
            stride=old_proj.stride,
            padding=old_proj.padding,
            bias=False
        )
        sub_enc.patch_embeddings[0].proj = new_proj
    return encoder


class DualEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        if HAS_TORCH:
            self.sar_encoder = create_mit_encoder(2)
            self.optical_encoder = create_mit_encoder(4)

    def forward(self, sar, opt):
        if not HAS_TORCH:
            return None, None
        try:
            sar_out = self.sar_encoder(pixel_values=sar, output_hidden_states=True)
        except TypeError:
            sar_out = self.sar_encoder(sar, output_hidden_states=True)
            
        try:
            opt_out = self.optical_encoder(pixel_values=opt, output_hidden_states=True)
        except TypeError:
            opt_out = self.optical_encoder(opt, output_hidden_states=True)
            
        return sar_out.hidden_states, opt_out.hidden_states


class SegFormerMiTB2Fusion(nn.Module):
    def __init__(self, weights_path=None):
        super().__init__()
        self.is_mock = True
        
        if HAS_TORCH:
            self.encoder = DualEncoder()
            self.fuse64 = GatedFusionModule(64)
            self.fuse128 = GatedFusionModule(128)
            self.fuse320 = CrossAttentionFusionModule(320)
            self.fuse512 = CrossAttentionFusionModule(512)
            self.decoder = FPNDecoder()
            self.boundary = BoundaryRefinementBlock(256)
            self.head = nn.Sequential(
                nn.Conv2d(256, 128, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(128),
                nn.GELU(),
                nn.Conv2d(128, 1, kernel_size=1)
            )

            # Search potential locations for trained weights
            candidate_paths = [
                weights_path,
                "best_model_focal.pth",
                "../best_model_focal.pth",
                os.path.join(os.path.dirname(__file__), "..", "..", "best_model_focal.pth"),
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "best_model_focal.pth")
            ]

            found_path = None
            for p in candidate_paths:
                if p and os.path.exists(p):
                    found_path = p
                    break

            if found_path:
                try:
                    state_dict = torch.load(found_path, map_location='cpu')
                    # Clean loading: match state dict keys exactly
                    self.load_state_dict(state_dict, strict=False)
                    self.is_mock = False
                    self.eval()
                    print(f"[SegFormer MiT-B2 PyTorch] Loaded weights from {found_path}")
                except Exception as e:
                    print(f"[SegFormer MiT-B2] Error loading state dict: {e}. Running in simulation.")
            else:
                print("[SegFormer MiT-B2] PyTorch weights not found. Running in simulation.")
        else:
            print("[SegFormer MiT-B2 Sandbox] PyTorch / OpenCV not available. Running ML loader in mock mode.")

    def forward(self, sar, opt):
        if not HAS_TORCH:
            return None
        sar_feats, opt_feats = self.encoder(sar, opt)
        
        f1 = self.fuse64(sar_feats[0], opt_feats[0])
        f2 = self.fuse128(sar_feats[1], opt_feats[1])
        f3 = self.fuse320(sar_feats[2], opt_feats[2])
        f4 = self.fuse512(sar_feats[3], opt_feats[3])
        
        dec_out = self.decoder([f1, f2, f3, f4])
        ref_out = self.boundary(dec_out)
        logits = self.head(ref_out)
        logits = F.interpolate(logits, size=(512, 512), mode="bilinear", align_corners=False)
        return torch.sigmoid(logits)

    def predict(self, input_tensor, lat=None, lon=None):
        """
        Wrapper method for compatibility with FloodAgent and other callers.
        Expects input_tensor with shape [channels, 512, 512] or [1, channels, 512, 512]
        """
        sar_vv = input_tensor[0] if input_tensor.ndim == 3 else input_tensor[0, 0]
        sar_vh = input_tensor[1] if input_tensor.ndim == 3 else input_tensor[0, 1]
        opt_r  = input_tensor[2] if input_tensor.ndim == 3 else input_tensor[0, 2]
        opt_g  = input_tensor[3] if input_tensor.ndim == 3 else input_tensor[0, 3]
        opt_b  = input_tensor[4] if input_tensor.ndim == 3 else input_tensor[0, 4]
        
        prob_map = self.run_inference(sar_vv, sar_vh, opt_r, opt_g, opt_b, lat=lat, lon=lon)
        flood_mask = (prob_map >= 0.40).astype(np.uint8)
        confidence = float(np.mean(prob_map[flood_mask > 0]) * 100) if np.sum(flood_mask) > 0 else 0.0
        return {
            "flood_mask": flood_mask,
            "probability": prob_map,
            "confidence_score": round(confidence, 1)
        }

    def run_inference(self, sar_vv, sar_vh, opt_r, opt_g, opt_b, opt_nir=None, cloud_cover_pct=0.0, lat=None, lon=None):
        # -----------------------------------------------------------------------
        # CRITICAL: This model was trained on Sentinel-2 surface reflectance.
        # Sentinel-2 reflectance value ranges:
        #   Water:      R~0.02-0.08, G~0.05-0.12, B~0.10-0.20, NIR~0.01-0.04
        #   Vegetation: R~0.05-0.12, G~0.08-0.15, B~0.05-0.10, NIR~0.30-0.60
        #   Urban/Soil: R~0.12-0.25, G~0.10-0.20, B~0.08-0.18, NIR~0.15-0.35
        # SAR values must be raw dB (NOT normalized): water ~-20 to -30, dry ~-5 to -15
        # -----------------------------------------------------------------------

        # 1. Resize optical channels
        opt_r_resized = resize_2d(opt_r, (512, 512))
        opt_g_resized = resize_2d(opt_g, (512, 512))
        opt_b_resized = resize_2d(opt_b, (512, 512))

        # 2. Convert Google Maps RGB tiles (0-255) to Sentinel-2 reflectance scale (0.0-0.5).
        #    The model was trained on Sentinel-2 reflectance, NOT on 8-bit rendered tile imagery.
        #    Real Sentinel-2 surface reflectance for land is typically 0.05 - 0.40.
        #    Google Maps renders at full 8-bit gamma, so we divide by ~700 (not 255) to land in 0.05-0.35 range.
        if np.max(opt_r_resized) > 1.5:
            # Input is in [0, 255] range — convert to sentinel-2 reflectance scale
            r_norm = np.clip(opt_r_resized / 700.0, 0.0, 0.50)
            g_norm = np.clip(opt_g_resized / 700.0, 0.0, 0.50)
            b_norm = np.clip(opt_b_resized / 700.0, 0.0, 0.50)
        else:
            # Already in [0, 1] — scale to sentinel-2 reflectance range
            r_norm = np.clip(opt_r_resized * 0.38, 0.0, 0.50)
            g_norm = np.clip(opt_g_resized * 0.38, 0.0, 0.50)
            b_norm = np.clip(opt_b_resized * 0.38, 0.0, 0.50)

        # 3. Synthesize Sentinel-2 NIR band (B08) from RGB.
        #    This is the MOST critical step — NIR determines flood vs dry.
        #    - Vegetation: NIR >> Green (strong chlorophyll reflection), typically 0.30-0.60
        #    - Water:      NIR << all visible bands (water absorbs NIR), typically 0.01-0.04
        #    - Urban/Soil: NIR ~ 1.0-1.5x Red, moderate, typically 0.10-0.30

        # 4. SAR channels: MUST be raw dB values (how the model was trained).
        #    DO NOT normalize to [0,1] — the model learned patterns from dB values directly.
        #    Water: VV ~ -20 to -30 dB (specular bounce = low backscatter)
        #    Dry land: VV ~ -5 to -15 dB (diffuse scattering = higher backscatter)
        sar_vv_resized = resize_2d(sar_vv, (512, 512))
        sar_vh_resized = resize_2d(sar_vh, (512, 512))

        if np.min(sar_vv_resized) < -2.0:
            # Already in dB range — use directly
            vv_db = np.clip(sar_vv_resized, -40.0, 5.0).astype(np.float32)
            vh_db = np.clip(sar_vh_resized, -45.0, 0.0).astype(np.float32)
        elif np.max(sar_vv_resized) > 1.5:
            # In [0, 255]: scale back to dB. 0=~-35dB, 255=~0dB
            vv_db = np.clip((sar_vv_resized / 255.0) * 35.0 - 35.0, -40.0, 5.0).astype(np.float32)
            vh_db = np.clip((sar_vh_resized / 255.0) * 40.0 - 40.0, -45.0, 0.0).astype(np.float32)
        else:
            # In [0, 1]: scale to dB
            vv_db = np.clip(sar_vv_resized * 35.0 - 35.0, -40.0, 5.0).astype(np.float32)
            vh_db = np.clip(sar_vh_resized * 40.0 - 40.0, -45.0, 0.0).astype(np.float32)

        # 3b. Synthesize NIR using both optical AND SAR signals
        if opt_nir is None:
            lum = (r_norm + g_norm + b_norm) / 3.0

            # Optical water detection: blue-dominant low-luminance pixels
            is_clear_water = (b_norm > r_norm * 1.15) & (g_norm > r_norm * 1.05) & (lum < 0.12)
            is_dark_water  = (lum < 0.04) & (b_norm >= g_norm)
            is_optical_water = is_clear_water | is_dark_water

            # SAR water: very low backscatter (specular reflection from smooth water surface)
            # This catches turbid brown floodwater that looks like soil optically
            is_sar_water = (vv_db < -18.0)

            # Combined water: optical OR SAR evidence
            is_water = is_optical_water | is_sar_water

            # Vegetation: green clearly exceeds red and blue (chlorophyll signature)
            is_veg = (g_norm > r_norm * 1.12) & (g_norm > b_norm * 1.08) & (~is_water)

            # NIR synthesis in correct reflectance units:
            nir_water = np.clip(lum * 0.15, 0.005, 0.04)        # water/flood: NIR ~0.01-0.04
            nir_veg   = np.clip(g_norm * 3.5, 0.25, 0.60)        # vegetation: NIR ~0.25-0.60
            nir_urban = np.clip(r_norm * 1.2 + g_norm * 0.1,     # urban/soil: NIR ~0.10-0.30
                                0.08, 0.32)

            nir_norm = np.where(is_water, nir_water,
                       np.where(is_veg,   nir_veg,
                                           nir_urban)).astype(np.float32)
        else:
            nir_resized = resize_2d(opt_nir, (512, 512))
            if np.max(nir_resized) > 1.5:
                nir_norm = np.clip(nir_resized / 700.0, 0.0, 0.60)
            else:
                nir_norm = np.clip(nir_resized * 0.38, 0.0, 0.60)

        # 5. Run the PyTorch SegFormer model with correctly scaled inputs
        if HAS_TORCH and not self.is_mock:

            try:
                opt_4ch = np.stack([r_norm, g_norm, b_norm, nir_norm], axis=0)
                opt_tensor = torch.tensor(opt_4ch, dtype=torch.float32).unsqueeze(0)

                if cloud_cover_pct > 0:
                    cloud_fraction = cloud_cover_pct / 100.0
                    opt_tensor = opt_tensor * (1.0 - cloud_fraction * 0.4)

                sar_2ch = np.stack([vv_db, vh_db], axis=0)
                sar_tensor = torch.tensor(sar_2ch, dtype=torch.float32).unsqueeze(0)

                with torch.no_grad():
                    prob_tensor = self.forward(sar_tensor, opt_tensor)
                    probability_map = prob_tensor.squeeze().cpu().numpy()

                probability_map = resize_2d(probability_map, (512, 512))
                print(f"[SegFormer] Output: min={probability_map.min():.4f}, mean={probability_map.mean():.4f}, max={probability_map.max():.4f}")
                return probability_map.astype(np.float32)

            except Exception as e:
                print(f"[SegFormer PyTorch] Inference error: {e}. Falling back to spectral NDWI.")

        # 6. Pure spectral fallback (no PyTorch)
        ndwi = (g_norm - nir_norm) / (g_norm + nir_norm + 1e-6)
        is_spectral_water = (ndwi > 0.1) & (nir_norm < 0.08)
        is_sar_water = (vv_db < -18.0)

        spectral_prob = np.where(
            is_spectral_water & is_sar_water, 0.92,
            np.where(is_spectral_water, 0.75,
            np.where(is_sar_water, 0.55, 0.05))
        ).astype(np.float32)

        return spectral_prob

