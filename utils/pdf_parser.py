import re
import json
from pathlib import Path
from datetime import datetime
import pdfplumber
from utils.logger import log


class OhioPdfParser:
    """Parser for Ohio crash report PDFs with improved accuracy"""
    
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.raw_pages = []
        self.pure_pages = []
        
    def parse(self):
        """Parse the PDF and return structured data"""
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                # Extract text in both raw and pure formats for different parsing needs
                for page in pdf.pages:
                    raw_text = page.extract_text() or ""
                    self.raw_pages.append(raw_text)
                    # Also store line-by-line for better parsing
                    self.pure_pages.append(raw_text.split('\n'))
            
            # Extract data
            crash_info = self._extract_crash_info()
            vehicles = self._extract_all_vehicles()
            
            # Build the final JSON structure
            return self._build_json_structure(crash_info, vehicles)
            
        except Exception as e:
            log.error(f"Error parsing PDF {self.pdf_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _find_in_lines(self, pattern, lines, start_index=0, flags=re.IGNORECASE):
        """Find pattern in list of lines starting from start_index"""
        for i in range(start_index, len(lines)):
            m = re.search(pattern, lines[i], flags)
            if m:
                return m.group(1) if m.lastindex else m.group(0), i
        return None, -1
    
    def _extract_crash_info(self) -> dict:
        """Extract crash information from page 1"""
        if not self.raw_pages or not self.pure_pages:
            return {}
        
        page1_text = self.raw_pages[0]
        page1_lines = self.pure_pages[0]
        
        # Extract report number (LOCAL INFORMATION at very top)
        report_number = ""
        for line in page1_lines[:5]:  # Check first 5 lines only
            if "LOCAL INFORMATION" in line:
                # The number is on the same line or next line
                m = re.search(r'P\d{14}', line)
                if m:
                    report_number = m.group(0)
                break
        
        # Extract incident number (LOCAL REPORT NUMBER)
        incident_number = ""
        for i, line in enumerate(page1_lines):
            if "LOCAL REPORT NUMBER" in line and "*" in line:
                # Number is typically 2-3 lines below
                for j in range(i+1, min(i+5, len(page1_lines))):
                    m = re.match(r'^\d{2}-\d{4}-\d{2}$', page1_lines[j].strip())
                    if m:
                        incident_number = m.group(0)
                        break
                break
        
        # Extract department (REPORTING AGENCY NAME)
        department = ""
        for i, line in enumerate(page1_lines):
            if "REPORTING AGENCY NAME" in line and "*" in line:
                # Department is typically on next line
                if i+1 < len(page1_lines):
                    dept_line = page1_lines[i+1].strip()
                    # Clean up - remove NCIC if it appears
                    if "NCIC" not in dept_line and dept_line:
                        department = dept_line
                    else:
                        # Try next line
                        m = re.search(r'^([A-Za-z\s]+?)(?:\s+NCIC|$)', dept_line)
                        if m:
                            department = m.group(1).strip()
                break
        
        # Extract NCIC (municipality code)
        municipality_code = ""
        for i, line in enumerate(page1_lines):
            if line.strip() == "NCIC *":
                # Code is on next line
                if i+1 < len(page1_lines):
                    ncic_line = page1_lines[i+1].strip()
                    # Extract just the code (e.g., "OHP08")
                    m = re.match(r'^([A-Z0-9]+)', ncic_line)
                    if m:
                        municipality_code = m.group(1)
                break
        
        # Extract number of units
        total_vehicles = ""
        for i, line in enumerate(page1_lines):
            if "NUMBER OF UNITS" in line:
                if i+1 < len(page1_lines):
                    m = re.match(r'^(\d+)', page1_lines[i+1].strip())
                    if m:
                        total_vehicles = m.group(1)
                break
        
        # Extract county
        county_code = ""
        for i, line in enumerate(page1_lines):
            if line.strip() == "COUNTY*":
                # County code is on next line before "1 - CITY"
                if i+1 < len(page1_lines):
                    m = re.match(r'^(\d+)', page1_lines[i+1].strip())
                    if m:
                        county_code = m.group(1)
                break
        
        # Extract locality
        locality_code = ""
        for i, line in enumerate(page1_lines):
            if line.strip() == "LOCALITY*":
                if i+1 < len(page1_lines):
                    m = re.match(r'^(\d+)', page1_lines[i+1].strip())
                    if m:
                        locality_code = m.group(1)
                break
        
        locality_map = {"1": "CITY", "2": "VILLAGE", "3": "TOWNSHIP"}
        locality = locality_map.get(locality_code, "TOWNSHIP")
        
        # Extract crash location (city/village/township name)
        crash_location = ""
        for i, line in enumerate(page1_lines):
            if "LOCATION: CITY, VILLAGE, TOWNSHIP*" in line:
                if i+1 < len(page1_lines):
                    loc_line = page1_lines[i+1].strip()
                    # Remove "CRASH DATE" if it appears
                    if "CRASH DATE" not in loc_line and loc_line:
                        crash_location = loc_line
                break
        
        # Extract crash date/time
        date_of_crash = ""
        for i, line in enumerate(page1_lines):
            if "CRASH DATE / TIME*" in line:
                if i+1 < len(page1_lines):
                    datetime_match = re.search(r'(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})', page1_lines[i+1])
                    if datetime_match:
                        try:
                            dt = datetime.strptime(datetime_match.group(1), "%m/%d/%Y")
                            date_of_crash = dt.strftime("%Y-%m-%d")
                        except:
                            pass
                break
        
        # Extract crash severity
        crash_severity = ""
        for i, line in enumerate(page1_lines):
            if "CRASH SEVERITY" in line:
                # Look backwards for the number
                for j in range(i-1, max(0, i-5), -1):
                    m = re.search(r'^(\d+)\s*$', page1_lines[j].strip())
                    if m:
                        crash_severity = m.group(1)
                        break
                break
        
        # Extract route information - look in LOCATION section
        route_type = ""
        route_number = ""
        
        # Find the route type and number in the bottom section
        for i, line in enumerate(page1_lines):
            if "ROUTE TYPE ROUTE NUMBER" in line:
                # Route type is typically a few lines below
                for j in range(i+1, min(i+10, len(page1_lines))):
                    # Look for pattern like "SR" or "US" or "CR"
                    m = re.match(r'^(SR|US|CR|IR|TR)$', page1_lines[j].strip())
                    if m:
                        route_type = m.group(1)
                        # Route number is typically on next line
                        if j+1 < len(page1_lines):
                            n = re.match(r'^(\d+)', page1_lines[j+1].strip())
                            if n:
                                route_number = n.group(1)
                        break
                break
        
        return {
            "incident_number": incident_number,
            "report_number": report_number,
            "department": department,
            "county_code": county_code,
            "municipality_code": municipality_code,
            "crash_location": crash_location,
            "date_of_crash": date_of_crash,
            "total_vehicles": total_vehicles,
            "crash_severity": crash_severity,
            "locality": locality,
            "route_type": route_type or "NA",
            "route_number": route_number or "NA",
        }
    
    def _extract_all_vehicles(self) -> list:
        """Extract all vehicles from the PDF"""
        vehicles = []
        
        # Skip page 1 (crash info), process remaining pages
        for page_num in range(1, len(self.pure_pages)):
            page_lines = self.pure_pages[page_num]
            
            # Find all UNIT # occurrences on this page
            for i, line in enumerate(page_lines):
                if re.match(r'^UNIT\s*#$', line.strip()):
                    # Unit number is on next line
                    if i+1 < len(page_lines):
                        m = re.match(r'^(\d+)$', page_lines[i+1].strip())
                        if m:
                            unit_num = m.group(1)
                            vehicle = self._extract_vehicle_from_page(page_lines, unit_num, i)
                            if vehicle:
                                vehicles.append(vehicle)
        
        return vehicles
    
    def _extract_vehicle_from_page(self, page_lines: list, unit_num: str, start_idx: int) -> dict:
        """Extract vehicle data starting from a specific index"""
        
        # Initialize vehicle data
        vehicle_data = {
            "owner_name": "",
            "plate_state": "",
            "plate_number": "",
            "vin": "",
            "occupants": "",
            "make": "",
            "color": "",
            "model": "",
            "year": "",
            "insurance_company": "",
            "insurance_policy": "",
            "insurance_verified": "",
            "towed_by": "",
            "vehicle_type": "",
            "is_commercial": "0",
            "is_hit_and_run": "0",
            "owner_address": "",
            "owner_phone": "",
        }
        
        # Person data
        person_data = {
            "name": "",
            "dob": "",
            "age": "",
            "gender": "",
            "address": "",
            "phone": "",
            "ol_state": "",
            "ol_class": "",
            "citation": "",
            "offense_charged": "",
            "offense_description": "",
        }
        
        # Extract owner name - should be a few lines after UNIT #
        for i in range(start_idx, min(start_idx + 10, len(page_lines))):
            if "OWNER NAME: LAST, FIRST, MIDDLE" in page_lines[i]:
                if i+1 < len(page_lines):
                    owner_line = page_lines[i+1].strip()
                    # Remove "SAME AS DRIVER" if present
                    owner_line = re.sub(r'\(\s*SAME AS DRIVER\s*\)', '', owner_line).strip()
                    if owner_line and "UNIT #" not in owner_line:
                        vehicle_data["owner_name"] = owner_line
                break
        
        # Extract LP STATE and LICENSE PLATE #
        for i in range(start_idx, len(page_lines)):
            if "LP STATE" in page_lines[i] and "LICENSE PLATE" in page_lines[i]:
                # Data is typically on next line
                if i+1 < len(page_lines):
                    lp_line = page_lines[i+1].strip()
                    # Format: "KY 2802GB ..."
                    parts = lp_line.split()
                    if len(parts) >= 2:
                        vehicle_data["plate_state"] = parts[0]
                        vehicle_data["plate_number"] = parts[1]
                break
        
        # Extract VIN
        for i in range(start_idx, len(page_lines)):
            if "VEHICLE IDENTIFICATION" in page_lines[i]:
                if i+1 < len(page_lines):
                    vin_line = page_lines[i+1].strip()
                    # VIN is 17 characters
                    m = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', vin_line)
                    if m:
                        vehicle_data["vin"] = m.group(1)
                break
        
        # Extract occupants
        for i in range(start_idx, len(page_lines)):
            if "# OCCUPANTS" in page_lines[i]:
                if i+1 < len(page_lines):
                    m = re.match(r'^(\d+)', page_lines[i+1].strip())
                    if m:
                        vehicle_data["occupants"] = m.group(1)
                break
        
        # Extract make
        for i in range(start_idx, len(page_lines)):
            if "VEHICLE MAKE" in page_lines[i]:
                if i+1 < len(page_lines):
                    make_line = page_lines[i+1].strip()
                    # Make is typically one word
                    m = re.match(r'^([A-Z]+)', make_line)
                    if m:
                        vehicle_data["make"] = m.group(1)
                break
        
        # Extract color
        for i in range(start_idx, len(page_lines)):
            if "COLOR" in page_lines[i]:
                # Color might be on same line or next
                color_match = re.search(r'COLOR\s*([A-Z]{3})', page_lines[i])
                if color_match:
                    vehicle_data["color"] = color_match.group(1)
                elif i+1 < len(page_lines):
                    m = re.match(r'^([A-Z]{3})', page_lines[i+1].strip())
                    if m:
                        vehicle_data["color"] = m.group(1)
                break
        
        # Extract model
        for i in range(start_idx, len(page_lines)):
            if "VEHICLE MODEL" in page_lines[i]:
                model_match = re.search(r'VEHICLE\s+MODEL\s*([A-Z0-9\-]+)', page_lines[i])
                if model_match:
                    vehicle_data["model"] = model_match.group(1)
                break
        
        # Extract year
        for i in range(start_idx, len(page_lines)):
            if "VEHICLE YEAR" in page_lines[i]:
                if i+1 < len(page_lines):
                    year_line = page_lines[i+1].strip()
                    m = re.match(r'^(19|20)\d{2}', year_line)
                    if m:
                        vehicle_data["year"] = m.group(0)
                break
        
        # Extract insurance company and policy
        for i in range(start_idx, len(page_lines)):
            if "INSURANCE COMPANY" in page_lines[i] and "INSURANCE POLICY" in page_lines[i]:
                if i+1 < len(page_lines):
                    ins_line = page_lines[i+1].strip()
                    # Look for "INSURANCE VERIFIED" checkbox
                    if i-1 >= 0 and "X" in page_lines[i-1]:
                        vehicle_data["insurance_verified"] = "X"
                break
        
        # Extract insurance company name - more lines down
        for i in range(start_idx, len(page_lines)):
            if "INSURANCE" in page_lines[i] and "VERIFIED" in page_lines[i]:
                # Company name is typically a few lines after
                for j in range(i+1, min(i+5, len(page_lines))):
                    # Look for uppercase company names
                    if re.match(r'^[A-Z\s&]+$', page_lines[j].strip()) and len(page_lines[j].strip()) > 3:
                        vehicle_data["insurance_company"] = page_lines[j].strip()
                        # Policy might be on next line
                        if j+1 < len(page_lines):
                            policy_match = re.search(r'\b(\d{10,})\b', page_lines[j+1])
                            if policy_match:
                                vehicle_data["insurance_policy"] = policy_match.group(1)
                        break
                break
        
        # Extract towed by
        for i in range(start_idx, len(page_lines)):
            if "TOWED BY: COMPANY NAME" in page_lines[i]:
                # Company might be a few lines down
                for j in range(i+1, min(i+5, len(page_lines))):
                    line = page_lines[j].strip()
                    if line and not re.match(r'^\d{4}$', line):  # Skip year line
                        # Check if it's a company name (mixed case or all caps, not a year)
                        if re.match(r'^[A-Z]', line) and len(line) > 2:
                            vehicle_data["towed_by"] = line
                            break
                break
        
        # Extract owner address
        for i in range(start_idx, len(page_lines)):
            if "OWNER ADDRESS: STREET, CITY, STATE, ZIP" in page_lines[i]:
                if i+1 < len(page_lines):
                    addr_line = page_lines[i+1].strip()
                    if addr_line and "SAME AS DRIVER" not in addr_line:
                        vehicle_data["owner_address"] = addr_line
                break
        
        # Extract owner phone
        for i in range(start_idx, len(page_lines)):
            if "OWNER PHONE:INCLUDE AREA CODE" in page_lines[i]:
                if i+1 < len(page_lines):
                    phone_line = page_lines[i+1].strip()
                    m = re.search(r'\d{3}[-.]?\d{3}[-.]?\d{4}', phone_line)
                    if m:
                        vehicle_data["owner_phone"] = m.group(0)
                break
        
        # Extract vehicle type
        for i in range(start_idx, len(page_lines)):
            if "UNIT TYPE" in page_lines[i]:
                # Type is typically a few lines before or after
                for j in range(max(0, i-5), min(i+5, len(page_lines))):
                    m = re.match(r'^(\d+)$', page_lines[j].strip())
                    if m and int(m.group(1)) < 30:  # Vehicle types are 1-27
                        vehicle_data["vehicle_type"] = m.group(1)
                        break
                break
        
        # Check for commercial
        for i in range(start_idx, len(page_lines)):
            if "COMMERCIAL" in page_lines[i] and "GOVERNMENT" in page_lines[i]:
                # Look for X mark nearby
                if i-1 >= 0 and "X" in page_lines[i-1]:
                    vehicle_data["is_commercial"] = "1"
                elif i+1 < len(page_lines) and "X" in page_lines[i+1]:
                    vehicle_data["is_commercial"] = "1"
                break
        
        # Check for hit and run
        for i in range(start_idx, len(page_lines)):
            if "HIT/SKIP UNIT" in page_lines[i]:
                if i-1 >= 0 and "X" in page_lines[i-1]:
                    vehicle_data["is_hit_and_run"] = "1"
                elif i+1 < len(page_lines) and "X" in page_lines[i+1]:
                    vehicle_data["is_hit_and_run"] = "1"
                break
        
        # Now extract person data - look for person section
        person_data = self._extract_person_from_page(page_lines, unit_num)
        
        # Build vehicle object
        return self._build_vehicle_object(vehicle_data, person_data, unit_num)
    
    def _extract_person_from_page(self, page_lines: list, unit_num: str) -> dict:
        """Extract person/driver data from page"""
        person = {
            "name": "",
            "dob": "",
            "age": "",
            "gender": "",
            "address": "",
            "phone": "",
            "ol_state": "",
            "ol_class": "",
            "citation": "",
            "offense_charged": "",
            "offense_description": "",
        }
        
        # Find person section - look for "UNIT #" followed by unit number, then "NAME:"
        unit_section_start = -1
        for i, line in enumerate(page_lines):
            if f"UNIT #" in line:
                # Check if next line has our unit number
                if i+1 < len(page_lines) and page_lines[i+1].strip() == unit_num:
                    unit_section_start = i
                    break
        
        if unit_section_start == -1:
            return person
        
        # Extract name
        for i in range(unit_section_start, min(unit_section_start + 30, len(page_lines))):
            if "NAME: LAST, FIRST, MIDDLE" in page_lines[i]:
                if i+1 < len(page_lines):
                    name_line = page_lines[i+1].strip()
                    if name_line and "DATE OF BIRTH" not in name_line:
                        person["name"] = name_line
                break
        
        # Extract DOB
        for i in range(unit_section_start, min(unit_section_start + 30, len(page_lines))):
            if "DATE OF BIRTH" in page_lines[i]:
                dob_match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', page_lines[i])
                if dob_match:
                    person["dob"] = dob_match.group(1)
                elif i+1 < len(page_lines):
                    dob_match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', page_lines[i+1])
                    if dob_match:
                        person["dob"] = dob_match.group(1)
                break
        
        # Extract age
        for i in range(unit_section_start, min(unit_section_start + 30, len(page_lines))):
            if "AGE" in page_lines[i] and "GENDER" in page_lines[i]:
                # Age and gender are typically on same line
                age_match = re.search(r'\b(\d{1,3})\b', page_lines[i])
                if age_match:
                    person["age"] = age_match.group(1)
                # Try next line too
                elif i+1 < len(page_lines):
                    age_match = re.search(r'^(\d{1,3})', page_lines[i+1].strip())
                    if age_match:
                        person["age"] = age_match.group(1)
                break
        
        # Extract gender
        for i in range(unit_section_start, min(unit_section_start + 30, len(page_lines))):
            if "GENDER" in page_lines[i]:
                gender_match = re.search(r'\b([MFU])\b', page_lines[i])
                if gender_match:
                    person["gender"] = gender_match.group(1)
                elif i+1 < len(page_lines):
                    gender_match = re.search(r'^([MFU])$', page_lines[i+1].strip())
                    if gender_match:
                        person["gender"] = gender_match.group(1)
                break
        
        # Extract address
        for i in range(unit_section_start, min(unit_section_start + 30, len(page_lines))):
            if "ADDRESS: STREET, CITY, STATE, ZIP" in page_lines[i]:
                if i+1 < len(page_lines):
                    addr_line = page_lines[i+1].strip()
                    if addr_line and "UNIT #" not in addr_line:
                        person["address"] = addr_line
                break
        
        # Extract phone
        for i in range(unit_section_start, min(unit_section_start + 30, len(page_lines))):
            if "CONTACT PHONE" in page_lines[i]:
                if i+1 < len(page_lines):
                    phone_match = re.search(r'\d{3}[-.]?\d{3}[-.]?\d{4}', page_lines[i+1])
                    if phone_match:
                        person["phone"] = phone_match.group(0)
                break
        
        # Extract OL STATE
        for i in range(unit_section_start, min(unit_section_start + 50, len(page_lines))):
            if page_lines[i].strip() == "OL STATE":
                if i+1 < len(page_lines):
                    state_match = re.match(r'^([A-Z]{2})$', page_lines[i+1].strip())
                    if state_match:
                        person["ol_state"] = state_match.group(1)
                break
        
        # Extract OL CLASS
        for i in range(unit_section_start, min(unit_section_start + 50, len(page_lines))):
            if page_lines[i].strip() == "OL CLASS":
                if i+1 < len(page_lines):
                    class_match = re.match(r'^(\d+)$', page_lines[i+1].strip())
                    if class_match:
                        person["ol_class"] = class_match.group(1)
                break
        
        # Extract citation number
        for i in range(unit_section_start, min(unit_section_start + 50, len(page_lines))):
            if "CITATION NUMBER" in page_lines[i]:
                if i+1 < len(page_lines):
                    citation_line = page_lines[i+1].strip()
                    if citation_line and len(citation_line) > 5:
                        person["citation"] = citation_line
                break
        
        # Extract offense charged
        for i in range(unit_section_start, min(unit_section_start + 50, len(page_lines))):
            if "OFFENSE CHARGED" in page_lines[i]:
                if i+1 < len(page_lines):
                    offense_line = page_lines[i+1].strip()
                    # Look for code like "4511.44"
                    if re.match(r'^\d{4}', offense_line):
                        person["offense_charged"] = offense_line
                break
        
        # Extract offense description
        for i in range(unit_section_start, min(unit_section_start + 50, len(page_lines))):
            if "OFFENSE DESCRIPTION" in page_lines[i]:
                if i+1 < len(page_lines):
                    desc_line = page_lines[i+1].strip()
                    if desc_line and len(desc_line) > 3:
                        person["offense_description"] = desc_line
                break
        
        return person
    
    def _build_vehicle_object(self, vehicle_data: dict, person_data: dict, unit_num: str) -> dict:
        """Build the final vehicle object"""
        
        # Parse address into components
        address_parts = {"line1": "", "city": "", "state": "", "zip": ""}
        if person_data["address"]:
            addr = person_data["address"]
            # Format: "814 JERSEY RIDGE RD, MAYSVILLE, KY, 41056"
            parts = [p.strip() for p in addr.split(',')]
            if len(parts) >= 4:
                address_parts["line1"] = parts[0]
                address_parts["city"] = parts[1]
                address_parts["state"] = parts[2]
                address_parts["zip"] = parts[3]
            elif len(parts) == 3:
                address_parts["line1"] = parts[0]
                address_parts["city"] = parts[1]
                # Try to split state and zip
                m = re.match(r'([A-Z]{2})\s+(\d{5})', parts[2])
                if m:
                    address_parts["state"] = m.group(1)
                    address_parts["zip"] = m.group(2)
        
        return {
            "vehicle_unit": unit_num,
            "is_commercial": vehicle_data["is_commercial"],
            "make": f" {vehicle_data['make']}" if vehicle_data['make'] else "",
            "model": vehicle_data["model"],
            "vehicle_year": vehicle_data["year"],
            "plate_number": f" {vehicle_data['plate_number']}" if vehicle_data['plate_number'] else "",
            "plate_state": f" {vehicle_data['plate_state']}" if vehicle_data['plate_state'] else "",
            "plate_year": "",
            "vin": vehicle_data["vin"],
            "policy": vehicle_data["insurance_policy"],
            "is_driven": "",
            "is_left_at_scene": "",
            "is_towed": "1" if vehicle_data["towed_by"] else "0",
            "is_impounded": "",
            "is_disabled": "",
            "is_parked": "0",
            "is_pedestrian": "",
            "is_pedal_cyclist": "",
            "is_hit_and_run": vehicle_data["is_hit_and_run"],
            "vehicle_used": "",
            "vehicle_type": vehicle_data["vehicle_type"] or "1",
            "trailer