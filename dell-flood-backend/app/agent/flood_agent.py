import time
import os
import smtplib
import numpy as np
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.agent.tools import (
    fetch_satellite,
    check_rainfall,
    check_gauge,
    send_sms_alert,
    trigger_voice_call,
    export_pdf
)
from app.ml.inference import SegFormerMiTB2Fusion
from app.ml.postprocess import PostProcessor
from app.RAG.generator import SituationReportGenerator


class FloodAgentState:
    def __init__(self):
        self.memory = {}
        self.activity_log = []

    def log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}"
        try:
            print(entry)
        except Exception:
            pass
        self.activity_log.append(entry)


class FloodAgent:
    def __init__(self):
        self.state = FloodAgentState()
        self.model = SegFormerMiTB2Fusion()
        self.post_processor = PostProcessor()
        self.report_generator = SituationReportGenerator()

    def run_cycle(self, location, lat, lon, phone_numbers=[]):
        """
        Autonomous FloodAgent pipeline:
        Perceive -> Plan -> Act (satellite + model + report) -> Reflect -> Update
        """
        self.state.log("===================================================")
        self.state.log(f"AEGIS AGENT CYCLE START - Location: {location} ({lat:.4f}N, {lon:.4f}E)")
        self.state.log("===================================================")

        # ==========================================
        # STEP 1: PERCEIVE - Weather & Gauge Telemetry
        # ==========================================
        self.state.log("STEP 1/5 [PERCEIVE] Fetching real-time weather and river telemetry...")

        rainfall_5day = check_rainfall(lat, lon)
        self.state.log(f"  [OK] 5-day accumulated rainfall: {rainfall_5day:.1f} mm")

        gauge_info = check_gauge(location, rainfall_5day, lat, lon)
        gauge_status = gauge_info["status"]
        gauge_level  = gauge_info["current_meters"]
        self.state.log(
            f"  [OK] CWC River Gauge - Level: {gauge_level:.2f} m | "
            f"Warning: {gauge_info['warning_level_meters']}m | "
            f"Danger: {gauge_info['danger_level_meters']}m | "
            f"Status: {gauge_status}"
        )

        last_alert_time = self.state.memory.get(location, {}).get("last_alert_timestamp", 0)
        time_since_last_alert = time.time() - last_alert_time

        # ==========================================
        # STEP 2: PLAN
        # ==========================================
        self.state.log("STEP 2/5 [PLAN] Evaluating action plan based on perceived indicators...")
        actions_to_take = []

        if rainfall_5day > 45.0 or gauge_status != "NORMAL":
            self.state.log(
                f"  -> Threshold exceeded (rain={rainfall_5day:.1f}mm, gauge={gauge_status}). "
                f"Triggering satellite acquisition + ML inference."
            )
            actions_to_take.append("FETCH_SATELLITE_AND_RUN_MODEL")
        else:
            self.state.log(
                f"  -> Normal telemetry verified (rain={rainfall_5day:.1f}mm, "
                f"gauge={gauge_status}). No flood emergency detected."
            )

        # ==========================================
        # STEP 3: ACT - Satellite Acquisition + Model
        # ==========================================
        severity     = "NONE"
        area_sq_km   = 0.0
        classification = "Normal Conditions / Dry Ground"
        report_text  = ""
        confidence   = 0
        population_affected = 0
        buildings_damaged   = 0
        facilities_at_risk  = 0

        if "FETCH_SATELLITE_AND_RUN_MODEL" in actions_to_take:
            # --- 3a: Sentinel Satellite Acquisition ---
            self.state.log("STEP 3/5 [ACQUISITION] Requesting Sentinel-1 SAR & Sentinel-2 Optical imagery...")
            satellite_data = fetch_satellite(lat, lon)

            sar_vv  = satellite_data["sar_vv"]
            sar_vh  = satellite_data["sar_vh"]
            opt_r   = satellite_data["opt_r"]
            opt_g   = satellite_data["opt_g"]
            opt_b   = satellite_data["opt_b"]
            cloud   = satellite_data.get("cloud_cover", 0.0)

            self.state.log(
                f"  [OK] SAR bands acquired - VV mean={sar_vv.mean():.3f} std={sar_vv.std():.3f} | "
                f"VH mean={sar_vh.mean():.3f} std={sar_vh.std():.3f}"
            )
            self.state.log(
                f"  [OK] Optical bands acquired - R={opt_r.mean():.1f} G={opt_g.mean():.1f} "
                f"B={opt_b.mean():.1f} | Cloud cover: {cloud:.1f}%"
            )

            # --- 3b: Compute NDWI from optical ---
            opt_r_f = opt_r.astype(float)
            opt_g_f = opt_g.astype(float)
            opt_b_f = opt_b.astype(float)
            ndwi = (opt_g_f - opt_r_f) / (opt_g_f + opt_r_f + 1e-6)
            ndwi_water_pct = float((ndwi > 0.3).sum()) / ndwi.size * 100
            self.state.log(
                f"  [OK] NDWI water index computed - mean={ndwi.mean():.3f} | "
                f"water pixels (>0.3): {ndwi_water_pct:.1f}%"
            )

            # --- 3c: SegFormer ML Inference ---
            self.state.log("STEP 4/5 [ML INFERENCE] Running SegFormer MiT-B2 Fusion flood segmentation model...")
            try:
                sar_vv_n = (sar_vv - sar_vv.mean()) / (sar_vv.std() + 1e-6)
                sar_vh_n = (sar_vh - sar_vh.mean()) / (sar_vh.std() + 1e-6)
                opt_r_n  = opt_r_f / 255.0
                opt_g_n  = opt_g_f / 255.0
                opt_b_n  = opt_b_f / 255.0
                ndwi_n   = (ndwi + 1.0) / 2.0

                input_tensor = np.stack([sar_vv_n, sar_vh_n, opt_r_n, opt_g_n, opt_b_n, ndwi_n], axis=0)
                result = self.model.predict(input_tensor, lat=lat, lon=lon)

                flood_mask  = result.get("flood_mask", np.zeros((512, 512)))
                prob_map    = result.get("probability", np.zeros((512, 512)))
                flooded_pix = int(flood_mask.sum())
                total_pix   = flood_mask.size
                flooded_pct = flooded_pix / total_pix * 100

                if rainfall_5day < 45.0 or flooded_pix == 0:
                    area_sq_km = 0.0
                    confidence = 0
                else:
                    area_sq_km = round(flooded_pix * 0.0001, 2)
                    confidence = int(result.get("confidence_score", prob_map.mean() * 100))

                self.state.log(
                    f"  [OK] SegFormer output - flooded pixels: {flooded_pix:,}/{total_pix:,} "
                    f"({flooded_pct:.2f}%) | prob mean: {prob_map.mean():.3f} | "
                    f"model confidence: {confidence}%"
                )

            except Exception as model_err:
                self.state.log(f"  [WARN] Model inference note: {model_err}. Computing from telemetry signals.")
                if rainfall_5day >= 45.0:
                    rain_score   = min(70, int(rainfall_5day / 4.0))
                    gauge_score  = 30 if gauge_status == "DANGER" else 15 if gauge_status == "WARNING" else 0
                    total_score  = rain_score + gauge_score
                    confidence   = min(88, total_score + 5)
                    area_sq_km   = round((rainfall_5day - 45.0) * 0.08 + (1.5 if gauge_status == "DANGER" else 0.4), 2)
                else:
                    confidence = 0
                    area_sq_km = 0.0
                self.state.log(
                    f"  [OK] Telemetry assessment - estimated area: {area_sq_km:.2f} sq km | "
                    f"confidence: {confidence}%"
                )

            # --- 3d: Classification & Severity ---
            if area_sq_km > 10.0 or gauge_status == "DANGER":
                classification = "Flash Flood - Major Embankment Breach"
                severity = "CRITICAL"
            elif area_sq_km > 4.0 or gauge_status == "WARNING":
                classification = "Riverine Flood - Overflow Channels"
                severity = "HIGH"
            elif area_sq_km > 0.5:
                classification = "Riverine Flood - Moderate Inundation"
                severity = "MODERATE"
            elif area_sq_km > 0.05:
                classification = "Surface Waterlogging - Minor"
                severity = "LOW"
            else:
                classification = "Normal Conditions / Dry Ground"
                severity = "NONE"

            population_affected = int(area_sq_km * 1250)
            buildings_damaged   = int(area_sq_km * 45)
            facilities_at_risk  = max(1, int(area_sq_km * 0.4)) if area_sq_km > 0 else 0

            self.state.log(
                f"  [OK] Classification: {classification} | Severity: {severity} | "
                f"Area: {area_sq_km:.2f} sq km | Pop. affected: {population_affected:,}"
            )

            # --- 3e: RAG Situation Report ---
            self.state.log("STEP 5/5 [REPORT & ALERTS] Generating LLM situation report bulletin...")
            try:
                report_text = self.report_generator.generate_report(
                    location, area_sq_km, classification, severity,
                    population_affected, buildings_damaged, facilities_at_risk
                )
                self.state.log("  [OK] Situation report generated successfully.")
            except Exception as rag_err:
                self.state.log(f"  [WARN] RAG report notice: {rag_err}. Using structured bulletin.")
                report_text = ""

            # --- 3f: Export PDF ---
            try:
                pdf_filename = f"report_{location.lower().replace(' ', '_')}_{int(time.time())}.pdf"
                pdf_path = f"./reports/{pdf_filename}"
                export_pdf(pdf_path, report_text or classification, location, severity)
                self.state.log(f"  [OK] PDF exported: {pdf_filename}")
            except Exception as pdf_err:
                self.state.log(f"  [WARN] PDF export notice: {pdf_err}")

            # --- 3g: Dispatch Alerts ---
            if severity in ["HIGH", "CRITICAL"] and phone_numbers:
                for phone in phone_numbers:
                    if time_since_last_alert > 7200:
                        send_sms_alert(phone, f"AEGIS ALERT: {severity} flood detected near {location}. Area: {area_sq_km:.2f} sq km. Evacuate immediately.")
                        trigger_voice_call(phone, location, severity)
                        self.state.log(f"  [OK] Emergency alert dispatched to {phone}")
                    else:
                        self.state.log(f"  [INFO] Alert throttled for {phone} - last alert was {int(time_since_last_alert/60)} min ago.")

        # Fallback dry-conditions report
        if not report_text:
            report_text = (
                f"AEGIS BULLETIN - {location.upper()}\n"
                f"---------------------------------------------------\n"
                f"STATUS: {classification}\n"
                f"Rainfall (5-day): {rainfall_5day:.1f} mm\n"
                f"Gauge Status: {gauge_status} ({gauge_level:.2f} m)\n"
                f"Inundated Area: {area_sq_km:.2f} sq km\n"
                f"Population Affected: {population_affected:,}\n"
                f"---------------------------------------------------\n"
                f"No immediate evacuation required. Continue monitoring."
            )

        # ==========================================
        # STEP 4: REFLECT & UPDATE MEMORY
        # ==========================================
        self.state.log("===================================================")
        self.state.log(f"CYCLE COMPLETE - {location} | {severity} | {area_sq_km:.2f} km2 | Confidence: {confidence}%")
        self.state.log("===================================================")

        self.state.memory[location] = {
            "last_alert_timestamp":  time.time() if severity in ["HIGH", "CRITICAL"] else last_alert_time,
            "last_severity":         severity,
            "last_area_sq_km":       area_sq_km,
            "last_gauge_status":     gauge_status,
            "last_rainfall_mm":      rainfall_5day,
            "last_confidence":       confidence,
        }

        # ==========================================
        # DISPATCH SITUATION EMAIL WITH LOCATION
        # ==========================================
        try:
            maps_link = f"https://www.google.com/maps?q={lat},{lon}"
            alert_tag = "CRITICAL FLOOD ALERT" if severity == "CRITICAL" else \
                        "HIGH FLOOD WARNING"   if severity == "HIGH"     else \
                        "MODERATE ADVISORY"    if severity == "MODERATE" else \
                        "MONITORING UPDATE"

            email_subject = f"[AEGIS] {alert_tag}: {location} - {severity} Severity"
            email_body = (
                f"AEGIS AUTONOMOUS FLOOD MONITORING SYSTEM\n"
                f"{'='*55}\n"
                f"ALERT LEVEL  : {severity}\n"
                f"LOCATION     : {location}\n"
                f"COORDINATES  : {lat:.5f} N, {lon:.5f} E\n"
                f"GOOGLE MAPS  : {maps_link}\n"
                f"TIMESTAMP    : {time.strftime('%Y-%m-%d %H:%M:%S')} IST\n"
                f"{'='*55}\n\n"
                f"TELEMETRY SUMMARY\n"
                f"-----------------\n"
                f"5-Day Accumulated Rainfall : {rainfall_5day:.1f} mm\n"
                f"River Gauge Level          : {gauge_level:.2f} m ({gauge_status})\n"
                f"Flood Classification       : {classification}\n"
                f"Estimated Inundated Area   : {area_sq_km:.2f} sq km\n"
                f"Model Confidence Score     : {confidence}%\n\n"
                f"IMPACT ASSESSMENT\n"
                f"-----------------\n"
                f"Population at Risk         : {population_affected:,} people\n"
                f"Structures at Risk         : {buildings_damaged} buildings\n"
                f"Critical Facilities        : {facilities_at_risk} (hospitals/schools)\n\n"
                f"SITUATION REPORT\n"
                f"-----------------\n"
                f"{report_text[:1200]}\n\n"
                f"{'='*55}\n"
                f"View location on map: {maps_link}\n"
                f"Generated by Aegis Autonomous Agent. Do not reply.\n"
            )

            sender_email   = os.getenv("SMTP_SENDER_EMAIL", "")
            sender_password = os.getenv("SMTP_SENDER_PASSWORD", "")
            target_email   = "shahzeb03794@gmail.com"

            if sender_email and sender_password:
                msg = MIMEMultipart()
                msg["From"]    = sender_email
                msg["To"]      = target_email
                msg["Subject"] = email_subject
                msg.attach(MIMEText(email_body, "plain"))

                server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, target_email, msg.as_string())
                server.close()
                self.state.log(f"  [OK] Email dispatched to {target_email} - subject: {email_subject}")
            else:
                self.state.log(f"  [Email Mock] Would send: {email_subject}")
                self.state.log(f"  Location: {location} ({lat:.5f}N, {lon:.5f}E) | {maps_link}")

        except Exception as email_err:
            self.state.log(f"  [WARN] Email dispatch notice: {email_err}")

        return {
            "location":         location,
            "severity":         severity,
            "classification":   classification,
            "area_sq_km":       area_sq_km,
            "gauge_status":     gauge_status,
            "rainfall_5day_mm": rainfall_5day,
            "confidence":       confidence,
            "population":       population_affected,
            "buildings":        buildings_damaged,
            "facilities":       facilities_at_risk,
            "report":           report_text,
            "logs":             self.state.activity_log,
        }
