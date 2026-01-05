import re
import json
import pdfplumber
from pathlib import Path

DOWNLOADS_DIR = Path("downloads")
OUTPUT_DIR = Path("json_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# -------------------------
# Helpers
# -------------------------

def map_to_required_schema(pdf_path, crash, vehicle, driver):
    # split date safely
    date_of_crash = ""
    if crash.get("crash_datetime"):
        date_of_crash = crash["crash_datetime"].split(" ")[0]

    return {
        "incident_number": crash.get("incident_number", ""),
        "report_number": crash.get("report_number", ""),
        "department": crash.get("department", ""),
        "state_code": "",
        "state_abbreviation": "OH",
        "state_name": "OHIO",
        "county_code": "",
        "county": "",
        "municipality_code": "",
        "municipality": "",
        "crash_location": crash.get("township", ""),
        "crash_type_l1": "",
        "crash_type_l2": "",
        "date_of_crash": date_of_crash,
        "total_killed": "",
        "total_injured": "",
        "total_vehicles": "",
        "case_file_s3_path": "",
        "s3_bucket_name": "",
        "s3_access_key": "",
        "s3_secret_key": "",
        "pdf_file_path": str(pdf_path),

        "case_detail": [
            {
                "local_information": "",
                "locality": "TOWNSHIP",
                "location": "NA",
                "route_type": "SR",
                "route_number": crash.get("route_number", ""),
                "route_prefix": "NA",
                "lane_speed_limit_1": "",
                "lane_speed_limit_2": "",
                "crash_severity": ""
            }
        ],

        "vehicles": [
            {
                "vehicle_unit": "1",
                "is_commercial": "0",
                "make": vehicle.get("vehicle_make", ""),
                "model": vehicle.get("vehicle_model", ""),
                "vehicle_year": vehicle.get("vehicle_year", ""),
                "plate_number": vehicle.get("license_plate", ""),
                "plate_state": "OH",
                "plate_year": "",
                "vin": vehicle.get("vin", ""),
                "policy": "",
                "is_driven": "",
                "is_left_at_scene": "",
                "is_towed": "",
                "is_impounded": "",
                "is_disabled": "",
                "is_parked": "0",
                "is_pedestrian": "",
                "is_pedal_cyclist": "",
                "is_hit_and_run": "0",
                "vehicle_used": "",
                "vehicle_type": "1",
                "trailer_or_carrier_count": "0",
                "color": "",
                "vehicle_body_type": "",
                "vehicle_travel_direction": "",

                "vehicle_details": {
                    "crash_seq_1st_event": "",
                    "crash_seq_2nd_event": "",
                    "crash_seq_3rd_event": "",
                    "crash_seq_4th_event": "",
                    "harmful_event": "",
                    "authorized_speed": vehicle.get("posted_speed", ""),
                    "estimated_original_speed": "",
                    "estimated_impact_speed": "",
                    "tad": "",
                    "estimated_damage": "",
                    "most_harmful_event": "",
                    "insurance_company": vehicle.get("insurance_company", ""),
                    "insurance_verified": "",
                    "us_dot": "",
                    "towed_by": "",
                    "occupant_count": "",
                    "initial_impact": "",
                    "contributing_circumstance": "",
                    "damage_severity": "",
                    "damaged_area": "",
                    "vehicle_defects": "",
                    "overweight_permit": ""
                },

                "persons": [
                    {
                        "person_type": "DRIVER",
                        "first_name": "",
                        "middle_name": "",
                        "last_name": driver.get("driver_name", ""),
                        "same_as_driver": "1",

                        "address_block": {
                            "address_line1": "",
                            "address_city": "",
                            "address_state": "",
                            "address_zip": ""
                        },

                        "seating_position": "",
                        "date_of_birth": driver.get("dob", ""),
                        "gender": driver.get("gender", ""),
                        "alcohol_or_drug_involved": "",
                        "ethnicity": "",
                        "occupant": "",
                        "airbag_deployed": "",
                        "airbag_status": "",
                        "trapped": "",
                        "ejection": "",
                        "injury": "",
                        "ems_name": "",
                        "injured_taken_by_ems": "",
                        "age": driver.get("age", ""),
                        "injured_taken_to": "",
                        "driver_info_id": "",
                        "alcohol_test_status": "",
                        "alcohol_test_type": "",
                        "alcohol_test_value": "",
                        "drug_test_status": "",
                        "drug_test_type": "",
                        "drug_test_value": "",
                        "offense_charged": "",
                        "local_code": "",
                        "offense_description": "",
                        "citation_number": driver.get("citation_number", ""),
                        "contact_number": "",
                        "ol_class": "",
                        "endorsement": "",
                        "restriction": "",
                        "driver_distracted_by": "",
                        "driving_license": "",
                        "dl_state": "OH",
                        "alcohol_or_drug_suspected": driver.get("alcohol_suspected", "")
                    }
                ]
            }
        ]
    }


def normalize_text(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def find(pattern, text, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    if not m:
        return None
    # If pattern has a capturing group, return it; else return full match
    return (m.group(1) if m.lastindex else m.group(0)).strip()

# -------------------------
# Page 1: Crash Info
# -------------------------
def extract_crash_info(text: str) -> dict:
    return {
        # Incident Number → LOCAL REPORT NUMBER
        "incident_number": find(r"\b\d{2}-\d{4}-\d{2}\b", text),

        # ✅ Report Number → LOCAL INFORMATION (P25102200000570)
        "report_number": find(
            r"LOCAL\s+INFORMATION\s+([A-Z]\d{11,})",
            text
        ),
        
        "department": find(
            r"REPORTING\s+AGENCY\s+NAME\s*\?\s([A-Za-z][A-Za-z\s]+)",
            text
        ),


        "crash_datetime": find(
            r"\b\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\b",
            text
        ),

        "latitude": find(
            r"LATITUDE\sDECIMAL\sDEGREES\s*([0-9]+\.[0-9]+)",
            text
        ),

        "longitude": find(
            r"LONGITUDE\sDECIMAL\sDEGREES\s*(-[0-9]+\.[0-9]+)",
            text
        ),

        "township": find(
            r"LOCATION:\sCITY,\sVILLAGE,\sTOWNSHIP\\s*([A-Za-z\s\(\)]+)",
            text
        ),

        "route_number": find(r"\bSR\s*(\d{1,3})\b", text),
    }

# -------------------------
# Page 2: Vehicle Info
# -------------------------
def extract_vehicle_info(text: str) -> dict:
    return {
        "owner_name": find(r"OWNER NAME.*?\s([A-Z,\s]+)", text),
        "vehicle_make": find(r"VEHICLE MAKE\s*([A-Z]+)", text),
        "vehicle_model": find(r"VEHICLE MODEL\s*([A-Z0-9\-]+)", text),
        "vehicle_year": find(r"\b(19|20)\d{2}\b", text),
        "license_plate": find(r"LICENSE PLATE #\s*([A-Z0-9]+)", text),
        "vin": find(r"VEHICLE IDENTIFICATION #\s*([A-Z0-9]+)", text),
        "posted_speed": find(r"POSTED SPEED\s*(\d+)", text),
        "insurance_company": find(r"INSURANCE COMPANY\s*([A-Z\s]+)", text),
    }

# -------------------------
# Page 3: Driver Info
# -------------------------
def extract_driver_info(text: str) -> dict:
    return {
        "driver_name": find(r"NAME:\sLAST,\sFIRST,\sMIDDLE\s([A-Z,\s]+)", text),
        "dob": find(r"\b\d{2}/\d{2}/\d{4}\b", text),
        "age": find(r"AGE\s*(\d{1,3})", text),
        "gender": find(r"\b(F|M|U)\b", text),
        "address": find(r"ADDRESS:\sSTREET,\sCITY,\sSTATE,\sZIP\s*([A-Z0-9,\s]+)", text),
        "citation_number": find(r"CITATION NUMBER\s*([A-Z0-9]+)", text),
        "alcohol_suspected": "YES" if "ALCOHOL" in text else "NO",
    }

# -------------------------
# Main Loop (ALL PDFs)
# -------------------------
for pdf_path in DOWNLOADS_DIR.glob("*.pdf"):
    print(f"Processing {pdf_path.name}")

    with pdfplumber.open(pdf_path) as pdf:
        pages = [normalize_text(p.extract_text() or "") for p in pdf.pages]

    crash = extract_crash_info(pages[0]) if len(pages) > 0 else {}
    vehicle = extract_vehicle_info(pages[1]) if len(pages) > 1 else {}
    driver = extract_driver_info(pages[2]) if len(pages) > 2 else {}

    data = map_to_required_schema(pdf_path, crash, vehicle, driver)


    output_file = OUTPUT_DIR / f"{pdf_path.stem}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Saved → {output_file}")

print("\n✅ All PDFs processed successfully")