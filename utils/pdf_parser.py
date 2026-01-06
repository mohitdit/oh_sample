import re
import json
from pathlib import Path
from datetime import datetime
import pdfplumber
from utils.logger import log


class OhioPdfParser:
    """
    Ohio PDF Parser - matches C# logic exactly
    Uses two-pass extraction: layout-preserved and cleaned text
    """
    
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.raw_lines = []  # Layout-preserved (like C# Raw mode)
        self.pure_lines = []  # Cleaned text (like C# Pure mode)
        
    def parse(self):
        """Main parsing entry point"""
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                # Extract in both modes
                for page in pdf.pages:
                    # Raw mode: preserve layout
                    raw_text = page.extract_text(layout=True) or ""
                    raw_lines = raw_text.split('\n')
                    self.raw_lines.extend([line for line in raw_lines if line.strip()])
                    
                    # Pure mode: clean text
                    pure_text = page.extract_text(layout=False) or ""
                    pure_lines = pure_text.split('\n')
                    self.pure_lines.extend([line for line in pure_lines if line.strip()])
            
            if not self.raw_lines:
                log.error(f"No text extracted from {self.pdf_path}")
                return None
            
            # Extract crash info (from raw_lines)
            crash_info = self._extract_crash_basic_info()
            case_info = self._extract_case_info()
            
            # Extract vehicles (from pure_lines - better for structured data)
            vehicles = self._extract_vehicles()
            
            # Build final JSON
            return self._build_final_json(crash_info, case_info, vehicles)
            
        except Exception as e:
            log.error(f"Parse error for {self.pdf_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_crash_basic_info(self) -> dict:
        """Extract basic crash information - matches C# BasicInfo region"""
        info = {
            "report_number": "",
            "case_number": "",
            "department": "",
            "municipality": "",
            "municipality_code": "",
            "no_of_vehicles": 0,
            "county": "",
            "locality_code": "",
            "location": "",
            "date_of_crash": "",
            "reference_road_name": "",
            "local_road_name": ""
        }
        
        for l in range(len(self.raw_lines)):
            line = self.raw_lines[l]
            
            # Report Number - from LOCAL INFORMATION line
            if "LOCAL INFORMATION" in line:
                match = re.search(r'(?<=LOCAL INFORMATION).*', line)
                if match:
                    info["report_number"] = match.group(0).strip()
            
            # Case Number - from REPORT NUMBER * section
            elif "REPORT NUMBER *" in line:
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    # Pattern: extract before "X" or "PHOTOS"
                    match = re.search(r'([0-9\-A-Za-z ]*(?=X(\s|P)))|([0-9A-Za-z\- ]*(?=PHOTOS))', next_line)
                    if match:
                        info["case_number"] = match.group(0).strip()
            
            # Department - from REPORTING AGENCY NAME *
            elif line.startswith("REPORTING AGENCY NAME *"):
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if "NCIC *" not in next_line:
                        info["department"] = next_line.strip()
                        info["municipality"] = next_line.strip()
            
            # NCIC (municipality code) and vehicle count
            elif line.startswith("NCIC *"):
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if not next_line.startswith("NUMBER OF UNITS"):
                        parts = next_line.strip().split(' ')
                        if len(parts) >= 2:
                            info["municipality_code"] = parts[0]
                            try:
                                info["no_of_vehicles"] = int(parts[1])
                            except:
                                pass
            
            # County
            elif line.startswith("COUNTY*"):
                if l - 1 >= 0 and "UNSOLVED" in self.raw_lines[l - 1]:
                    if l + 1 < len(self.raw_lines):
                        next_line = self.raw_lines[l + 1]
                        if "CITY" not in next_line:
                            info["county"] = next_line.strip()
            
            # Locality
            elif line.startswith("LOCALITY*"):
                if l - 1 >= 0 and self.raw_lines[l - 1].endswith("TOWNSHIP"):
                    if l + 1 < len(self.raw_lines):
                        next_line = self.raw_lines[l + 1]
                        if "LOCATION: CITY, VILLAGE, TOWNSHIP*" not in next_line:
                            info["locality_code"] = next_line.strip()
            
            # Location (city/village/township name)
            elif line.startswith("LOCATION: CITY, VILLAGE, TOWNSHIP*"):
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if "CRASH DATE" not in next_line:
                        info["location"] = next_line.strip()
            
            # Crash Date/Time
            elif line.startswith("CRASH DATE / TIME*"):
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if "LATITUDE" not in next_line:
                        info["date_of_crash"] = next_line.strip()
            
            # Reference Road Name
            elif "REFERENCE ROAD NAME (ROAD, MILEPOST, HOUSE #)" in line:
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if "ROUTE TYPE" not in next_line:
                        info["reference_road_name"] = next_line.strip()
            
            # Location Road Name
            elif line.startswith("LOCATION ROAD NAME"):
                # Check if DISTANCE is 2-3 lines ahead
                if (l + 3 < len(self.raw_lines) and self.raw_lines[l + 3].startswith("DISTANCE")) or \
                   (l + 2 < len(self.raw_lines) and self.raw_lines[l + 2].startswith("DISTANCE")):
                    # Check if next line is not a float
                    try:
                        float(self.raw_lines[l + 1].strip())
                    except:
                        info["local_road_name"] = self.raw_lines[l + 1].strip()
        
        return info
    
    def _extract_case_info(self) -> dict:
        """Extract case routing info - matches C# CaseInfo"""
        info = {
            "crash_severity": 0,
            "locality": "TOWNSHIP",
            "route_type": "NA",
            "route_number": "NA",
            "route_prefix": "NA"
        }
        
        for l in range(len(self.raw_lines)):
            line = self.raw_lines[l]
            
            # Crash Severity
            if line.endswith("FATAL"):
                parts = re.split(r'1\s*-|1-', line)
                if len(parts) > 1:
                    try:
                        info["crash_severity"] = int(parts[0].strip())
                    except:
                        pass
            
            # Locality mapping
            elif line.startswith("LOCALITY*"):
                if l - 1 >= 0 and self.raw_lines[l - 1].endswith("TOWNSHIP"):
                    if l + 1 < len(self.raw_lines):
                        next_line = self.raw_lines[l + 1]
                        if "LOCATION: CITY, VILLAGE, TOWNSHIP*" not in next_line:
                            locality_map = ["CITY", "VILLAGE", "TOWNSHIP"]
                            try:
                                code = int(next_line.strip()) - 1
                                if 0 <= code < 3:
                                    info["locality"] = locality_map[code]
                            except:
                                pass
            
            # Route information - complex multi-line logic
            elif line == "LOCATION" and l + 1 < len(self.raw_lines) and self.raw_lines[l + 1] == "REFERENCE":
                if l + 2 < len(self.raw_lines) and "ROUTE NUMBER" in self.raw_lines[l + 2]:
                    # Check for PREFIX pattern (7-11 lines ahead)
                    prefix_found = False
                    for offset in [7, 8, 9, 10, 11]:
                        if l + offset < len(self.raw_lines) and "ROUTE TYPE ROUTE NUMBER PREFIX" in self.raw_lines[l + offset]:
                            prefix_found = True
                            # Get prefix from line before "1 - NORTH"
                            for p in range(l + offset, l + offset + 3):
                                if p < len(self.raw_lines) and "1 - NORTH" in self.raw_lines[p]:
                                    if p - 1 >= 0:
                                        info["route_prefix"] = self.raw_lines[p - 1].strip()
                            info["route_type"] = "NA"
                            info["route_number"] = "NA"
                            break
                    
                    if not prefix_found:
                        # Get route type
                        for offset in [7, 8, 9, 10]:
                            if l + offset < len(self.raw_lines) and "ROUTE TYPE ROUTE NUMBER" in self.raw_lines[l + offset]:
                                if l + offset - 1 >= 0:
                                    info["route_type"] = self.raw_lines[l + offset - 1].strip()
                                break
                        
                        # Get route number
                        for offset in [9, 10, 11, 12]:
                            if l + offset < len(self.raw_lines) and "PREFIX 1 - NORTH" in self.raw_lines[l + offset]:
                                if l + offset - 1 >= 0:
                                    info["route_number"] = self.raw_lines[l + offset - 1].strip()
                                break
                        
                        info["route_prefix"] = "NA"
                    break
        
        return info
    
    def _extract_vehicles(self) -> list:
        """Extract vehicle information - uses pure_lines like C# VehicleDetailsGet"""
        vehicles = []
        current_vehicle = None
        current_vehicle_info = None
        
        for i in range(len(self.pure_lines)):
            line = self.pure_lines[i]
            
            # Start of vehicle section
            if "UNIT #         OWNER NAME: LAST, FIRST, MIDDLE" in line and "SAME AS DRIVER" in line and "OWNER PHONE" in line:
                # Save previous vehicle if exists
                if current_vehicle is not None:
                    vehicles.append(self._build_vehicle_json(current_vehicle, current_vehicle_info))
                
                # Start new vehicle
                current_vehicle = {}
                current_vehicle_info = {}
                
                if i + 1 < len(self.pure_lines):
                    parts = re.split(r'\s{2,}|DAMAGE SCALE', self.pure_lines[i + 1])
                    parts = [p.strip() for p in parts if p.strip() and p.strip() != ' ']
                    
                    if len(parts) >= 1:
                        try:
                            current_vehicle["vehicle_unit"] = int(parts[0])
                            current_vehicle_info["vehicle_unit"] = int(parts[0])
                        except:
                            pass
                    if len(parts) >= 2 and parts[1] != ",":
                        current_vehicle["owner_name"] = parts[1]
                    if len(parts) >= 3:
                        current_vehicle["owner_phone"] = parts[2]
                    
                    log.info(f"Processing Unit # {current_vehicle.get('vehicle_unit', '?')}")
            
            # Damage Severity
            elif current_vehicle and "2 - MINOR DAMAGE" in line and "4 - DISABLING DAMAGE" in line:
                match = re.search(r'\d{1,2}\s{1,15}(?=(2 - MINOR DAMAGE))', line)
                if match:
                    current_vehicle_info["damage_severity"] = match.group(0).strip()
            
            # Owner Address
            elif current_vehicle and "OWNER ADDRESS: STREET, CITY, STATE, ZIP" in line and "SAME AS DRIVER" in line:
                if i + 1 < len(self.pure_lines):
                    # Match address before large spacing and digit
                    matches = re.findall(r'[a-zA-Z0-9,. ]*(?=(\s{4,}\d\s{2,3}))', self.pure_lines[i + 1])
                    if not matches:
                        matches = re.findall(r'[a-zA-Z0-9,. ]*(?=(\s{4,}\d\s{1,2}-))', self.pure_lines[i + 1])
                    if matches and matches[0].strip():
                        current_vehicle["owner_address"] = matches[0].strip()
            
            # Commercial Carrier
            elif current_vehicle and "COMMERCIAL CARRIER: NAME, ADDRESS, CITY, STATE, ZIP" in line:
                if i + 1 < len(self.pure_lines):
                    parts = re.split(r'\s{3,}|DAMAGED AREA\(S\)', self.pure_lines[i + 1])
                    parts = [p.strip() for p in parts if p.strip() and p.strip() != ' ']
                    current_vehicle["carrier_name"] = parts[0] if len(parts) >= 1 else "NA"
                    current_vehicle["carrier_number"] = parts[1] if len(parts) >= 2 else "NA"
            
            # LP STATE, LICENSE PLATE, VIN
            elif current_vehicle and "LP STATE" in line and "LICENSE PLATE" in line and "VEHICLE IDENTIFICATION" in line:
                if i + 1 < len(self.pure_lines):
                    next_line = self.pure_lines[i + 1]
                    if "INSURANCE" in next_line and "INSURANCE COMPANY" in next_line:
                        # No vehicle data
                        current_vehicle["vin"] = "NA"
                        current_vehicle["plate_state"] = "NA"
                        current_vehicle["plate_no"] = "NA"
                        current_vehicle["year"] = 0
                        current_vehicle["make"] = "NA"
                    else:
                        parts = re.split(r'\s{2,}', next_line)
                        parts = [p.strip() for p in parts if p.strip()]
                        
                        # Extract VIN
                        vin_match = re.search(r'\w{17}', next_line)
                        if vin_match:
                            current_vehicle["vin"] = vin_match.group(0)
                        
                        if len(parts) >= 5:
                            current_vehicle["plate_state"] = parts[0]
                            current_vehicle["plate_no"] = parts[1]
                            try:
                                current_vehicle["year"] = int(parts[3])
                            except:
                                pass
                            current_vehicle["make"] = parts[4]
                        elif len(parts) == 1:
                            if "UNKNOWN" in parts[0] or "OTHER" in parts[0]:
                                current_vehicle["make"] = parts[0]
            
            # Insurance info
            elif current_vehicle and "INSURANCE" in line and "INSURANCE COMPANY" in line and "INSURANCE POLICY" in line:
                if i + 1 < len(self.pure_lines):
                    parts = re.split(r'\s{3,}', self.pure_lines[i + 1])
                    parts = [p.strip() for p in parts if p.strip()]
                    
                    if len(parts) == 6:
                        current_vehicle_info["insurance_verified"] = "YES" if parts[0] == "X" else "NO"
                        current_vehicle_info["insurance_company"] = parts[2]
                        current_vehicle["policy_no"] = parts[3]
                        current_vehicle["color"] = parts[4]
                        current_vehicle["model"] = parts[5]
                    elif len(parts) == 3:
                        current_vehicle["color"] = parts[1]
                        current_vehicle["model"] = parts[2]
                    elif len(parts) == 1:
                        # Check if it's a color
                        import webcolors
                        try:
                            webcolors.name_to_hex(parts[0].lower())
                            current_vehicle["color"] = parts[0]
                        except:
                            if "UNKNOWN" in parts[0] or "OTHER" in parts[0]:
                                current_vehicle["make"] = parts[0]
            
            # Towed by
            elif current_vehicle and "TOWED BY: COMPANY" in line and "US DOT #" in line:
                if i + 2 < len(self.pure_lines):
                    parts = re.split(r'\s{2,}', self.pure_lines[i + 2])
                    parts = [p.strip() for p in parts if p.strip()]
                    
                    if len(parts) >= 3:
                        current_vehicle_info["us_dot"] = parts[2] if parts[2].isdigit() else "NA"
                    
                    if len(parts) == 4:
                        current_vehicle_info["towed_by"] = parts[3]
                    elif len(parts) == 3:
                        current_vehicle_info["towed_by"] = "NA" if parts[2].isdigit() else parts[2]
                    else:
                        current_vehicle_info["towed_by"] = "NA"
                    
                    if i + 3 < len(self.pure_lines) and self.pure_lines[i + 3].strip().startswith("X"):
                        current_vehicle["is_commercial"] = True
                    
                    current_vehicle["is_towed"] = current_vehicle_info.get("towed_by") != "NA"
            
            # Hit/Skip
            elif current_vehicle and line.strip().startswith("DEVICE                    HIT/SKIP UNIT"):
                if i + 1 < len(self.pure_lines):
                    if re.search(r'\sX\s', self.pure_lines[i + 1]):
                        current_vehicle["is_hit_and_run"] = True
                
                # Occupants
                if i + 3 < len(self.pure_lines):
                    match = re.search(r'\s*\d{1,2}\s*(?=3 -)', self.pure_lines[i + 3])
                    if match:
                        current_vehicle_info["no_of_occupants"] = int(match.group(0).strip())
            
            # Date of Birth - signals end of vehicle section
            elif current_vehicle and "DATE OF BIRTH" in line:
                if current_vehicle:
                    vehicles.append(self._build_vehicle_json(current_vehicle, current_vehicle_info))
                    current_vehicle = None
                    current_vehicle_info = None
                break
        
        # Add last vehicle if exists
        if current_vehicle:
            vehicles.append(self._build_vehicle_json(current_vehicle, current_vehicle_info))
        
        return vehicles
    
    def _build_vehicle_json(self, veh: dict, veh_info: dict) -> dict:
        """Build vehicle JSON matching required schema"""
        return {
            "vehicle_unit": str(veh.get("vehicle_unit", "1")),
            "is_commercial": "1" if veh.get("is_commercial", False) else "0",
            "make": f" {veh.get('make', '')}",
            "model": veh.get("model", ""),
            "vehicle_year": str(veh.get("year", "")),
            "plate_number": f" {veh.get('plate_no', '')}",
            "plate_state": f" {veh.get('plate_state', '')}",
            "plate_year": "",
            "vin": veh.get("vin", ""),
            "policy": veh.get("policy_no", ""),
            "is_driven": "",
            "is_left_at_scene": "",
            "is_towed": "1" if veh.get("is_towed", False) else "0",
            "is_impounded": "",
            "is_disabled": "",
            "is_parked": "0",
            "is_pedestrian": "",
            "is_pedal_cyclist": "",
            "is_hit_and_run": "1" if veh.get("is_hit_and_run", False) else "0",
            "vehicle_used": "",
            "vehicle_type": str(veh.get("vehicle_type", "1")),
            "trailer_or_carrier_count": "0",
            "color": veh.get("color", ""),
            "vehicle_body_type": "",
            "vehicle_travel_direction": "",
            "vehicle_details": {
                "crash_seq_1st_event": "",
                "crash_seq_2nd_event": "",
                "crash_seq_3rd_event": "",
                "crash_seq_4th_event": "",
                "harmful_event": "",
                "authorized_speed": "",
                "estimated_original_speed": "",
                "estimated_impact_speed": "",
                "tad": "",
                "estimated_damage": "",
                "most_harmful_event": "",
                "insurance_company": veh_info.get("insurance_company", ""),
                "insurance_verified": veh_info.get("insurance_verified", ""),
                "us_dot": veh_info.get("us_dot", ""),
                "towed_by": veh_info.get("towed_by", ""),
                "occupant_count": str(veh_info.get("no_of_occupants", "")),
                "initial_impact": "",
                "contributing_circumstance": "",
                "damage_severity": veh_info.get("damage_severity", ""),
                "damaged_area": "",
                "vehicle_defects": "",
                "overweight_permit": ""
            },
            "persons": []  # TODO: Extract person data
        }
    
    def _build_final_json(self, crash_info: dict, case_info: dict, vehicles: list) -> dict:
        """Build final JSON structure"""
        # Parse date
        date_of_crash = ""
        if crash_info.get("date_of_crash"):
            try:
                dt = datetime.strptime(crash_info["date_of_crash"].split()[0], "%m/%d/%Y")
                date_of_crash = dt.strftime("%Y-%m-%d")
            except:
                pass
        
        return {
            "incident_number": crash_info.get("case_number", ""),
            "report_number": crash_info.get("report_number", ""),
            "department": crash_info.get("department", ""),
            "state_code": "",
            "state_abbreviation": "OH",
            "state_name": "OHIO",
            "county_code": crash_info.get("county", ""),
            "county": crash_info.get("county", ""),
            "municipality_code": crash_info.get("municipality_code", ""),
            "municipality": crash_info.get("municipality_code", ""),
            "crash_location": crash_info.get("location", ""),
            "crash_type_l1": "",
            "crash_type_l2": "",
            "date_of_crash": date_of_crash,
            "total_killed": "",
            "total_injured": "",
            "total_vehicles": str(crash_info.get("no_of_vehicles", "")),
            "case_file_s3_path": "",
            "s3_bucket_name": "",
            "s3_access_key": "",
            "s3_secret_key": "",
            "pdf_file_path": str(self.pdf_path),
            "case_detail": [
                {
                    "local_information": "",
                    "locality": case_info.get("locality", "TOWNSHIP"),
                    "location": "NA",
                    "route_type": case_info.get("route_type", "NA"),
                    "route_number": case_info.get("route_number", "NA"),
                    "route_prefix": case_info.get("route_prefix", "NA"),
                    "lane_speed_limit_1": "",
                    "lane_speed_limit_2": "",
                    "crash_severity": str(case_info.get("crash_severity", ""))
                }
            ],
            "vehicles": vehicles
        }


def convert_pdf_to_json(pdf_path: Path, output_dir: Path = None) -> bool:
    """Convert PDF to JSON"""
    if output_dir is None:
        output_dir = Path("json_output")
    
    output_dir.mkdir(exist_ok=True)
    
    try:
        parser = OhioPdfParser(pdf_path)
        data = parser.parse()
        
        if data:
            json_path = output_dir / f"{pdf_path.stem}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            log.info(f"✅ Converted {pdf_path.name} → {json_path.name}")
            return True
        else:
            log.error(f"❌ Failed to parse {pdf_path.name}")
            return False
            
    except Exception as e:
        log.error(f"❌ Error converting {pdf_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return False