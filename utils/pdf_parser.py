import fitz  # PyMuPDF
import json
import re
from pathlib import Path
from typing import Dict, List, Any

class OhioCrashParser:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = None
        # Initialize FULL Schema
        self.data = {
            "incident_number": "", 
            "report_number": "", 
            "department": "Ohio State Highway Patrol",
            "state_code": "", 
            "state_abbreviation": "OH", 
            "state_name": "OHIO",
            "county_code": "", 
            "county": "", 
            "municipality_code": "", 
            "municipality": "",
            "crash_location": "", 
            "crash_type_l1": "", 
            "crash_type_l2": "",
            "date_of_crash": "", 
            "total_killed": "0", 
            "total_injured": "0", 
            "total_vehicles": "0",
            "case_file_s3_path": "", 
            "s3_bucket_name": "", 
            "s3_access_key": "", 
            "s3_secret_key": "",
            "pdf_file_path": str(pdf_path),
            "case_detail": [],
            "vehicles": []
        }
        # Temp dictionary to store vehicles by their Unit ID
        self.temp_units = {}

    def parse(self):
        try:
            self.doc = fitz.open(self.pdf_path)
            
            # --- DYNAMIC PAGE LOOP ---
            for page_num, page in enumerate(self.doc):
                # Get text blocks to preserve some layout, but flat list for searching
                text = page.get_text("text")
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                page_type = self._identify_page_type(lines)
                print(f"📄 Page {page_num+1}: {page_type}")

                if page_type == "BASIC_INFO":
                    self._extract_basic_info(lines)
                elif page_type == "UNIT":
                    self._extract_unit_info(lines)
                elif page_type == "MOTORIST":
                    self._extract_motorist_info(lines)
                elif page_type == "OCCUPANT":
                    self._extract_occupant_info(lines)

            # --- FINALIZE DATA ---
            # Sort vehicles by Unit ID and convert to list
            sorted_ids = sorted(self.temp_units.keys(), key=lambda x: int(x) if x.isdigit() else x)
            for uid in sorted_ids:
                self.data["vehicles"].append(self.temp_units[uid])
            
            self.data["total_vehicles"] = str(len(self.data["vehicles"]))
            
            return self.data
        except Exception as e:
            print(f"❌ Error parsing PDF: {e}")
            return {}

    def _identify_page_type(self, lines: List[str]) -> str:
        """Robust page identification using keywords in the first 20 lines."""
        header_text = " ".join(lines[:20]).upper()
        
        if "LOCAL REPORT NUMBER" in header_text and ("PHOTOS TAKEN" in header_text or "OH-2" in header_text):
            return "BASIC_INFO"
        # Adjusted: Checks for UNIT # and general vehicle terms, less strict on 'OWNER NAME'
        if "UNIT #" in header_text and ("COMMERCIAL" in header_text or "OWNER" in header_text or "VEHICLE" in header_text):
            return "UNIT"
        if "MOTORIST" in header_text and "NON-MOTORIST" in header_text:
            return "MOTORIST"
        if "OCCUPANT" in header_text and "WITNESS" in header_text:
            return "OCCUPANT"
        
        return "UNKNOWN"

    def _find_val(self, lines, keyword, offset=1):
        """Standard next-line finder."""
        for i, line in enumerate(lines):
            if keyword in line:
                if i + offset < len(lines):
                    return lines[i + offset]
        return ""

    def _find_digit_near_keyword(self, lines, keyword, lookahead=5):
        """Scans 'lookahead' lines after keyword to find a pure digit (e.g., County Code '1')."""
        for i, line in enumerate(lines):
            if keyword in line:
                for k in range(1, lookahead + 1):
                    if i + k < len(lines):
                        val = lines[i+k].strip()
                        if val.isdigit():
                            return val
        return ""

    def _extract_basic_info(self, lines):
        # 1. Incident & Report Number
        self.data["incident_number"] = self._find_val(lines, "LOCAL REPORT NUMBER")
        self.data["report_number"] = self._find_val(lines, "LOCAL INFORMATION")
        
        # 2. Municipality
        self.data["municipality_code"] = self._find_val(lines, "NCIC")
        self.data["municipality"] = self.data["municipality_code"]
        
        # 3. County (Use digit search)
        county = self._find_digit_near_keyword(lines, "COUNTY", lookahead=3)
        self.data["county"] = county
        self.data["county_code"] = county

        # 4. Location
        loc_line = self._find_val(lines, "LOCATION: CITY, VILLAGE, TOWNSHIP")
        self.data["crash_location"] = loc_line

        # 5. Crash Date
        date_line = self._find_val(lines, "CRASH DATE")
        self.data["date_of_crash"] = date_line.split(" ")[0] if date_line else ""

        # 6. Severity (Use digit search)
        severity = self._find_digit_near_keyword(lines, "CRASH SEVERITY", lookahead=4)

        # 7. Route Details (Handling header/value merging)
        # Often lines are: "ROUTE TYPE ROUTE NUMBER" -> "SR" -> "136"
        route_type = ""
        route_num = ""
        
        # Search specifically for the sequence
        for i, line in enumerate(lines):
            if "ROUTE TYPE" in line and "ROUTE NUMBER" in line:
                # Look at next few lines for SR, US, CR or numbers
                for k in range(1, 4):
                    if i+k < len(lines):
                        cand = lines[i+k]
                        if cand in ["SR", "US", "CR", "IR"]:
                            route_type = cand
                        elif cand.isdigit():
                            route_num = cand
        
        # Fallback if logic above failed (values might be on same line)
        if not route_num:
             route_num = self._find_val(lines, "ROUTE NUMBER")

        self.data["case_detail"].append({
            "local_information": self.data["report_number"],
            "locality": "TOWNSHIP" if "Township" in loc_line else "CITY",
            "location": self._find_val(lines, "LOCATION ROAD NAME"),
            "route_type": route_type,
            "route_number": route_num, 
            "route_prefix": "NA",
            "lane_speed_limit_1": "",
            "lane_speed_limit_2": "",
            "crash_severity": severity
        })

    def _extract_unit_info(self, lines):
        # 1. Get Unit ID
        unit_id = "1"
        for i, line in enumerate(lines):
            if line == "UNIT #":
                if i+1 < len(lines): unit_id = lines[i+1]
                break
        
        # 2. Sequence of Events
        first_event = self._find_digit_near_keyword(lines, "SEQUENCE OF EVENTS", lookahead=5)

        # 3. Vehicle Details
        # VIN often appears after "VEHICLE IDENTIFICATION #"
        vin = self._find_val(lines, "VEHICLE IDENTIFICATION #")
        
        # Make/Model often sequential
        make = self._find_val(lines, "VEHICLE MAKE")
        model = self._find_val(lines, "VEHICLE MODEL")
        year = self._find_val(lines, "VEHICLE YEAR")

        veh = {
            "vehicle_unit": unit_id,
            "is_commercial": "0", 
            "make": make,
            "model": model,
            "vehicle_year": year,
            "plate_number": self._find_val(lines, "LICENSE PLATE #"),
            "plate_state": self._find_val(lines, "STATE"),
            "vin": vin,
            "policy": self._find_val(lines, "INSURANCE POLICY #"),
            "is_towed": "1" if "TOWED BY:" in " ".join(lines) else "0",
            "is_hit_and_run": "0",
            "color": self._find_val(lines, "COLOR"),
            "vehicle_type": self._find_digit_near_keyword(lines, "VEHICLE TYPE", lookahead=2),
            "vehicle_details": {
                "crash_seq_1st_event": first_event,
                "most_harmful_event": self._find_digit_near_keyword(lines, "MOST HARMFUL EVENT", lookahead=2),
                "insurance_company": self._find_val(lines, "INSURANCE COMPANY"),
                "insurance_verified": "1" if self._find_val(lines, "INSURANCE COMPANY") else "0",
            },
            "persons": [] 
        }
        
        self.temp_units[unit_id] = veh

    def _extract_motorist_info(self, lines):
        # 1. Unit Link
        unit_id = "1"
        for i, line in enumerate(lines):
            if line == "UNIT #":
                if i+1 < len(lines): unit_id = lines[i+1]
                break
        
        # 2. Name Parsing
        raw_name = self._find_val(lines, "NAME: LAST, FIRST, MIDDLE")
        parts = [p.strip() for p in raw_name.split(",")]
        last = parts[0] if len(parts) > 0 else ""
        first = parts[1] if len(parts) > 1 else ""
        middle = parts[2] if len(parts) > 2 else ""

        # 3. Address
        addr_line = self._find_val(lines, "ADDRESS: STREET, CITY, STATE, ZIP")
        if not addr_line or "SAME AS DRIVER" in addr_line:
             # Fallback logic if address spans multiple lines in PDF text stream
             pass

        person = {
            "person_type": "D",
            "first_name": first,
            "last_name": last,
            "middle_name": middle,
            "same_as_driver": "1",
            "address_block": {
                "address_line1": addr_line,
                "address_city": "", 
                "address_state": "",
                "address_zip": ""
            },
            "contact_number": self._find_val(lines, "CONTACT PHONE - INCLUDE AREA CODE"),
            "date_of_birth": self._find_val(lines, "DATE OF BIRTH"),
            "gender": self._find_val(lines, "GENDER"),
            "seating_position": "1",
            "dl_state": self._find_val(lines, "DRIVERS LICENSE STATE"),
            "alcohol_test_status": self._find_digit_near_keyword(lines, "ALCOHOL TEST STATUS", lookahead=2),
            "drug_test_status": self._find_digit_near_keyword(lines, "DRUG TEST STATUS", lookahead=2)
        }

        # 4. Attach to Unit
        if unit_id in self.temp_units:
            self.temp_units[unit_id]["persons"].append(person)
        else:
            self.temp_units[unit_id] = {"vehicle_unit": unit_id, "persons": [person]}

    def _extract_occupant_info(self, lines):
        # Logic for occupant pages if needed (Unit # -> Name)
        pass

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Change this filename to test your specific file
    input_pdf = "20235016815.pdf"  
    
    parser = OhioCrashParser(input_pdf)
    result = parser.parse()
    
    print(json.dumps(result, indent=2))